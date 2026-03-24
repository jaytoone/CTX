"""
Ablation study variants for CTX experiment.

Four variants to measure the contribution of each component:
  A (Full CTX):       import graph + trigger classifier + adaptive-k
  B (No Graph):       trigger classifier + adaptive-k, NO import graph
  C (No Classifier):  import graph + adaptive-k, NO trigger classification (uniform TF-IDF)
  D (Fixed-k=5):      import graph + trigger classifier, fixed k=5 (NO adaptive-k)

Based on AdaptiveTriggerRetriever with selective component disabling.
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


class AblationVariantB:
    """No Graph variant: trigger classifier + adaptive-k, but NO import graph traversal.

    IMPLICIT_CONTEXT queries fall back to TF-IDF instead of graph traversal.
    """

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.classifier = TriggerClassifier()
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0
        self.symbol_index: Dict[str, List[str]] = {}
        self.concept_index: Dict[str, List[str]] = {}

        self.vectorizer = TfidfVectorizer(
            token_pattern=r'[a-zA-Z_][a-zA-Z0-9_]{1,}',
            lowercase=True,
            max_features=10000,
            sublinear_tf=True,
        )
        self.tfidf_matrix = None
        self._index()

    def _index(self) -> None:
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
                    self._index_symbols(rel_path, content)
                    self._index_concepts(rel_path, content)
                    expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', content).replace("_", " ")
                    documents.append(expanded)
        if documents:
            self.tfidf_matrix = self.vectorizer.fit_transform(documents)

    def _index_symbols(self, file_path: str, content: str) -> None:
        for match in re.finditer(r'(?:^|\n)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
            self.symbol_index.setdefault(match.group(1), []).append(file_path)
        for match in re.finditer(r'(?:^|\n)class\s+([A-Z][a-zA-Z0-9_]*)', content):
            self.symbol_index.setdefault(match.group(1), []).append(file_path)

    def _index_concepts(self, file_path: str, content: str) -> None:
        concept_match = re.search(r'Concepts:\s*(.+)', content)
        if concept_match:
            for concept in concept_match.group(1).split(","):
                self.concept_index.setdefault(concept.strip().lower(), []).append(file_path)

    def _adaptive_k(self, trigger_type: TriggerType, confidence: float, total_files: int) -> int:
        base_k = {
            TriggerType.EXPLICIT_SYMBOL: 3,
            TriggerType.SEMANTIC_CONCEPT: 8,
            TriggerType.TEMPORAL_HISTORY: 5,
            TriggerType.IMPLICIT_CONTEXT: 10,
        }
        k = base_k.get(trigger_type, 5)
        if confidence > 0.8:
            k = max(2, int(k * 0.7))
        elif confidence < 0.5:
            k = min(total_files, int(k * 1.5))
        return min(k, total_files)

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        triggers = self.classifier.classify(query_text)
        primary = triggers[0] if triggers else None
        if primary is None:
            return self._tfidf_retrieve(query_id, query_text, k)

        effective_k = min(self._adaptive_k(primary.trigger_type, primary.confidence, len(self.file_paths)), k)

        if primary.trigger_type == TriggerType.EXPLICIT_SYMBOL:
            return self._symbol_retrieve(query_id, query_text, primary.value, effective_k)
        elif primary.trigger_type == TriggerType.IMPLICIT_CONTEXT:
            # KEY ABLATION: no graph, use TF-IDF instead
            return self._tfidf_retrieve(query_id, query_text, effective_k)
        else:
            return self._tfidf_retrieve(query_id, query_text, effective_k)

    def _symbol_retrieve(self, query_id: str, query_text: str, symbol: str, k: int) -> RetrievalResult:
        symbol_clean = symbol.rstrip("(").strip().strip("`'\"")
        matched: Dict[str, float] = {}
        if symbol_clean in self.symbol_index:
            for f in self.symbol_index[symbol_clean]:
                matched[f] = 1.0
        if not matched:
            for sym, flist in self.symbol_index.items():
                if symbol_clean.lower() in sym.lower() or sym.lower() in symbol_clean.lower():
                    for f in flist:
                        matched.setdefault(f, 0.7)
        if not matched:
            return self._tfidf_retrieve(query_id, query_text, k)
        sorted_files = sorted(matched.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)
        return RetrievalResult(query_id=query_id, retrieved_files=retrieved,
                               scores=dict(sorted_files), tokens_used=tokens_used,
                               total_tokens=self.total_tokens, strategy="ablation_no_graph")

    def _tfidf_retrieve(self, query_id: str, query_text: str, k: int) -> RetrievalResult:
        if self.tfidf_matrix is None:
            return RetrievalResult(query_id=query_id, retrieved_files=[], scores={},
                                   tokens_used=0, total_tokens=self.total_tokens,
                                   strategy="ablation_no_graph")
        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
        query_vec = self.vectorizer.transform([expanded])
        sims = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
        top_idx = np.argsort(sims)[::-1][:k]
        retrieved = [self.file_paths[i] for i in top_idx]
        scores = {self.file_paths[i]: float(sims[i]) for i in top_idx}
        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)
        return RetrievalResult(query_id=query_id, retrieved_files=retrieved, scores=scores,
                               tokens_used=tokens_used, total_tokens=self.total_tokens,
                               strategy="ablation_no_graph")


class AblationVariantC:
    """No Classifier variant: import graph + adaptive-k, but NO trigger classification.

    All queries use uniform TF-IDF retrieval (no trigger-specific routing).
    Still uses import graph to expand results.
    """

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0
        self.import_graph: Dict[str, List[str]] = {}
        self.module_to_file: Dict[str, str] = {}

        self.vectorizer = TfidfVectorizer(
            token_pattern=r'[a-zA-Z_][a-zA-Z0-9_]{1,}',
            lowercase=True,
            max_features=10000,
            sublinear_tf=True,
        )
        self.tfidf_matrix = None
        self._index()

    def _index(self) -> None:
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

                    mod_match = re.search(r'MODULE_NAME\s*=\s*"([^"]+)"', content)
                    if mod_match:
                        self.module_to_file[mod_match.group(1)] = rel_path

                    imports = []
                    for m in re.finditer(r'#\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
                        imports.append(m.group(1))
                    self.import_graph[rel_path] = imports

                    expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', content).replace("_", " ")
                    documents.append(expanded)
        if documents:
            self.tfidf_matrix = self.vectorizer.fit_transform(documents)

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Uniform TF-IDF retrieval + graph expansion, no trigger classification."""
        if self.tfidf_matrix is None:
            return RetrievalResult(query_id=query_id, retrieved_files=[], scores={},
                                   tokens_used=0, total_tokens=self.total_tokens,
                                   strategy="ablation_no_classifier")

        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', query_text).replace("_", " ")
        query_vec = self.vectorizer.transform([expanded])
        sims = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Get initial top candidates
        initial_k = max(3, k // 2)
        top_idx = np.argsort(sims)[::-1][:initial_k]
        scored: Dict[str, float] = {self.file_paths[i]: float(sims[i]) for i in top_idx}

        # Expand via import graph
        for fpath in list(scored.keys()):
            for mod_name in self.import_graph.get(fpath, []):
                if mod_name in self.module_to_file:
                    dep = self.module_to_file[mod_name]
                    if dep not in scored:
                        scored[dep] = scored[fpath] * 0.5

        sorted_files = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = dict(sorted_files)
        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved)
        return RetrievalResult(query_id=query_id, retrieved_files=retrieved, scores=scores,
                               tokens_used=tokens_used, total_tokens=self.total_tokens,
                               strategy="ablation_no_classifier")


class AblationVariantD:
    """Fixed-k=5 variant: import graph + trigger classifier, but always k=5.

    Removes the adaptive-k component.
    """

    def __init__(self, codebase_dir: str):
        from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever
        self._inner = AdaptiveTriggerRetriever(codebase_dir)

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Always use k=5, ignoring adaptive-k logic."""
        # Override: always retrieve exactly 5
        result = self._inner.retrieve(query_id, query_text, k=5)
        result.strategy = "ablation_fixed_k5"
        return result
