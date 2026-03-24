"""
BM25 sparse keyword retrieval strategy.

Uses the rank_bm25 library for keyword-based file retrieval.
"""

import os
import re
from typing import Dict, List

from rank_bm25 import BM25Okapi

from src.retrieval.full_context import RetrievalResult, estimate_tokens


def _tokenize(text: str) -> List[str]:
    """Simple tokenizer: split on non-alphanumeric, lowercase, filter short tokens."""
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
    return [t for t in tokens if len(t) > 1]


class BM25Retriever:
    """BM25 keyword-based retrieval."""

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.file_tokens: List[List[str]] = []
        self.total_tokens = 0
        self.bm25 = None
        self._index()

    def _index(self) -> None:
        """Index all Python files with BM25."""
        for root, _, filenames in os.walk(self.codebase_dir):
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.codebase_dir)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.files[rel_path] = content
                    self.file_paths.append(rel_path)
                    self.file_tokens.append(_tokenize(content))
                    self.total_tokens += estimate_tokens(content)

        if self.file_tokens:
            self.bm25 = BM25Okapi(self.file_tokens)

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve top-k files using BM25 scoring."""
        if self.bm25 is None:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="bm25",
            )

        query_tokens = _tokenize(query_text)
        raw_scores = self.bm25.get_scores(query_tokens)

        # Rank files by score
        scored_files = sorted(
            zip(self.file_paths, raw_scores),
            key=lambda x: x[1],
            reverse=True,
        )

        top_k = scored_files[:k]
        retrieved_files = [f for f, _ in top_k]
        scores = {f: float(s) for f, s in top_k}

        # Calculate tokens used (only top-k files)
        tokens_used = sum(
            estimate_tokens(self.files[f]) for f in retrieved_files
        )

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved_files,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="bm25",
        )
