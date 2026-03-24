"""
Adaptive Trigger retrieval strategy -- the core experiment.

Classifies the query's trigger type, then applies a specialized
retrieval strategy per type:
  - EXPLICIT_SYMBOL  -> exact match on function/class names (high precision)
  - SEMANTIC_CONCEPT -> TF-IDF similarity on expanded concepts
  - TEMPORAL_HISTORY -> keyword match on module docstrings + concepts
  - IMPLICIT_CONTEXT -> graph-based import chain traversal

Dynamically adjusts k based on trigger confidence (CAR-style).
"""

import math
import os
import re
from typing import Dict, List, Set

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.retrieval.full_context import RetrievalResult, estimate_tokens
from src.trigger.trigger_classifier import TriggerClassifier, TriggerType


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

        # TF-IDF for semantic fallback
        self.vectorizer = TfidfVectorizer(
            token_pattern=r'[a-zA-Z_][a-zA-Z0-9_]{1,}',
            lowercase=True,
            max_features=10000,
            sublinear_tf=True,
        )
        self.tfidf_matrix = None

        self._index()

    def _index(self) -> None:
        """Build all indices from the codebase."""
        documents = []

        for root, _, filenames in os.walk(self.codebase_dir):
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.codebase_dir)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()

                    self.files[rel_path] = content
                    self.file_paths.append(rel_path)
                    self.total_tokens += estimate_tokens(content)

                    # Extract module name from MODULE_NAME constant
                    mod_match = re.search(r'MODULE_NAME\s*=\s*"([^"]+)"', content)
                    if mod_match:
                        mod_name = mod_match.group(1)
                        self.module_to_file[mod_name] = rel_path

                    # Build symbol index
                    self._index_symbols(rel_path, content)

                    # Build concept index
                    self._index_concepts(rel_path, content)

                    # Build import graph
                    self._index_imports(rel_path, content)

                    # Expand for TF-IDF
                    expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', content)
                    expanded = expanded.replace("_", " ")
                    documents.append(expanded)

        if documents:
            self.tfidf_matrix = self.vectorizer.fit_transform(documents)

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
        """Build import dependency graph."""
        imports = []
        for match in re.finditer(r'#\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
            imports.append(match.group(1))
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
        """Retrieve by semantic concept matching."""
        matched_files: Dict[str, float] = {}

        # Direct concept index lookup
        for concept_key, file_list in self.concept_index.items():
            if concept.lower() in concept_key or concept_key in concept.lower():
                for f in file_list:
                    matched_files.setdefault(f, 0.0)
                    matched_files[f] = max(matched_files[f], 0.8)

        # Augment with TF-IDF similarity
        if self.tfidf_matrix is not None:
            expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
            query_vec = self.vectorizer.transform([expanded])
            sims = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

            for i, sim in enumerate(sims):
                fpath = self.file_paths[i]
                if sim > 0.05:
                    current = matched_files.get(fpath, 0.0)
                    # Combine: concept match + TF-IDF similarity
                    matched_files[fpath] = max(current, float(sim) * 0.6) + current * 0.4

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
        matching on module docstrings and concept keywords.
        """
        # Extract topic from the query (remove temporal keywords)
        topic = query_text.lower()
        for kw in ["previously", "before", "last time", "earlier", "remember",
                    "discussed", "mentioned", "we talked", "show the module"]:
            topic = topic.replace(kw, "")
        topic = topic.strip()

        # Search in concept index and content
        matched_files: Dict[str, float] = {}

        for concept_key, file_list in self.concept_index.items():
            if any(word in concept_key for word in topic.split() if len(word) > 2):
                for f in file_list:
                    matched_files.setdefault(f, 0.0)
                    matched_files[f] = max(matched_files[f], 0.75)

        # Content search fallback
        for fpath, content in self.files.items():
            content_lower = content.lower()
            match_count = sum(1 for word in topic.split() if len(word) > 2 and word in content_lower)
            if match_count > 0:
                score = min(0.9, match_count * 0.2)
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

        # If no module name found, use TF-IDF to find the primary file
        if not primary_files and self.tfidf_matrix is not None:
            expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
            query_vec = self.vectorizer.transform([expanded])
            sims = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
            top_idx = int(np.argmax(sims))
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
        """Fallback TF-IDF retrieval."""
        if self.tfidf_matrix is None:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="adaptive_trigger",
            )

        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
        query_vec = self.vectorizer.transform([expanded])
        sims = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        top_indices = np.argsort(sims)[::-1][:k]
        retrieved = [self.file_paths[i] for i in top_indices]
        scores = {self.file_paths[i]: float(sims[i]) for i in top_indices}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="adaptive_trigger",
        )
