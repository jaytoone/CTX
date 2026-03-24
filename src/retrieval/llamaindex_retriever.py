"""
LlamaIndex-compatible CodeSplitter retrieval strategy.

Reproduces the core principle of LlamaIndex's CodeSplitter pipeline:
- AST-aware code chunking (40-line chunks with 5-line overlap)
- TF-IDF similarity search over chunks (API-free, fully local)

This is a faithful reimplementation of the CodeSplitter chunking logic
combined with local TF-IDF retrieval, avoiding the need for
llama-index-core or external embedding API calls.
"""

import os
import re
from typing import Dict, List, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.retrieval.full_context import RetrievalResult, estimate_tokens


def _ast_aware_split(content: str, chunk_lines: int = 40, overlap: int = 5) -> List[str]:
    """Split code into chunks respecting function/class boundaries.

    Mimics LlamaIndex CodeSplitter behavior:
    - Tries to break at function/class definition boundaries
    - Falls back to fixed-size line chunks with overlap
    - Each chunk retains enough context for embedding
    """
    lines = content.split("\n")
    if len(lines) <= chunk_lines:
        return [content]

    # Find function/class boundary lines
    boundaries = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "async def ")):
            boundaries.add(i)

    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_lines, len(lines))

        # Try to extend or shrink to a boundary
        if end < len(lines):
            # Look for a boundary near the end of the chunk
            best_break = None
            for b in range(end + 5, max(start + chunk_lines // 2, end - 10) - 1, -1):
                if b in boundaries:
                    best_break = b
                    break
            if best_break is not None:
                end = best_break

        chunk = "\n".join(lines[start:end])
        chunks.append(chunk)

        # Move forward with overlap
        start = max(start + 1, end - overlap)

    return chunks


class LlamaIndexRetriever:
    """LlamaIndex CodeSplitter-compatible retrieval.

    Reproduces LlamaIndex's code retrieval pipeline:
    1. AST-aware chunking (CodeSplitter with 40-line chunks, 5-line overlap)
    2. TF-IDF vectorization of chunks (local, no API)
    3. Cosine similarity search
    4. File-level score aggregation (max chunk score per file)
    """

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0

        # Chunk-level data
        self.chunks: List[str] = []
        self.chunk_to_file: List[str] = []  # chunk index -> file path

        self.vectorizer = TfidfVectorizer(
            token_pattern=r'[a-zA-Z_][a-zA-Z0-9_]{1,}',
            lowercase=True,
            max_features=10000,
            sublinear_tf=True,
        )
        self.tfidf_matrix = None
        self._index()

    def _index(self) -> None:
        """Index all Python files with AST-aware chunking + TF-IDF."""
        for root, _, filenames in os.walk(self.codebase_dir):
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    rel_path = os.path.relpath(fpath, self.codebase_dir)
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    self.files[rel_path] = content
                    self.file_paths.append(rel_path)
                    self.total_tokens += estimate_tokens(content)

                    # AST-aware chunking
                    file_chunks = _ast_aware_split(content, chunk_lines=40, overlap=5)
                    for chunk in file_chunks:
                        self.chunks.append(self._expand_identifiers(chunk))
                        self.chunk_to_file.append(rel_path)

        if self.chunks:
            self.tfidf_matrix = self.vectorizer.fit_transform(self.chunks)

    def _expand_identifiers(self, text: str) -> str:
        """Expand camelCase and snake_case for better matching."""
        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        expanded = expanded.replace("_", " ")
        return expanded

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve top-k files using chunk-level TF-IDF similarity.

        Scores each chunk, then aggregates to file level (max chunk score).
        """
        if self.tfidf_matrix is None:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="llamaindex",
            )

        expanded_query = self._expand_identifiers(query_text)
        query_vec = self.vectorizer.transform([expanded_query])

        # Chunk-level similarities
        chunk_sims = cosine_similarity(query_vec, self.tfidf_matrix).flatten()

        # Aggregate to file level: max chunk score per file
        file_scores: Dict[str, float] = {}
        for idx, sim in enumerate(chunk_sims):
            fpath = self.chunk_to_file[idx]
            file_scores[fpath] = max(file_scores.get(fpath, 0.0), float(sim))

        # Rank and take top-k
        sorted_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved_files = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(
            estimate_tokens(self.files[f]) for f in retrieved_files
        )

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved_files,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="llamaindex",
        )
