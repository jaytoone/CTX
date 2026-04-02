"""
Adaptive Trigger retrieval strategy -- the core experiment.

Classifies the query's trigger type, then applies a specialized
retrieval strategy per type:
  - EXPLICIT_SYMBOL  -> exact match on function/class names (high precision)
  - SEMANTIC_CONCEPT -> BM25 similarity on expanded concepts
  - TEMPORAL_HISTORY -> keyword match on module docstrings + concepts
  - IMPLICIT_CONTEXT -> graph-based import chain traversal

Dynamically adjusts k based on trigger confidence (CAR-style).
"""

import os
import re
import warnings
from typing import Dict, List, Set

import numpy as np
from rank_bm25 import BM25Okapi

from src.retrieval.full_context import RetrievalResult, estimate_tokens
from src.trigger.trigger_classifier import TriggerClassifier, TriggerType

# Directories to exclude from indexing (venvs, build artifacts, VCS, caches)
_EXCLUDED_DIRS = frozenset({
    'venv', '.venv', 'env', '.env',
    'node_modules', '__pycache__', '.git', '.svn', '.hg',
    'build', 'dist', 'site-packages', '.local',
    '.tox', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'htmlcov', '.eggs', 'buck-out', '_build',
})


class AdaptiveTriggerRetriever:
    """Adaptive retrieval that selects strategy based on trigger type."""

    def __init__(self, codebase_dir: str, use_dense: bool = False):
        self.codebase_dir = codebase_dir
        self.classifier = TriggerClassifier()
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0

        # Symbol index: maps function/class names to file paths
        self.symbol_index: Dict[str, List[str]] = {}
        # Concept index: maps concept keywords to file paths
        self.concept_index: Dict[str, List[str]] = {}
        # Import graph: maps file -> files it imports (by module name)
        self.import_graph: Dict[str, List[str]] = {}
        # Reverse import graph: maps file -> files that import it (callers)
        self.reverse_import_graph: Dict[str, List[str]] = {}
        # Module name -> file path mapping
        self.module_to_file: Dict[str, str] = {}

        # BM25 for semantic fallback
        self.bm25: BM25Okapi | None = None
        self._bm25_corpus: List[List[str]] = []

        # Dense embedding (optional — enabled for benchmark eval, disabled for hook latency)
        self.use_dense = use_dense
        self._dense_model = None
        self._dense_embeddings: np.ndarray | None = None  # shape: (n_files, dim)

        self._index()

    def _index(self) -> None:
        """Build all indices from the codebase."""
        for root, dirs, filenames in os.walk(self.codebase_dir):
            # Prune excluded directories to avoid indexing venvs, caches, etc.
            dirs[:] = [
                d for d in dirs
                if d not in _EXCLUDED_DIRS and not d.endswith('.egg-info')
            ]
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.codebase_dir)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                    except OSError:
                        continue

                    self.files[rel_path] = content
                    self.file_paths.append(rel_path)
                    self.total_tokens += estimate_tokens(content)

                    # Extract module name from MODULE_NAME constant (CTX-internal)
                    mod_match = re.search(r'MODULE_NAME\s*=\s*"([^"]+)"', content)
                    if mod_match:
                        mod_name = mod_match.group(1)
                        self.module_to_file[mod_name] = rel_path

                    # Derive module name from file path structure (universal)
                    stem = rel_path.replace("\\", "/")
                    if stem.endswith(".py"):
                        stem = stem[:-3]
                    parts = [p for p in stem.split("/") if p and p != "__init__"]
                    if parts:
                        for i in range(len(parts)):
                            mod_key = ".".join(parts[i:])
                            if mod_key not in self.module_to_file:
                                self.module_to_file[mod_key] = rel_path

                    # Build symbol index
                    self._index_symbols(rel_path, content)

                    # Build concept index
                    self._index_concepts(rel_path, content)

                    # Build import graph
                    self._index_imports(rel_path, content)

                    # Tokenize for BM25 (unigrams + selective bigrams for multi-word concepts)
                    expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', content)
                    expanded = expanded.replace("_", " ")
                    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', expanded.lower())
                    # Add bigrams from adjacent meaningful tokens (len>3) to capture
                    # compound concepts like "request_context", "route_handler".
                    bigrams = [
                        f"{tokens[i]}_{tokens[i+1]}"
                        for i in range(len(tokens) - 1)
                        if len(tokens[i]) > 3 and len(tokens[i+1]) > 3
                    ]
                    self._bm25_corpus.append(tokens + bigrams)

        if self._bm25_corpus:
            self.bm25 = BM25Okapi(self._bm25_corpus)

        # Build reverse import graph from complete import_graph + module_to_file
        self._build_reverse_imports()

        # Build dense embeddings if enabled
        if self.use_dense and self.file_paths:
            self._build_dense_index()

    def _build_dense_index(self) -> None:
        """Build sentence embedding index for all files (used in benchmark mode)."""
        try:
            from sentence_transformers import SentenceTransformer
            self._dense_model = SentenceTransformer("all-MiniLM-L6-v2")
            # Truncate each file to first 512 chars for speed; covers most function bodies
            texts = [self.files[fp][:512] for fp in self.file_paths]
            self._dense_embeddings = self._dense_model.encode(
                texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True
            )
        except Exception:
            self._dense_model = None
            self._dense_embeddings = None

    def _build_reverse_imports(self) -> None:
        """Build reverse import graph: imported_file -> list of files that import it.

        Requires import_graph and module_to_file to be fully built first.
        Used in _implicit_retrieve to traverse caller chains (not just dependencies).
        """
        for fpath, imports in self.import_graph.items():
            for mod_name in imports:
                if mod_name in self.module_to_file:
                    imported_file = self.module_to_file[mod_name]
                    if imported_file != fpath:  # avoid self-loops
                        self.reverse_import_graph.setdefault(imported_file, []).append(fpath)

    def _dense_scores(self, query_text: str) -> np.ndarray | None:
        """Return cosine similarity scores between query and all files."""
        if self._dense_model is None or self._dense_embeddings is None:
            return None
        try:
            q_emb = self._dense_model.encode(
                [query_text], normalize_embeddings=True, show_progress_bar=False
            )
            return (self._dense_embeddings @ q_emb.T).flatten()
        except Exception:
            return None

    def _index_symbols(self, file_path: str, content: str) -> None:
        """Extract function and class names using AST (falls back to regex on parse error)."""
        import ast as _ast
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = _ast.parse(content)
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    self.symbol_index.setdefault(node.name, []).append(file_path)
                elif isinstance(node, _ast.ClassDef):
                    self.symbol_index.setdefault(node.name, []).append(file_path)
        except SyntaxError:
            # Graceful degradation: regex fallback for non-parseable files
            for match in re.finditer(r'(?:^|\n)\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
                name = match.group(1)
                self.symbol_index.setdefault(name, []).append(file_path)
            for match in re.finditer(r'(?:^|\n)\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
                name = match.group(1)
                self.symbol_index.setdefault(name, []).append(file_path)

    def _index_concepts(self, file_path: str, content: str) -> None:
        """Extract concept keywords from docstrings and comments."""
        # Extract from Concepts: line in module docstring (CTX-internal)
        concept_match = re.search(r'Concepts:\s*(.+)', content)
        if concept_match:
            concepts = [c.strip() for c in concept_match.group(1).split(",")]
            for concept in concepts:
                self.concept_index.setdefault(concept.lower(), []).append(file_path)

        # Extract from Tier: line (CTX-internal)
        tier_match = re.search(r'Tier:\s*(\w+)', content)
        if tier_match:
            tier = tier_match.group(1).lower()
            self.concept_index.setdefault(f"tier:{tier}", []).append(file_path)

        # General: extract significant nouns from module-level docstring (universal)
        import ast as _ast
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = _ast.parse(content)
            module_doc = _ast.get_docstring(tree)
            if module_doc:
                # Extract words of length 4+ from first 2 lines of docstring
                first_lines = " ".join(module_doc.splitlines()[:2])
                words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{3,}', first_lines.lower())
                for w in set(words):
                    self.concept_index.setdefault(w, []).append(file_path)
        except SyntaxError:
            pass

    def _index_imports(self, file_path: str, content: str) -> None:
        """Build import dependency graph using AST for accuracy (regex fallback).

        Also builds import_alias_map for IMPLICIT_CONTEXT: maps local aliases
        like 'from X import Y as Z' to their source module ('X.Y').
        """
        import ast as _ast
        imports = []
        seen = set()
        # NEW (Iter 6): Track local import aliases for better IMPLICIT_CONTEXT traversal
        self.import_alias_map: Dict[str, Dict[str, str]] = getattr(
            self, 'import_alias_map', {}
        )
        alias_map: Dict[str, str] = {}  # alias -> source_module for this file

        def _add(mod: str) -> None:
            if mod and mod not in seen:
                seen.add(mod)
                imports.append(mod)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = _ast.parse(content)
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Import):
                    for alias in node.names:
                        _add(alias.name.split(".")[0])
                elif isinstance(node, _ast.ImportFrom):
                    if node.module:
                        top = node.module.split(".")[0]
                        _add(top)
                        # NEW (Iter 6): Track alias -> source mapping
                        for alias in node.names:
                            if alias.asname:
                                # 'from X import Y as Z' -> alias_map[Z] = X.Y
                                source = f"{node.module}.{alias.name}"
                                alias_map[alias.asname] = source
                    # Handle relative imports: resolve against file's own package
                    if node.level and node.level > 0:
                        parts = file_path.replace("\\", "/").split("/")
                        # Go up `level` directories from current file's package
                        pkg_parts = parts[:-node.level] if node.level < len(parts) else []
                        if node.module:
                            pkg_parts.extend(node.module.split("."))
                        if pkg_parts:
                            _add(".".join(pkg_parts))
                            _add(pkg_parts[-1])
        except SyntaxError:
            # Regex fallback for import aliases
            for m in re.finditer(r'from\s+([\w.]+)\s+import\s+([\w]+)\s+as\s+(\w+)', content, re.MULTILINE):
                source = f"{m.group(1)}.{m.group(2)}"
                alias_map[m.group(3)] = source
            for m in re.finditer(r'^\s*import\s+([\w.]+)', content, re.MULTILINE):
                _add(m.group(1).split(".")[0])
            for m in re.finditer(r'^\s*from\s+([\w.]+)\s+import', content, re.MULTILINE):
                _add(m.group(1).split(".")[0])

        # NEW (Iter 6): Store alias map for this file
        if alias_map:
            self.import_alias_map[file_path] = alias_map

        self.import_graph[file_path] = imports

    def _adaptive_k(self, trigger_type: TriggerType, confidence: float, total_files: int) -> int:
        """Dynamically compute k based on trigger type and confidence.

        Higher confidence -> smaller k (more focused retrieval).
        EXPLICIT_SYMBOL -> very small k.
        SEMANTIC_CONCEPT -> moderate k.
        IMPLICIT_CONTEXT -> larger k (need dependency chain).
        """
        base_k = {
            TriggerType.EXPLICIT_SYMBOL: 3,
            TriggerType.SEMANTIC_CONCEPT: 8,
            TriggerType.TEMPORAL_HISTORY: 5,
            TriggerType.IMPLICIT_CONTEXT: 10,
        }

        k = base_k.get(trigger_type, 5)

        # Scale inversely with confidence
        if confidence > 0.8:
            k = max(2, int(k * 0.7))
        elif confidence < 0.5:
            k = min(total_files, int(k * 1.5))

        return min(k, total_files)

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve files using adaptive trigger-based strategy."""
        triggers = self.classifier.classify(query_text)
        primary_trigger = triggers[0] if triggers else None

        if primary_trigger is None:
            # Fallback to TF-IDF
            return self._tfidf_retrieve(query_id, query_text, k)

        trigger_type = primary_trigger.trigger_type
        confidence = primary_trigger.confidence
        adaptive_k = self._adaptive_k(trigger_type, confidence, len(self.file_paths))

        # Use the smaller of adaptive_k and requested k
        effective_k = min(adaptive_k, k)

        if trigger_type == TriggerType.EXPLICIT_SYMBOL:
            # In dense benchmark mode, route to concept retrieval so dense embedding augments
            # the symbol match with semantic reranking — critical for NL→Code (COIR-style) queries
            # where the query contains symbol names but meaning comes from full NL context.
            if self.use_dense:
                return self._concept_retrieve(query_id, query_text, primary_trigger.value, k)
            return self._symbol_retrieve(query_id, query_text, primary_trigger.value, effective_k)
        elif trigger_type == TriggerType.SEMANTIC_CONCEPT:
            return self._concept_retrieve(query_id, query_text, primary_trigger.value, effective_k)
        elif trigger_type == TriggerType.TEMPORAL_HISTORY:
            return self._temporal_retrieve(query_id, query_text, primary_trigger.value, effective_k)
        elif trigger_type == TriggerType.IMPLICIT_CONTEXT:
            return self._implicit_retrieve(query_id, query_text, primary_trigger.value, effective_k)
        else:
            return self._tfidf_retrieve(query_id, query_text, effective_k)

    def _symbol_retrieve(self, query_id: str, query_text: str, symbol: str, k: int) -> RetrievalResult:
        """Retrieve by exact symbol name matching."""
        # Clean symbol value
        symbol_clean = symbol.rstrip("(").strip().strip("`'\"")

        matched_files: Dict[str, float] = {}

        # Direct symbol lookup
        if symbol_clean in self.symbol_index:
            for f in self.symbol_index[symbol_clean]:
                matched_files[f] = 1.0

        # Partial match on symbol names
        if not matched_files:
            for sym_name, file_list in self.symbol_index.items():
                if symbol_clean.lower() in sym_name.lower() or sym_name.lower() in symbol_clean.lower():
                    for f in file_list:
                        matched_files.setdefault(f, 0.0)
                        matched_files[f] = max(matched_files[f], 0.7)

        # Also check raw text content for the symbol
        if not matched_files:
            for fpath, content in self.files.items():
                if symbol_clean in content:
                    matched_files[fpath] = 0.5

        # If still nothing, fall back to BM25 on full query text
        if not matched_files:
            return self._tfidf_retrieve(query_id, query_text, k)

        # If all matches are via raw content (unordered, score=0.5), rerank with BM25.
        # Raw content search finds files mentioning the symbol (e.g. in docstrings) but gives
        # no ordering signal. BM25 on the full query text provides a reliable reranking.
        if self.bm25 is not None and all(v == 0.5 for v in matched_files.values()):
            full_exp = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
            full_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', full_exp.lower())
            if full_tokens:
                bm25_scores = self.bm25.get_scores(full_tokens)
                bm25_max = float(np.max(bm25_scores)) if bm25_scores.max() > 0 else 1.0
                for fpath in list(matched_files.keys()):
                    idx = self.file_paths.index(fpath) if fpath in self.file_paths else -1
                    if idx >= 0 and bm25_max > 0:
                        # Blend raw match (0.3) + BM25 (0.7) for better ordering
                        matched_files[fpath] = 0.3 + 0.7 * (float(bm25_scores[idx]) / bm25_max)

        # Sort by score and take top k
        sorted_files = sorted(matched_files.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="adaptive_trigger",
        )

    def _concept_retrieve(self, query_id: str, query_text: str, concept: str, k: int) -> RetrievalResult:
        """Retrieve by semantic concept matching.

        BM25 is the primary ranker. concept_index adds a small boost to BM25
        results only — never injects files that BM25 didn't rank.
        """
        matched_files: Dict[str, float] = {}

        # Step 1: BM25 hybrid ranker — blend concept BM25 + full-query BM25.
        # Concept tokens provide precision (avoid noise words like "find", "code").
        # Full-query tokens provide recall when concept extraction loses information
        # (e.g. long docstrings, COIR-style natural-language-to-code queries).
        if self.bm25 is not None:
            concept_expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', concept).replace("_", " ")
            concept_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', concept_expanded.lower())
            # Fallback to full query_text tokens if concept is empty or trivial
            if not concept_tokens or all(len(t) <= 2 for t in concept_tokens):
                full_exp = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
                concept_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', full_exp.lower())

            # Add bigrams to concept query (matches bigrams in BM25 corpus index)
            concept_bigrams = [
                f"{concept_tokens[i]}_{concept_tokens[i+1]}"
                for i in range(len(concept_tokens) - 1)
                if len(concept_tokens[i]) > 3 and len(concept_tokens[i+1]) > 3
            ]
            concept_tokens = concept_tokens + concept_bigrams

            # Concept BM25
            concept_scores = self.bm25.get_scores(concept_tokens)
            concept_max = float(np.max(concept_scores)) if concept_scores.max() > 0 else 1.0

            # Full-query BM25 — always computed for hybrid blend
            full_exp = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
            full_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', full_exp.lower())
            full_bigrams = [
                f"{full_tokens[i]}_{full_tokens[i+1]}"
                for i in range(len(full_tokens) - 1)
                if len(full_tokens[i]) > 3 and len(full_tokens[i+1]) > 3
            ]
            full_tokens = full_tokens + full_bigrams
            full_scores = self.bm25.get_scores(full_tokens) if full_tokens != concept_tokens else concept_scores
            full_max = float(np.max(full_scores)) if full_scores.max() > 0 else 1.0

            # Blend: concept precision + full recall.
            # Short concepts (≤3 tokens, e.g. "ctx", "deprecated") are already distilled
            # signals — trust concept BM25 more to avoid noise from generic query words
            # like "find", "code", "related" in the full query.
            # Long concepts (COIR-style docstrings) may have dropped information vs the
            # full query, so full recall gets more weight.
            if len(concept_tokens) <= 3:
                # Short/specific concept: trust BM25 precision (0.75 concept, 0.25 full)
                concept_weight = 0.75
                full_weight = 0.25
            else:
                concept_coverage = len(concept_tokens) / max(len(full_tokens), 1)
                full_weight = min(0.6, 0.4 + (1.0 - concept_coverage) * 0.4)  # 0.4–0.6
                concept_weight = 1.0 - full_weight

            for i in range(len(self.file_paths)):
                fpath = self.file_paths[i]
                c_norm = float(concept_scores[i]) / concept_max
                f_norm = float(full_scores[i]) / full_max
                blended = concept_weight * c_norm + full_weight * f_norm
                if blended > 0.05:
                    matched_files[fpath] = blended

        # Step 2: concept_index boosts BM25 results only (no new injections)
        concept_lc = concept.lower()
        for concept_key, file_list in self.concept_index.items():
            if concept_lc in concept_key or concept_key in concept_lc:
                for f in file_list:
                    if f in matched_files:
                        matched_files[f] *= 1.15  # 15% rank boost

        # Step 2a: Symbol-index cross-boost — if a significant query word is a known
        # defined symbol (function/class), inject those files at a moderate score.
        # This helps SEMA queries like "Find all code related to register" where
        # BM25 ranks generic registration-related files highly but the specific
        # defining module (e.g. auth.py with `def register()`) scores low due to
        # low corpus frequency. Only inject for specific symbols (≤5 matching files)
        # to avoid flooding results with common function names like "run".
        _sema_stop = frozenset(['find', 'show', 'code', 'all', 'related', 'about', 'list',
                                 'with', 'from', 'import', 'used', 'that', 'this', 'where'])
        query_lc = query_text.lower()
        for token in re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', query_lc):
            if token in _sema_stop:
                continue
            sym_files = self.symbol_index.get(token, [])
            if 1 <= len(sym_files) <= 5:
                seen = set()
                for f in sym_files:
                    if f not in seen:
                        seen.add(f)
                        if f not in matched_files:
                            matched_files[f] = 0.60  # inject at moderate confidence
                        else:
                            # Boost existing match: symbol definition is a strong signal
                            matched_files[f] = min(1.0, matched_files[f] * 1.2)

        # Step 2b: Path-score boost + filename-stem injection.
        # Two effects:
        #   (a) Boost already-scored files whose path contains query terms.
        #   (b) Inject files whose basename STEM exactly matches a query word —
        #       even if BM25 missed them (e.g. "ctx" query → inject ctx.py directly).
        #       This handles high-IDF suppression where the term is too common in the
        #       codebase for BM25 to rank the defining file highly.
        query_words = set(re.findall(r'[a-zA-Z]{3,}', query_text.lower()))
        if query_words:
            # (a) Boost already-matched files
            for fpath in list(matched_files.keys()):
                fpath_norm = fpath.lower().replace("/", " ").replace("\\", " ").replace("_", " ").replace("-", " ")
                path_words = set(re.findall(r'[a-zA-Z]{3,}', fpath_norm))
                overlap = query_words & path_words
                if overlap:
                    boost = min(1.5, 1.0 + len(overlap) * 0.15)
                    matched_files[fpath] = matched_files[fpath] * boost

            # (b) Stem boost: if a file's single-word basename stem (e.g. "ctx", "views")
            # exactly matches a query word, boost it to a high confidence score.
            # Applies whether or not the file is already in matched_files — if the file
            # has a low BM25 score due to high corpus frequency (e.g. "__init__.py",
            # "__version__.py"), we still want to surface it.
            # Score 0.85 (authoritative naming). Limit 5 files total.
            stem_injected = 0
            for fpath in self.file_paths:
                if stem_injected >= 5:
                    break
                basename_no_ext = os.path.splitext(os.path.basename(fpath))[0]
                stem_parts = re.findall(r'[a-zA-Z]{3,}', basename_no_ext.lower())
                # Only match single-word stems (e.g. ctx, views, init, version)
                if len(stem_parts) == 1 and stem_parts[0] in query_words:
                    current = matched_files.get(fpath, 0.0)
                    if current < 0.85:
                        matched_files[fpath] = 0.85
                    stem_injected += 1

        # Step 3: Dense embedding re-rank (benchmark mode only, use_dense=True)
        # For long NL queries (COIR-style docstrings), dense similarity dramatically
        # outperforms BM25. Blend BM25 (0.25) + Dense (0.75) when dense is available.
        if self.use_dense:
            dense_scores = self._dense_scores(query_text)
            if dense_scores is not None and len(dense_scores) == len(self.file_paths):
                d_max = float(np.max(dense_scores)) if dense_scores.max() > 0 else 1.0
                for i, fpath in enumerate(self.file_paths):
                    d_norm = float(dense_scores[i]) / d_max
                    bm25_score = matched_files.get(fpath, 0.0)
                    # Dense dominates for semantic queries; BM25 adds lexical precision
                    combined = 0.25 * bm25_score + 0.75 * d_norm
                    if combined > 0.02:
                        matched_files[fpath] = combined

        sorted_files = sorted(matched_files.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="adaptive_trigger",
        )

    def _temporal_retrieve(self, query_id: str, query_text: str, temporal_ref: str, k: int) -> RetrievalResult:
        """Retrieve based on temporal/history references.

        Since we don't have actual session history, we simulate by
        matching on module names, paths, and concept keywords.
        temporal_ref carries the extracted topic word (e.g. "setup", "logging").
        """
        _TEMPORAL_KW = frozenset([
            "previously", "before", "last time", "earlier", "remember",
            "discussed", "mentioned", "we talked", "show the module",
            "show", "module", "about", "the", "we",
        ])
        _STOP = frozenset([
            "the", "all", "and", "for", "that", "this", "was", "are",
            "had", "our", "but", "not", "can", "has", "its", "his",
            "a", "an", "to", "of", "in", "is", "it", "be", "by",
            "on", "at", "up", "as", "do", "go", "so", "my", "me",
        ])

        # Use temporal_ref if it's a meaningful topic word (not just a temporal keyword)
        if temporal_ref and temporal_ref not in _TEMPORAL_KW and len(temporal_ref) > 2:
            raw_topic = temporal_ref
        else:
            raw_topic = query_text.lower()
            for kw in _TEMPORAL_KW:
                raw_topic = raw_topic.replace(kw, " ")

        topic_words = [
            w for w in raw_topic.split()
            if len(w) > 2 and w not in _STOP and w.isalnum()  # isalnum: allow "py310" etc.
        ]

        matched_files: Dict[str, float] = {}

        # Priority 1: concept index — metadata/docstring keyword match (score 0.75)
        for concept_key, file_list in self.concept_index.items():
            if any(word in concept_key for word in topic_words if len(word) > 2):
                for f in file_list:
                    matched_files.setdefault(f, 0.0)
                    matched_files[f] = max(matched_files[f], 0.75)

        # Priority 1.5: Symbol index match — if a topic word exactly matches OR is a
        # prefix of a known function/class name, inject the defining files at 0.75.
        # Helps: "abort" → helpers.py (abort), "dispatch" → views.py (dispatch_request).
        # Deduplicates file lists before checking the count threshold (avoids false
        # rejection when a file is indexed multiple times for the same symbol).
        for word in topic_words:
            if len(word) < 4:
                continue
            candidate_files: Dict[str, float] = {}
            for sym_name, file_list in self.symbol_index.items():
                if sym_name == word or sym_name.startswith(word + "_") or sym_name.startswith(word.capitalize()):
                    for f in file_list:
                        candidate_files[f] = 0.75
            if 1 <= len(candidate_files) <= 8:
                for f, score in candidate_files.items():
                    matched_files.setdefault(f, 0.0)
                    matched_files[f] = max(matched_files[f], score)

        # Priority 2: path-based match — filename stem contains topic word (score 0.85)
        # This is higher than concept index since a file named "logging.py" IS the logging module
        if topic_words:
            for fpath in self.file_paths:
                fpath_lower = fpath.lower().replace("/", " ").replace("_", " ").replace("-", " ")
                path_matches = sum(1 for word in topic_words if len(word) > 2 and word in fpath_lower)
                if path_matches > 0:
                    score = min(0.95, 0.7 + path_matches * 0.15)
                    matched_files.setdefault(fpath, 0.0)
                    matched_files[fpath] = max(matched_files[fpath], score)

        # Priority 3: content search (score cap 0.5 — lower than path match)
        if topic_words:
            for fpath, content in self.files.items():
                content_lower = content.lower()
                match_count = sum(1 for word in topic_words if len(word) > 2 and word in content_lower)
                if match_count > 0:
                    score = min(0.5, match_count * 0.2)
                    matched_files.setdefault(fpath, 0.0)
                    matched_files[fpath] = max(matched_files[fpath], score)

        if not matched_files:
            return self._tfidf_retrieve(query_id, query_text, k)

        sorted_files = sorted(matched_files.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="adaptive_trigger",
        )

    def _implicit_retrieve(self, query_id: str, query_text: str, context_ref: str, k: int) -> RetrievalResult:
        """Retrieve using import-chain traversal for implicit context."""
        # First find the primary file mentioned
        primary_files: Set[str] = set()
        path_seeded = False  # True if seeds found via direct path matching (high confidence)

        # Check for module names in the query.
        # Use letter-boundary matching (not substring) to avoid short names like "a"
        # matching inside longer words like "understand".
        # We use [a-zA-Z0-9] (not [a-zA-Z0-9_]) so "auth" matches in "test_auth"
        # (underscore is a separator, not a letter boundary) but "a" does not match in "understand".
        for mod_name, fpath in self.module_to_file.items():
            if len(mod_name) < 2:
                continue
            if re.search(r'(?<![a-zA-Z0-9])' + re.escape(mod_name) + r'(?![a-zA-Z0-9])',
                         query_text, re.IGNORECASE):
                primary_files.add(fpath)

        # Path-based seed selection (NEW): extract long snake_case identifiers from
        # the query (≥8 chars) and match them against file basenames directly.
        # This handles queries like "understand test_security_api_key_header_description"
        # where the module name maps 1:1 to a filename.
        # Much more reliable than BM25 for named-module queries.
        if not primary_files:
            # Extract long identifiers (snake_case, 8+ chars) from query
            identifiers = re.findall(r'[a-z][a-z0-9_]{7,}', query_text.lower())
            _skip = frozenset(['modules', 'needed', 'fully', 'understand', 'related',
                                'previous', 'discussed', 'following', 'function', 'whatever'])
            candidates: Dict[str, List[str]] = {}  # identifier → list of matching fpaths
            for ident in identifiers:
                if ident in _skip:
                    continue
                ident_clean = ident.replace('_', '')
                for fpath in self.file_paths:
                    basename = os.path.splitext(os.path.basename(fpath))[0].lower()
                    basename_clean = basename.replace('_', '')
                    if basename == ident or basename_clean == ident_clean:
                        candidates.setdefault(ident, []).append(fpath)
            # Use candidates: prefer unique matches (1 file → definitive)
            for ident, fpaths in candidates.items():
                if len(fpaths) == 1:
                    # Unique match: use as high-confidence seed
                    primary_files.add(fpaths[0])
                    path_seeded = True
                elif len(fpaths) <= 4:
                    # Ambiguous but limited: add all candidates, let graph resolve
                    for fp in fpaths:
                        primary_files.add(fp)
                    path_seeded = True

        # Always compute BM25 scores — used both for seed selection and final blend.
        # Blending with BM25 is critical for large codebases (e.g. FastAPI 928 files)
        # where import traversal finds no internal deps (external libs not in corpus).
        bm25_scores_arr: "np.ndarray | None" = None
        if self.bm25 is not None:
            expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
            query_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', expanded.lower())
            bigrams = [
                f"{query_tokens[i]}_{query_tokens[i+1]}"
                for i in range(len(query_tokens) - 1)
                if len(query_tokens[i]) > 3 and len(query_tokens[i+1]) > 3
            ]
            bm25_scores_arr = self.bm25.get_scores(query_tokens + bigrams)

        if not primary_files and bm25_scores_arr is not None:
            top_idx = int(np.argmax(bm25_scores_arr))
            primary_files.add(self.file_paths[top_idx])

        # Traverse import graph to find dependencies.
        # Iter 10: depth scales with k: small k → focused 2-hop, large k → deeper 4-hop.
        # FastAPI (928 files) needs deeper traversal for better IMPLICIT recall.
        bfs_depth = 4 if k >= 8 else 2
        all_relevant: Dict[str, float] = {}
        for pf in primary_files:
            all_relevant[pf] = 1.0
            self._traverse_imports(pf, all_relevant, depth=bfs_depth, decay=0.5)

        # Iter 10 NEW: Path boost for import chain — files closer in import chain
        # get higher weight (e.g., direct imports > 2-hop > 3-hop).
        # Normalize by hop distance from primary file.
        for fpath, score in list(all_relevant.items()):
            # Track original traversal depth from primary files
            if fpath in primary_files:
                all_relevant[fpath] = max(score, 1.0)  # Primary files always at max
            else:
                # Check if this file was found via shallow traverse (depth 1)
                # Files at depth 1 should score higher than depth 2+
                in_shallow = False
                for pf in primary_files:
                    if fpath in self.import_graph.get(pf, []):
                        in_shallow = True
                        break
                if in_shallow:
                    all_relevant[fpath] = max(score, 0.8)  # Boost shallow deps

        # NEW (Iter 6): Follow import aliases for better IMPLICIT coverage.
        # When a file imports 'from X import Y as Z', we should also fetch
        # files that export Y (the actual symbol). This helps when queries
        # reference aliased imports.
        alias_map = getattr(self, 'import_alias_map', {})
        for fpath in list(all_relevant.keys()):
            fwd_aliases = alias_map.get(fpath, {})
            for alias_name, source_module in fwd_aliases.items():
                # Source module might map to a file via module_to_file
                if source_module in self.module_to_file:
                    target = self.module_to_file[source_module]
                    if target not in all_relevant:
                        all_relevant[target] = 0.25  # Lower weight — indirect

        # Traverse reverse import graph (callers) — only for low-fan-out files.
        # High-fan-out hubs (e.g. __init__.py) introduce noise.
        for pf in list(primary_files):
            callers = self.reverse_import_graph.get(pf, [])
            if len(callers) <= 10:
                for caller in callers:
                    if caller not in all_relevant:
                        all_relevant[caller] = 0.3
                        self._traverse_imports(caller, all_relevant, depth=1, decay=0.15)

        # BM25 fallback: inject BM25 results when graph traversal under-fills k slots.
        # For large codebases (external libs not in corpus), import traversal often
        # returns only the seed file. BM25 fills the remaining k slots with lexical matches.
        # For small repos with good graph coverage, BM25 is skipped (avoids noise).
        graph_count = len(all_relevant)
        if bm25_scores_arr is not None and len(bm25_scores_arr) == len(self.file_paths):
            bm25_max = float(np.max(bm25_scores_arr)) if bm25_scores_arr.max() > 0 else 1.0
            if graph_count < k:
                # Graph under-filled: use BM25 to complete the result set
                # Blend already-included files; inject new ones at reduced weight
                top_bm25 = np.argsort(bm25_scores_arr)[::-1][:k]
                for idx in top_bm25:
                    fpath = self.file_paths[idx]
                    bm25_norm = float(bm25_scores_arr[idx]) / bm25_max
                    if fpath in all_relevant:
                        all_relevant[fpath] = 0.5 * all_relevant[fpath] + 0.5 * bm25_norm
                    elif bm25_norm > 0.1:
                        all_relevant[fpath] = 0.4 * bm25_norm
            else:
                # Graph well-filled: only blend for already-included files (rerank)
                top_bm25 = np.argsort(bm25_scores_arr)[::-1][:graph_count]
                for idx in top_bm25:
                    fpath = self.file_paths[idx]
                    if fpath in all_relevant:
                        bm25_norm = float(bm25_scores_arr[idx]) / bm25_max
                        all_relevant[fpath] = 0.6 * all_relevant[fpath] + 0.4 * bm25_norm

        sorted_files = sorted(all_relevant.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="adaptive_trigger",
        )

    def _traverse_imports(self, file_path: str, result: Dict[str, float],
                          depth: int, decay: float) -> None:
        """Recursively traverse import graph."""
        if depth <= 0:
            return

        imports = self.import_graph.get(file_path, [])
        for mod_name in imports:
            if mod_name in self.module_to_file:
                imported_file = self.module_to_file[mod_name]
                current_score = result.get(imported_file, 0.0)
                new_score = decay
                if new_score > current_score:
                    result[imported_file] = new_score
                    self._traverse_imports(imported_file, result, depth - 1, decay * 0.5)

    def _tfidf_retrieve(self, query_id: str, query_text: str, k: int) -> RetrievalResult:
        """Fallback BM25 retrieval (replaces TF-IDF)."""
        if self.bm25 is None:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="adaptive_trigger",
            )

        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
        query_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', expanded.lower())
        bigrams = [
            f"{query_tokens[i]}_{query_tokens[i+1]}"
            for i in range(len(query_tokens) - 1)
            if len(query_tokens[i]) > 3 and len(query_tokens[i+1]) > 3
        ]
        raw_scores = self.bm25.get_scores(query_tokens + bigrams)

        top_indices = np.argsort(raw_scores)[::-1][:k]
        retrieved = [self.file_paths[i] for i in top_indices]
        scores = {self.file_paths[i]: float(raw_scores[i]) for i in top_indices}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="adaptive_trigger",
        )
