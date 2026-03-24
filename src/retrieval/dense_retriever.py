"""
Dense retrieval strategy using TF-IDF + cosine similarity.

Lightweight vector-based retrieval without FAISS --
uses scikit-learn's TfidfVectorizer and cosine_similarity.
"""

import os
import re
from typing import Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.retrieval.full_context import RetrievalResult, estimate_tokens


class DenseRetriever:
    """TF-IDF + cosine similarity based retrieval."""

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0
        self.vectorizer = TfidfVectorizer(
            token_pattern=r'[a-zA-Z_][a-zA-Z0-9_]{1,}',
            lowercase=True,
            max_features=10000,
            sublinear_tf=True,
        )
        self.tfidf_matrix = None
        self._index()

    def _index(self) -> None:
        """Index all Python files with TF-IDF."""
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
                    # Expand camelCase and snake_case for better matching
                    expanded = self._expand_identifiers(content)
                    documents.append(expanded)
                    self.total_tokens += estimate_tokens(content)

        if documents:
            self.tfidf_matrix = self.vectorizer.fit_transform(documents)

    def _expand_identifiers(self, text: str) -> str:
        """Expand camelCase and snake_case identifiers for better semantic matching."""
        # Split camelCase: AuthManager -> Auth Manager
        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # Split snake_case: auth_manager -> auth manager
        expanded = expanded.replace("_", " ")
        return expanded

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve top-k files using TF-IDF cosine similarity."""
        if self.tfidf_matrix is None:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="dense_tfidf",
            )

        # Transform query
        expanded_query = self._expand_identifiers(query_text)
        query_vec = self.vectorizer.transform([expanded_query])

        # Compute similarity
        similarities = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Rank by similarity
        top_indices = np.argsort(similarities)[::-1][:k]

        retrieved_files = [self.file_paths[i] for i in top_indices]
        scores = {self.file_paths[i]: float(similarities[i]) for i in top_indices}

        tokens_used = sum(
            estimate_tokens(self.files[f]) for f in retrieved_files
        )

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved_files,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="dense_tfidf",
        )
