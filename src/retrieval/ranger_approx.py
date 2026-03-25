"""
RANGER-approx: AST-based call graph retrieval.

Approximates RANGER (2025) using Python ast module:
- Precise symbol extraction via AST (vs regex)
- Call graph construction (function-level call edges)
- Combined import + call graph BFS traversal

Reference: RANGER: Retrieval-Augmented Generation with
           Enhanced Repository-level Graph Extraction (2025)

Key differences from CTX:
- No trigger classification (uniform graph traversal for all queries)
- AST-based symbol extraction (vs regex in CTX)
- Combined import + call graph (vs import-only in CTX)
- Fixed traversal depth (no adaptive-k)
"""

import ast
import os
import re
from collections import deque
from typing import Dict, List, Set, Tuple

import networkx as nx

from src.retrieval.full_context import RetrievalResult, estimate_tokens


def _tokenize_simple(text: str) -> List[str]:
    """Simple tokenizer for query matching."""
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
    return [t for t in tokens if len(t) > 1]


def extract_ast_symbols(content: str, filepath: str = "") -> Dict:
    """Extract functions, classes, calls, and imports via AST.

    Falls back to regex if AST parsing fails (e.g., SyntaxError).

    Args:
        content: Python source code
        filepath: File path (for error reporting)

    Returns:
        Dict with keys: defs, calls, imports
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _extract_symbols_regex(content)

    defs = []
    calls = []
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs.append(node.name)
            # Extract calls within this function body
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.append(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.append(child.func.attr)
        elif isinstance(node, ast.ClassDef):
            defs.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return {
        "defs": list(set(defs)),
        "calls": list(set(calls)),
        "imports": imports,
    }


def _extract_symbols_regex(content: str) -> Dict:
    """Regex fallback for symbol extraction when AST fails."""
    defs = []
    calls = []
    imports = []

    # Functions and classes
    for match in re.finditer(r'(?:^|\n)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
        defs.append(match.group(1))
    for match in re.finditer(r'(?:^|\n)class\s+([A-Z][a-zA-Z0-9_]*)', content):
        defs.append(match.group(1))

    # Calls (simple heuristic)
    for match in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
        name = match.group(1)
        if name not in ('def', 'class', 'if', 'for', 'while', 'with', 'print',
                         'return', 'import', 'from', 'raise', 'except', 'isinstance',
                         'type', 'len', 'range', 'str', 'int', 'float', 'list', 'dict',
                         'set', 'tuple', 'bool', 'super', 'hasattr', 'getattr'):
            calls.append(name)

    # Imports (synthetic format and real)
    for match in re.finditer(r'#\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
        imports.append(match.group(1))
    for match in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
        imports.append(match.group(1))
    for match in re.finditer(r'^from\s+([\w.]+)\s+import', content, re.MULTILINE):
        imports.append(match.group(1))

    return {
        "defs": list(set(defs)),
        "calls": list(set(calls)),
        "imports": imports,
    }


class RANGERApproxRetriever:
    """RANGER-approx: AST-based call+import graph retrieval.

    Unlike CTX which classifies triggers and routes to specialized
    strategies, RANGER-approx applies uniform graph traversal to
    all queries using a combined import + call graph.

    The retrieval pipeline:
    1. Build AST-based symbol index and call graph at init time
    2. For each query, find seed files by symbol/keyword matching
    3. BFS over combined (import + call) graph from seeds
    4. Return top-k by graph proximity score
    """

    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self.files: Dict[str, str] = {}
        self.file_paths: List[str] = []
        self.total_tokens = 0

        # AST-extracted indices
        self.symbol_index: Dict[str, List[str]] = {}  # symbol_name -> [file_paths]
        self.file_symbols: Dict[str, Dict] = {}  # file -> {defs, calls, imports}

        # Combined graph (import + call edges)
        self.graph = nx.DiGraph()
        self.module_to_file: Dict[str, str] = {}
        self.symbol_to_file: Dict[str, List[str]] = {}  # def_name -> [files]

        self._index()

    def _index(self) -> None:
        """Build AST-based indices and combined graph."""
        # Pass 1: Extract symbols from all files
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

                    # AST symbol extraction
                    info = extract_ast_symbols(content, rel_path)
                    self.file_symbols[rel_path] = info

                    # Build symbol-to-file mapping
                    for sym in info["defs"]:
                        self.symbol_to_file.setdefault(sym, []).append(rel_path)
                        self.symbol_index.setdefault(sym, []).append(rel_path)

                    # Extract module name
                    mod_name = self._extract_module_name(rel_path, content)
                    self.module_to_file[mod_name] = rel_path

                    self.graph.add_node(rel_path)

        # Pass 2: Build combined import + call graph edges
        self._build_combined_graph()

    def _extract_module_name(self, rel_path: str, content: str) -> str:
        """Extract module name from MODULE_NAME constant or path."""
        mod_match = re.search(r'MODULE_NAME\s*=\s*"([^"]+)"', content)
        if mod_match:
            return mod_match.group(1)
        return os.path.splitext(os.path.basename(rel_path))[0]

    def _build_combined_graph(self) -> None:
        """Build combined import + call graph.

        Edge types:
        - Import edge: file A imports module defined in file B
        - Call edge: file A calls a function defined in file B
        """
        for rel_path, info in self.file_symbols.items():
            # Import edges
            for imp_mod in info["imports"]:
                # Try direct module name match
                target = self.module_to_file.get(imp_mod)
                if target and target != rel_path:
                    self.graph.add_edge(rel_path, target)
                    continue

                # Try last component of dotted import
                parts = imp_mod.split(".")
                for part in reversed(parts):
                    target = self.module_to_file.get(part)
                    if target and target != rel_path:
                        self.graph.add_edge(rel_path, target)
                        break

                # Try synthetic import format
                for match_mod, match_file in self.module_to_file.items():
                    if imp_mod in match_mod or match_mod in imp_mod:
                        if match_file != rel_path:
                            self.graph.add_edge(rel_path, match_file)

            # Call edges: if file A calls symbol X defined in file B
            for call_name in info["calls"]:
                target_files = self.symbol_to_file.get(call_name, [])
                for target in target_files:
                    if target != rel_path:
                        self.graph.add_edge(rel_path, target)

    def _find_seed_files(self, query_text: str) -> List[Tuple[str, float]]:
        """Find seed files for BFS via AST symbol matching.

        RANGER uses precise AST-based matching rather than fuzzy text search.

        Args:
            query_text: The query string

        Returns:
            List of (file_path, score) sorted by score descending
        """
        matched: Dict[str, float] = {}
        query_tokens = _tokenize_simple(query_text)

        # 1. Exact AST symbol match (RANGER's primary strength)
        for token in query_tokens:
            if token in self.symbol_index:
                for fpath in self.symbol_index[token]:
                    matched[fpath] = max(matched.get(fpath, 0.0), 1.0)

        # 2. Partial symbol match
        for token in query_tokens:
            for sym_name, file_list in self.symbol_index.items():
                if token in sym_name.lower() or sym_name.lower() in token:
                    for fpath in file_list:
                        matched[fpath] = max(matched.get(fpath, 0.0), 0.7)

        # 3. Module name match
        for mod_name, fpath in self.module_to_file.items():
            if mod_name.lower() in query_text.lower():
                matched[fpath] = max(matched.get(fpath, 0.0), 0.9)

        # 4. Content keyword fallback
        if not matched:
            for fpath, content in self.files.items():
                content_lower = content.lower()
                hits = sum(1 for t in query_tokens if len(t) > 2 and t in content_lower)
                if hits > 0:
                    score = min(0.6, hits * 0.15)
                    matched[fpath] = max(matched.get(fpath, 0.0), score)

        return sorted(matched.items(), key=lambda x: x[1], reverse=True)

    def _bfs_traverse(self, seeds: List[str], max_hops: int = 3) -> Dict[str, float]:
        """BFS traversal on combined import+call graph.

        Unlike GraphRAG-lite which uses import-only edges, RANGER
        traverses both import and call edges for richer context.

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
            if seed in self.graph:
                queue.append((seed, 0))
                scores[seed] = 1.0
                visited.add(seed)

        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue

            # Traverse both directions (imports and imported-by, calls and called-by)
            neighbors = set()
            neighbors.update(self.graph.successors(node))
            neighbors.update(self.graph.predecessors(node))

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
        """Retrieve files using RANGER-approx graph traversal.

        Unlike CTX which classifies triggers and adapts strategy,
        RANGER applies uniform combined-graph BFS to all queries.

        Args:
            query_id: Query identifier
            query_text: The query text
            k: Number of files to return

        Returns:
            RetrievalResult with scored file list
        """
        # Step 1: Find seed files via AST symbol matching
        seed_matches = self._find_seed_files(query_text)

        if not seed_matches:
            return RetrievalResult(
                query_id=query_id,
                retrieved_files=[],
                scores={},
                tokens_used=0,
                total_tokens=self.total_tokens,
                strategy="ranger_approx",
            )

        # Use top seeds (max 3)
        top_seeds = [fp for fp, _ in seed_matches[:3]]

        # Step 2: BFS on combined import+call graph
        # RANGER uses fixed traversal depth (no adaptive k)
        max_hops = 3
        graph_scores = self._bfs_traverse(top_seeds, max_hops=max_hops)

        # Step 3: Combine seed + graph scores
        combined: Dict[str, float] = {}
        for fpath, g_score in graph_scores.items():
            seed_score = dict(seed_matches).get(fpath, 0.0)
            combined[fpath] = seed_score * 0.4 + g_score * 0.6

        # Step 4: Sort and return top-k
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
            strategy="ranger_approx",
        )
