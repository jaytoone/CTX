"""
Hybrid: Dense Embedding (seed) + CTX Import Graph (expansion)

Two-stage pipeline combining dense retrieval's semantic matching
with CTX's structural import graph traversal:

  Step 1: Dense retrieval (Chroma + sentence-transformers) selects
          top seed_k files by semantic similarity to the query.
  Step 2: Each seed file is expanded via BFS import graph traversal
          up to expansion_hops depth.
  Step 3: Deduplicated union is scored and top-k returned.

Hypothesis: Dense fills CTX's weakness on text-to-code queries
(COIR R@5: Dense=1.0 vs CTX=0.38), while CTX's graph expansion
preserves structural dependency resolution (IMPLICIT_CONTEXT R@5=1.0).
"""

import os
import re
from collections import deque
from typing import Dict, List, Set, Tuple

from src.retrieval.full_context import RetrievalResult, estimate_tokens


class HybridDenseCTXRetriever:
    """Hybrid retriever: dense embedding seed + import graph expansion.

    Uses ChromaDB + sentence-transformers for semantic seed selection,
    then expands seeds via BFS over the codebase import graph.
    """

    def __init__(self, codebase_dir: str, seed_k: int = 3, expansion_hops: int = 2):
        self.codebase_dir = codebase_dir
        self.seed_k = seed_k
        self.expansion_hops = expansion_hops

        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0

        # Import graph: file -> list of imported module names
        self.import_graph: Dict[str, List[str]] = {}
        # Reverse import graph: file -> list of files that import it
        self.reverse_graph: Dict[str, List[str]] = {}
        # Module name -> file path
        self.module_to_file: Dict[str, str] = {}
        # File path -> module name
        self.file_to_module: Dict[str, str] = {}

        # Dense retrieval via ChromaDB
        self.collection = None

        self._index()

    def _preprocess(self, text: str) -> str:
        """Preprocess code text for embedding."""
        expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        expanded = expanded.replace("_", " ")
        if len(expanded) > 2048:
            expanded = expanded[:2048]
        return expanded

    def _extract_module_name(self, rel_path: str, content: str) -> str:
        """Extract module name from file content or path."""
        mod_match = re.search(r'MODULE_NAME\s*=\s*"([^"]+)"', content)
        if mod_match:
            return mod_match.group(1)
        return os.path.splitext(os.path.basename(rel_path))[0]

    def _parse_imports(self, content: str) -> List[str]:
        """Parse imports from Python source code.

        Handles both synthetic format (# import xxx) and real Python
        imports (import xxx, from xxx import yyy).
        """
        imports = []

        # Synthetic format: # import module_name
        for match in re.finditer(r'#\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
            imports.append(match.group(1))

        # Real Python imports via ast
        try:
            import ast
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        imports.append(parts[-1])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        parts = node.module.split(".")
                        imports.append(parts[-1])
        except SyntaxError:
            pass

        return imports

    def _index(self) -> None:
        """Build dense index (ChromaDB) and import graph."""
        import chromadb

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

                    # Dense index data
                    documents.append(self._preprocess(content))
                    ids.append(rel_path)

                    # Module name mapping
                    mod_name = self._extract_module_name(rel_path, content)
                    self.module_to_file[mod_name] = rel_path
                    self.file_to_module[rel_path] = mod_name

                    # Import graph
                    self.import_graph[rel_path] = self._parse_imports(content)

        # Build reverse graph
        for fpath, imports in self.import_graph.items():
            for mod_name in imports:
                if mod_name in self.module_to_file:
                    target = self.module_to_file[mod_name]
                    self.reverse_graph.setdefault(target, []).append(fpath)

        # Build ChromaDB index
        if documents:
            chroma_client = chromadb.Client()
            self.collection = chroma_client.create_collection(
                name="hybrid_codebase",
                metadata={"hnsw:space": "cosine"},
            )
            batch_size = 50
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                batch_ids = ids[i:i + batch_size]
                self.collection.add(
                    documents=batch_docs,
                    ids=batch_ids,
                )

    def _dense_seed_select(self, query_text: str, seed_k: int) -> List[Tuple[str, float]]:
        """Select seed files using dense embedding similarity.

        Returns list of (file_path, similarity_score) tuples.
        """
        if self.collection is None or self.collection.count() == 0:
            return []

        expanded_query = self._preprocess(query_text)
        results = self.collection.query(
            query_texts=[expanded_query],
            n_results=min(seed_k, self.collection.count()),
        )

        seeds = []
        retrieved_ids = results["ids"][0] if results["ids"] else []
        distances = results["distances"][0] if results["distances"] else []

        for fpath, dist in zip(retrieved_ids, distances):
            sim = max(0.0, 1.0 - dist)
            seeds.append((fpath, sim))

        return seeds

    def _graph_expand(self, seeds: List[str], max_hops: int) -> Dict[str, float]:
        """Expand seed files via BFS over the import graph.

        Traverses both import directions (imports and imported-by).
        Score decays with distance: score = 1.0 / (1 + hop_distance).

        Args:
            seeds: Starting file paths
            max_hops: Maximum BFS depth

        Returns:
            Dict mapping file_path -> relevance score
        """
        scores: Dict[str, float] = {}
        visited: Set[str] = set()
        queue: deque = deque()

        for seed in seeds:
            if seed in self.files:
                queue.append((seed, 0))
                scores[seed] = 1.0
                visited.add(seed)

        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue

            neighbors: Set[str] = set()

            # Forward: files that this node imports
            for mod_name in self.import_graph.get(node, []):
                if mod_name in self.module_to_file:
                    neighbors.add(self.module_to_file[mod_name])

            # Reverse: files that import this node
            for importer in self.reverse_graph.get(node, []):
                neighbors.add(importer)

            for neighbor in neighbors:
                hop = depth + 1
                new_score = 1.0 / (1 + hop)

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, hop))
                    scores[neighbor] = max(scores.get(neighbor, 0.0), new_score)
                elif new_score > scores.get(neighbor, 0.0):
                    scores[neighbor] = new_score

        return scores

    def retrieve(self, query_id: str, query_text: str, k: int = 10) -> RetrievalResult:
        """Retrieve files using hybrid dense+graph strategy.

        1. Dense embedding selects top seed_k files (semantic matching)
        2. Import graph BFS expands from seeds (structural traversal)
        3. Scores are combined and top-k returned

        Args:
            query_id: Query identifier
            query_text: The query text
            k: Number of files to return

        Returns:
            RetrievalResult with scored file list
        """
        # Step 1: Dense seed selection
        seed_results = self._dense_seed_select(query_text, self.seed_k)

        if not seed_results:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="hybrid_dense_ctx",
            )

        seed_files = [fp for fp, _ in seed_results]
        seed_scores = {fp: s for fp, s in seed_results}

        # Step 2: Graph expansion from seeds
        graph_scores = self._graph_expand(seed_files, self.expansion_hops)

        # Step 3: Combine scores
        # Dense seed score (semantic) + graph expansion score (structural)
        combined: Dict[str, float] = {}
        for fpath in set(list(seed_scores.keys()) + list(graph_scores.keys())):
            dense_s = seed_scores.get(fpath, 0.0)
            graph_s = graph_scores.get(fpath, 0.0)
            # Weighted combination: dense similarity + graph proximity
            combined[fpath] = dense_s * 0.5 + graph_s * 0.5

        # Sort and take top-k
        sorted_files = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(
            estimate_tokens(self.files[f]) for f in retrieved if f in self.files
        )

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="hybrid_dense_ctx",
        )
