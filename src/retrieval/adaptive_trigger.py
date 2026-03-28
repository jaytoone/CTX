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

    def __init__(self, codebase_dir: str):
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
        # Module name -> file path mapping
        self.module_to_file: Dict[str, str] = {}

        # BM25 for semantic fallback
        self.bm25: BM25Okapi | None = None
        self._bm25_corpus: List[List[str]] = []

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

                    # Tokenize for BM25
                    expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', content)
                    expanded = expanded.replace("_", " ")
                    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', expanded.lower())
                    self._bm25_corpus.append(tokens)

        if self._bm25_corpus:
            self.bm25 = BM25Okapi(self._bm25_corpus)

    def _index_symbols(self, file_path: str, content: str) -> None:
        """Extract function and class names and map them to file paths."""
        # Match def function_name(
        for match in re.finditer(r'(?:^|\n)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
            name = match.group(1)
            self.symbol_index.setdefault(name, []).append(file_path)

        # Match class ClassName:
        for match in re.finditer(r'(?:^|\n)class\s+([A-Z][a-zA-Z0-9_]*)', content):
            name = match.group(1)
            self.symbol_index.setdefault(name, []).append(file_path)

    def _index_concepts(self, file_path: str, content: str) -> None:
        """Extract concept keywords from docstrings and comments."""
        # Extract from Concepts: line in module docstring
        concept_match = re.search(r'Concepts:\s*(.+)', content)
        if concept_match:
            concepts = [c.strip() for c in concept_match.group(1).split(",")]
            for concept in concepts:
                self.concept_index.setdefault(concept.lower(), []).append(file_path)

        # Extract from Tier: line
        tier_match = re.search(r'Tier:\s*(\w+)', content)
        if tier_match:
            tier = tier_match.group(1).lower()
            self.concept_index.setdefault(f"tier:{tier}", []).append(file_path)

    def _index_imports(self, file_path: str, content: str) -> None:
        """Build import dependency graph from real Python import statements."""
        imports = []

        # Real Python: import X, import X.Y, import X as Z
        for m in re.finditer(r'^\s*import\s+([\w.]+)', content, re.MULTILINE):
            mod = m.group(1).split(".")[0]
            if mod not in imports:
                imports.append(mod)

        # Real Python: from X import Y
        for m in re.finditer(r'^\s*from\s+([\w.]+)\s+import', content, re.MULTILINE):
            mod = m.group(1).split(".")[0]
            if mod not in imports:
                imports.append(mod)

        # CTX-internal comment style (backward compat)
        for m in re.finditer(r'#\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
            mod = m.group(1)
            if mod not in imports:
                imports.append(mod)

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

        # If still nothing, fall back to TF-IDF
        if not matched_files:
            return self._tfidf_retrieve(query_id, query_text, k)

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

        # Step 1: BM25 primary ranker — use extracted concept, not full query_text.
        # Full query text contains noise tokens ("find", "code", "related") that
        # appear in all Python files and dilute the concept-specific signal.
        if self.bm25 is not None:
            concept_expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', concept).replace("_", " ")
            query_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', concept_expanded.lower())
            # Fallback to full query_text tokens if concept is empty or trivial
            if not query_tokens or all(len(t) <= 2 for t in query_tokens):
                full_exp = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
                query_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', full_exp.lower())
            bm25_scores = self.bm25.get_scores(query_tokens)
            max_score = float(np.max(bm25_scores)) if bm25_scores.max() > 0 else 1.0

            for i, score in enumerate(bm25_scores):
                fpath = self.file_paths[i]
                norm_score = float(score) / max_score
                if norm_score > 0.05:
                    matched_files[fpath] = norm_score

        # Step 2: concept_index boosts BM25 results only (no new injections)
        concept_lc = concept.lower()
        for concept_key, file_list in self.concept_index.items():
            if concept_lc in concept_key or concept_key in concept_lc:
                for f in file_list:
                    if f in matched_files:
                        matched_files[f] *= 1.15  # 15% rank boost

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
            if len(w) > 2 and w not in _STOP and w.isalpha()
        ]

        matched_files: Dict[str, float] = {}

        # Priority 1: concept index — metadata/docstring keyword match (score 0.75)
        for concept_key, file_list in self.concept_index.items():
            if any(word in concept_key for word in topic_words if len(word) > 2):
                for f in file_list:
                    matched_files.setdefault(f, 0.0)
                    matched_files[f] = max(matched_files[f], 0.75)

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

        # Check for module names in the query
        for mod_name, fpath in self.module_to_file.items():
            if mod_name in query_text:
                primary_files.add(fpath)

        # If no module name found, use BM25 to find the primary file
        if not primary_files and self.bm25 is not None:
            expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
            query_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', expanded.lower())
            scores = self.bm25.get_scores(query_tokens)
            top_idx = int(np.argmax(scores))
            primary_files.add(self.file_paths[top_idx])

        # Traverse import graph to find dependencies
        all_relevant: Dict[str, float] = {}
        for pf in primary_files:
            all_relevant[pf] = 1.0
            self._traverse_imports(pf, all_relevant, depth=2, decay=0.5)

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
        raw_scores = self.bm25.get_scores(query_tokens)

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
