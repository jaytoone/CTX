"""
GraphRAG-lite retrieval strategy -- a strong graph-based baseline.

Lightweight version of Microsoft GraphRAG (no API calls, fully local):
- Builds a NetworkX import-dependency graph from the codebase
- For each query, identifies seed files via keyword/symbol matching
- Traverses the graph via BFS to find connected files
- Scores by hop distance (closer = higher relevance)
- Returns top-k files within configurable max hops
"""

import ast
import os
import re
from collections import deque
from typing import Dict, List, Set, Tuple

import networkx as nx

from src.retrieval.full_context import RetrievalResult, estimate_tokens


def _tokenize_simple(text: str) -> List[str]:
    """Simple tokenizer for matching."""
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
    return [t for t in tokens if len(t) > 1]


class GraphRAGRetriever:
    """GraphRAG-lite: import-graph-based retrieval baseline.

    Builds a directed import graph from the codebase and uses BFS
    traversal with distance-based scoring for retrieval.
    """

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0

        # Graph structures
        self.graph = nx.DiGraph()
        self.module_to_file: Dict[str, str] = {}
        self.file_to_module: Dict[str, str] = {}

        # Symbol index for seed selection
        self.symbol_index: Dict[str, List[str]] = {}

        self._index()

    def build_graph(self, files: List[Dict[str, str]]) -> nx.DiGraph:
        """Build import dependency graph from file data.

        This is the public API for graph construction, useful for
        external callers that want to inspect the graph.

        Args:
            files: List of dicts with 'path' and 'content' keys

        Returns:
            Directed graph where edges represent import relationships
        """
        g = nx.DiGraph()
        mod_to_file = {}

        # First pass: register all modules
        for f in files:
            path = f["path"]
            content = f["content"]
            g.add_node(path)

            # Extract module name
            mod_name = self._extract_module_name(path, content)
            mod_to_file[mod_name] = path

        # Second pass: add import edges
        for f in files:
            path = f["path"]
            content = f["content"]
            imported = self._parse_imports(content)

            for imp in imported:
                if imp in mod_to_file and mod_to_file[imp] != path:
                    # Edge: this file depends on imported file
                    g.add_edge(path, mod_to_file[imp])

        return g

    def _index(self) -> None:
        """Build graph index from the codebase directory."""
        file_data = []

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

                    file_data.append({"path": rel_path, "content": content})

                    # Build symbol index
                    self._index_symbols(rel_path, content)

        # Build the graph
        self.graph = self.build_graph(file_data)

        # Store module mappings
        for fd in file_data:
            mod_name = self._extract_module_name(fd["path"], fd["content"])
            self.module_to_file[mod_name] = fd["path"]
            self.file_to_module[fd["path"]] = mod_name

    def _extract_module_name(self, rel_path: str, content: str) -> str:
        """Extract module name from file content or path.

        Checks for MODULE_NAME constant (synthetic) first,
        then falls back to filename-based module name (real codebases).
        """
        # Synthetic format: MODULE_NAME = "xxx"
        mod_match = re.search(r'MODULE_NAME\s*=\s*"([^"]+)"', content)
        if mod_match:
            return mod_match.group(1)

        # Real codebase: derive from path
        # e.g. "src/utils/helper.py" -> "helper"
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
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        # Take the last component
                        parts = alias.name.split(".")
                        imports.append(parts[-1])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        parts = node.module.split(".")
                        imports.append(parts[-1])
        except SyntaxError:
            pass

        return imports

    def _index_symbols(self, file_path: str, content: str) -> None:
        """Extract function and class names for seed file selection."""
        # Functions
        for match in re.finditer(r'(?:^|\n)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
            name = match.group(1)
            self.symbol_index.setdefault(name, []).append(file_path)

        # Classes
        for match in re.finditer(r'(?:^|\n)class\s+([A-Z][a-zA-Z0-9_]*)', content):
            name = match.group(1)
            self.symbol_index.setdefault(name, []).append(file_path)

    def _find_seed_files(self, query_text: str) -> List[Tuple[str, float]]:
        """Find seed files for BFS traversal based on query matching.

        Returns list of (file_path, score) tuples.
        """
        matched: Dict[str, float] = {}

        # 1. Direct symbol match
        query_tokens = _tokenize_simple(query_text)
        for token in query_tokens:
            if token in self.symbol_index:
                for fpath in self.symbol_index[token]:
                    matched[fpath] = max(matched.get(fpath, 0.0), 1.0)

            # Partial symbol match
            for sym_name, file_list in self.symbol_index.items():
                if token in sym_name.lower() or sym_name.lower() in token:
                    for fpath in file_list:
                        matched[fpath] = max(matched.get(fpath, 0.0), 0.7)

        # 2. Module name match
        for mod_name, fpath in self.module_to_file.items():
            if mod_name.lower() in query_text.lower():
                matched[fpath] = max(matched.get(fpath, 0.0), 0.9)

        # 3. Content keyword match (fallback)
        if not matched:
            for fpath, content in self.files.items():
                content_lower = content.lower()
                hits = sum(1 for t in query_tokens if len(t) > 2 and t in content_lower)
                if hits > 0:
                    score = min(0.6, hits * 0.15)
                    matched[fpath] = max(matched.get(fpath, 0.0), score)

        return sorted(matched.items(), key=lambda x: x[1], reverse=True)

    def _bfs_traverse(self, seeds: List[str], max_hops: int = 3) -> Dict[str, float]:
        """BFS traversal from seed nodes with distance-based scoring.

        Score decays with each hop: score = 1.0 / (1 + hop_distance)

        Args:
            seeds: Starting file paths
            max_hops: Maximum BFS depth

        Returns:
            Dict mapping file_path -> relevance score
        """
        scores: Dict[str, float] = {}
        visited: Set[str] = set()
        queue: deque = deque()

        # Initialize with seeds
        for seed in seeds:
            if seed in self.graph:
                queue.append((seed, 0))
                scores[seed] = 1.0
                visited.add(seed)

        while queue:
            node, depth = queue.popleft()

            if depth >= max_hops:
                continue

            # Traverse both directions (imports and imported-by)
            neighbors = set()
            neighbors.update(self.graph.successors(node))   # files this node imports
            neighbors.update(self.graph.predecessors(node))  # files that import this node

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
        """Retrieve files using graph-based traversal.

        1. Find seed files via keyword/symbol matching
        2. BFS traverse the import graph from seeds
        3. Score by hop distance
        4. Return top-k

        Args:
            query_id: Query identifier
            query_text: The query text
            k: Number of files to return

        Returns:
            RetrievalResult with scored file list
        """
        # Step 1: Find seed files
        seed_matches = self._find_seed_files(query_text)

        if not seed_matches:
            # No seeds found -- return empty
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="graph_rag",
            )

        # Use top seeds (max 3 to avoid over-expansion)
        top_seeds = [fp for fp, _ in seed_matches[:3]]

        # Step 2: BFS traverse
        # Dynamic max_hops based on graph density
        avg_degree = (
            sum(dict(self.graph.degree()).values()) / max(1, self.graph.number_of_nodes())
        )
        if avg_degree > 5:
            max_hops = 2  # Dense graph -> fewer hops
        else:
            max_hops = 3  # Sparse graph -> more hops

        graph_scores = self._bfs_traverse(top_seeds, max_hops=max_hops)

        # Combine seed match scores with graph traversal scores
        combined: Dict[str, float] = {}
        for fpath, g_score in graph_scores.items():
            seed_score = dict(seed_matches).get(fpath, 0.0)
            # Weighted combination: seed match + graph proximity
            combined[fpath] = seed_score * 0.4 + g_score * 0.6

        # Sort and take top-k
        sorted_files = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:k]
        retrieved = [f for f, _ in sorted_files]
        scores = {f: s for f, s in sorted_files}

        tokens_used = sum(estimate_tokens(self.files[f]) for f in retrieved if f in self.files)

        return RetrievalResult(
            query_id=query_id,
            retrieved_files=retrieved,
            scores=scores,
            tokens_used=tokens_used,
            total_tokens=self.total_tokens,
            strategy="graph_rag",
        )
