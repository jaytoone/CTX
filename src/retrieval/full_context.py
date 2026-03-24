"""
Full Context retrieval strategy (baseline).

Loads all files in the codebase -- represents the naive approach
where the entire codebase is placed in the LLM context window.
"""

import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RetrievalResult:
    """Result from a retrieval strategy."""
    query_id: str
    retrieved_files: List[str]
    scores: Dict[str, float]
    tokens_used: int
    total_tokens: int
    strategy: str


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for code."""
    return max(1, len(text) // 4)


class FullContextRetriever:
    """Baseline: loads every file in the codebase."""

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.total_tokens = 0
        self._load_all()

    def _load_all(self) -> None:
        """Load all Python files from the codebase directory."""
        for root, _, filenames in os.walk(self.codebase_dir):
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.codebase_dir)
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    self.files[rel_path] = content
                    self.total_tokens += estimate_tokens(content)

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve by loading ALL files (baseline behavior).

        In full-context mode, every file gets a score of 1.0 and all are
        returned regardless of k -- this simulates dumping the entire
        codebase into the context window.
        """
        all_files = list(self.files.keys())
        scores = {f: 1.0 for f in all_files}

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=all_files,
            scores=scores,
            tokens_used=self.total_tokens,
            total_tokens=self.total_tokens,
            strategy="full_context",
        )
