"""
Real codebase loader for CTX experiment.

Loads actual Python projects from disk, extracts symbols via ast,
and generates ground-truth queries automatically.
"""

import ast
import hashlib
import os
import random
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class FileInfo:
    """Extracted information about a real Python file."""
    path: str
    module_name: str
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    imported_modules: List[str] = field(default_factory=list)
    docstring: str = ""
    line_count: int = 0
    concepts: List[str] = field(default_factory=list)


@dataclass
class RealQuery:
    """A test query generated from real codebase analysis."""
    id: str
    text: str
    trigger_type: str
    relevant_files: List[str]
    relevant_symbols: List[str] = field(default_factory=list)


def _stable_seed(project_path: str, seed: int) -> int:
    """Create a stable seed from project path + base seed."""
    h = hashlib.md5(project_path.encode()).hexdigest()
    return seed + int(h[:8], 16) % 10000


def _extract_file_info(file_path: str, rel_path: str) -> Optional[FileInfo]:
    """Extract functions, classes, imports from a Python file using ast."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    line_count = source.count("\n") + 1

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    functions = []
    classes = []
    imports = []
    imported_modules = []
    docstring = ""

    # Module docstring
    if (tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, (ast.Str, ast.Constant))):
        val = tree.body[0].value
        docstring = val.s if isinstance(val, ast.Str) else str(getattr(val, "value", ""))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                imported_modules.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
                imported_modules.append(node.module.split(".")[0])

    # Derive module name from path
    module_name = os.path.splitext(os.path.basename(rel_path))[0]

    # Extract concepts from docstring and function/class names
    concepts = _extract_concepts(docstring, functions, classes, module_name)

    return FileInfo(
        path=rel_path,
        module_name=module_name,
        functions=functions,
        classes=classes,
        imports=imports,
        imported_modules=list(set(imported_modules)),
        docstring=docstring[:500] if docstring else "",
        line_count=line_count,
        concepts=concepts,
    )


def _extract_concepts(docstring: str, functions: List[str], classes: List[str],
                       module_name: str) -> List[str]:
    """Extract semantic concepts from file metadata."""
    concepts = set()

    # From module name (split snake_case)
    for part in module_name.split("_"):
        if len(part) > 2:
            concepts.add(part.lower())

    # From function names
    for func in functions:
        for part in func.split("_"):
            if len(part) > 2 and part not in ("self", "cls", "init", "str", "repr", "get", "set"):
                concepts.add(part.lower())

    # From class names (split CamelCase)
    import re
    for cls in classes:
        parts = re.findall(r'[A-Z][a-z]+', cls)
        for part in parts:
            if len(part) > 2:
                concepts.add(part.lower())

    # From docstring keywords
    if docstring:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', docstring.lower())
        stopwords = {"the", "and", "for", "this", "that", "with", "from", "are", "was",
                     "has", "have", "not", "but", "can", "will", "all", "any", "each",
                     "def", "class", "return", "import", "none", "true", "false", "self"}
        for w in words[:20]:
            if w not in stopwords:
                concepts.add(w)

    return list(concepts)[:10]


class RealCodebaseLoader:
    """Loads real Python projects and generates ground-truth queries."""

    def __init__(self, project_path: str, seed: int = 42):
        self.project_path = os.path.abspath(project_path)
        self.seed = _stable_seed(project_path, seed)
        random.seed(self.seed)

        if not os.path.isdir(self.project_path):
            raise ValueError(f"Project path does not exist: {self.project_path}")

    def load(self) -> Dict:
        """Load the codebase and generate queries + ground truth.

        Returns:
            Dictionary compatible with DatasetGenerator.generate() output:
            {
                "size": "real",
                "file_count": int,
                "seed": int,
                "tier_distribution": {...},
                "files": [...],
                "queries": [...],
                "project_name": str,
                "codebase_dir": str,
            }
        """
        # Step 1: Scan and extract info from all .py files
        file_infos = self._scan_files()

        if not file_infos:
            raise ValueError(f"No Python files found in {self.project_path}")

        # Step 2: Assign tiers based on reference count
        self._assign_tiers(file_infos)

        # Step 3: Generate queries
        queries = self._generate_queries(file_infos)

        # Step 4: Build metadata
        tier_distribution = {
            "head": sum(1 for f in file_infos if f.get("tier") == "head"),
            "torso": sum(1 for f in file_infos if f.get("tier") == "torso"),
            "tail": sum(1 for f in file_infos if f.get("tier") == "tail"),
        }

        project_name = os.path.basename(self.project_path)

        metadata = {
            "size": "real",
            "file_count": len(file_infos),
            "seed": self.seed,
            "tier_distribution": tier_distribution,
            "files": file_infos,
            "queries": [asdict(q) for q in queries],
            "project_name": project_name,
            "codebase_dir": self.project_path,
        }

        return metadata

    def _scan_files(self) -> List[Dict]:
        """Scan all Python files and extract metadata."""
        file_infos = []

        for root, dirs, filenames in os.walk(self.project_path):
            # Skip common non-source directories
            dirs[:] = [d for d in dirs if d not in (
                "__pycache__", ".git", "node_modules", ".venv", "venv",
                "env", ".tox", ".eggs", "dist", "build", ".mypy_cache",
                ".pytest_cache",
            )]

            for fname in filenames:
                if not fname.endswith(".py"):
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.project_path)

                info = _extract_file_info(fpath, rel_path)
                if info is None:
                    continue
                if info.line_count < 3:
                    continue  # Skip near-empty files

                file_infos.append(asdict(info))

        return file_infos

    def _assign_tiers(self, file_infos: List[Dict]) -> None:
        """Assign head/torso/tail tiers based on import reference count."""
        # Count how often each module is imported by others
        module_to_path = {}
        for fi in file_infos:
            module_to_path[fi["module_name"]] = fi["path"]

        reference_counts = {fi["path"]: 0 for fi in file_infos}
        for fi in file_infos:
            for imp_mod in fi["imported_modules"]:
                if imp_mod in module_to_path:
                    ref_path = module_to_path[imp_mod]
                    reference_counts[ref_path] = reference_counts.get(ref_path, 0) + 1

        # Also count by import path matching
        for fi in file_infos:
            for imp in fi.get("imports", []):
                for other_fi in file_infos:
                    if other_fi["path"] != fi["path"]:
                        # Check if import matches the file path
                        mod_parts = imp.split(".")
                        path_parts = other_fi["path"].replace("/", ".").replace("\\", ".").replace(".py", "").split(".")
                        if mod_parts[-1] in path_parts:
                            reference_counts[other_fi["path"]] = reference_counts.get(other_fi["path"], 0) + 1

        # Sort by reference count and assign tiers
        sorted_by_refs = sorted(file_infos, key=lambda f: reference_counts.get(f["path"], 0), reverse=True)
        n = len(sorted_by_refs)
        head_cutoff = max(1, int(n * 0.2))
        torso_cutoff = max(head_cutoff + 1, int(n * 0.5))

        tier_map = {}
        for i, fi in enumerate(sorted_by_refs):
            if i < head_cutoff:
                tier_map[fi["path"]] = "head"
            elif i < torso_cutoff:
                tier_map[fi["path"]] = "torso"
            else:
                tier_map[fi["path"]] = "tail"

        for fi in file_infos:
            fi["tier"] = tier_map.get(fi["path"], "tail")
            fi["reference_count"] = reference_counts.get(fi["path"], 0)

    def _generate_queries(self, file_infos: List[Dict]) -> List[RealQuery]:
        """Generate ground-truth queries from real codebase analysis."""
        queries = []
        query_id = 0

        # Build lookup structures
        all_files_with_functions = [fi for fi in file_infos if fi["functions"]]
        all_files_with_classes = [fi for fi in file_infos if fi["classes"]]

        # Build import graph for IMPLICIT queries
        import_graph = {}
        module_to_path = {}
        for fi in file_infos:
            module_to_path[fi["module_name"]] = fi["path"]

        for fi in file_infos:
            deps = []
            for imp_mod in fi.get("imported_modules", []):
                if imp_mod in module_to_path:
                    deps.append(module_to_path[imp_mod])
            for imp in fi.get("imports", []):
                mod_parts = imp.split(".")
                for other in file_infos:
                    if other["path"] != fi["path"]:
                        path_parts = other["path"].replace("/", ".").replace("\\", ".").replace(".py", "").split(".")
                        if mod_parts[-1] in path_parts:
                            deps.append(other["path"])
            import_graph[fi["path"]] = list(set(deps))

        # 1. EXPLICIT_SYMBOL queries - ask about specific function/class names
        if all_files_with_functions:
            sample_size = min(30, len(all_files_with_functions))
            for fi in random.sample(all_files_with_functions, sample_size):
                func = random.choice(fi["functions"])
                # Skip dunder methods
                if func.startswith("__") and func.endswith("__"):
                    continue
                queries.append(RealQuery(
                    id=f"q_{query_id:04d}",
                    text=f"Find the function {func} and show its implementation",
                    trigger_type="EXPLICIT_SYMBOL",
                    relevant_files=[fi["path"]],
                    relevant_symbols=[func],
                ))
                query_id += 1

        if all_files_with_classes:
            sample_size = min(15, len(all_files_with_classes))
            for fi in random.sample(all_files_with_classes, sample_size):
                cls = random.choice(fi["classes"])
                queries.append(RealQuery(
                    id=f"q_{query_id:04d}",
                    text=f"Show the class {cls} definition",
                    trigger_type="EXPLICIT_SYMBOL",
                    relevant_files=[fi["path"]],
                    relevant_symbols=[cls],
                ))
                query_id += 1

        # 2. SEMANTIC_CONCEPT queries - ask about concepts
        concept_to_files: Dict[str, List[str]] = {}
        for fi in file_infos:
            for concept in fi.get("concepts", []):
                concept_to_files.setdefault(concept, []).append(fi["path"])

        # Pick concepts that appear in 2-10 files (interesting concepts)
        interesting_concepts = {
            c: files for c, files in concept_to_files.items()
            if 2 <= len(files) <= 10
        }
        if interesting_concepts:
            sample_size = min(20, len(interesting_concepts))
            for concept in random.sample(list(interesting_concepts.keys()), sample_size):
                files = interesting_concepts[concept]
                queries.append(RealQuery(
                    id=f"q_{query_id:04d}",
                    text=f"Find all code related to {concept}",
                    trigger_type="SEMANTIC_CONCEPT",
                    relevant_files=files,
                    relevant_symbols=[],
                ))
                query_id += 1

        # 3. TEMPORAL_HISTORY queries - simulated history references
        sample_size = min(10, len(file_infos))
        for fi in random.sample(file_infos, sample_size):
            topic = fi["concepts"][0] if fi["concepts"] else fi["module_name"]
            queries.append(RealQuery(
                id=f"q_{query_id:04d}",
                text=f"Show the module we discussed previously about {topic}",
                trigger_type="TEMPORAL_HISTORY",
                relevant_files=[fi["path"]],
                relevant_symbols=[],
            ))
            query_id += 1

        # 4. IMPLICIT_CONTEXT queries - based on import relationships
        files_with_deps = [fi for fi in file_infos if import_graph.get(fi["path"])]
        if files_with_deps:
            sample_size = min(15, len(files_with_deps))
            for fi in random.sample(files_with_deps, sample_size):
                deps = import_graph[fi["path"]]
                all_relevant = [fi["path"]] + deps
                queries.append(RealQuery(
                    id=f"q_{query_id:04d}",
                    text=f"What modules are needed to fully understand {fi['module_name']}?",
                    trigger_type="IMPLICIT_CONTEXT",
                    relevant_files=all_relevant,
                    relevant_symbols=[],
                ))
                query_id += 1

        return queries
