"""
Chroma + sentence-transformers dense retrieval strategy.

Production-grade RAG pipeline baseline using:
- sentence-transformers (all-MiniLM-L6-v2) for local neural embeddings
- ChromaDB as the local vector database
- Cosine similarity search over dense embeddings

This represents the typical production RAG retrieval setup
that many teams deploy for code search tasks.
"""

import os
import re
import tempfile
from typing import Dict, List

from src.retrieval.full_context import RetrievalResult, estimate_tokens


class ChromaDenseRetriever:
    """Chroma + sentence-transformers dense retrieval.

    Uses real neural embeddings (all-MiniLM-L6-v2) stored in a
    local ChromaDB instance for cosine similarity search.
    This represents the production RAG baseline that most teams use.
    """

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0
        self.collection = None
        self._index()

    def _preprocess(self, text: str) -> str:
        """Preprocess code text for embedding.

        Expands identifiers and adds natural language context
        to improve embedding quality for code.
        """
        # Expand camelCase
        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        # Expand snake_case
        expanded = expanded.replace("_", " ")
        # Truncate to ~512 tokens (model max) -- roughly 2048 chars
        if len(expanded) > 2048:
            expanded = expanded[:2048]
        return expanded

    def _index(self) -> None:
        """Index all Python files into ChromaDB with sentence-transformer embeddings."""
        import chromadb

        # Collect files
        documents = []
        ids = []
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

                    documents.append(self._preprocess(content))
                    ids.append(rel_path)

        if not documents:
            return

        # Create ephemeral Chroma client with sentence-transformer embeddings
        # Uses all-MiniLM-L6-v2 by default via chromadb's built-in embedding
        chroma_client = chromadb.Client()

        # Use default embedding function (all-MiniLM-L6-v2 via onnxruntime)
        self.collection = chroma_client.create_collection(
            name="ctx_codebase",
            metadata={"hnsw:space": "cosine"},
        )

        # Add documents in batches to avoid memory issues
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            self.collection.add(
                documents=batch_docs,
                ids=batch_ids,
            )

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve top-k files using Chroma dense vector search.

        Embeds the query with the same sentence-transformer model
        and performs cosine similarity search in ChromaDB.
        """
        if self.collection is None or self.collection.count() == 0:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="chroma_dense",
            )

        # Query ChromaDB
        expanded_query = self._preprocess(query_text)
        results = self.collection.query(
            query_texts=[expanded_query],
            n_results=min(k, self.collection.count()),
        )

        retrieved_files = results["ids"][0] if results["ids"] else []
        # Chroma returns distances; convert to similarity scores
        distances = results["distances"][0] if results["distances"] else []
        scores = {}
        for fpath, dist in zip(retrieved_files, distances):
            # Cosine distance -> similarity: sim = 1 - dist (for cosine space)
            scores[fpath] = max(0.0, 1.0 - dist)

        tokens_used = sum(
            estimate_tokens(self.files[f]) for f in retrieved_files if f in self.files
        )

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved_files,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="chroma_dense",
        )
