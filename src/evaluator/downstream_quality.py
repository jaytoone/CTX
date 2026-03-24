"""
Downstream quality estimation for CTX experiment.

Estimates LLM answer quality without calling LLM APIs:

1. Context Completeness Score (CCS):
   Fraction of required symbols present in retrieved context.

2. Answer Supportability Score (ASS):
   Fraction of queries whose answer is supportable by the retrieved context.
"""

import ast
import os
import re
from typing import Dict, List, Set, Tuple

from src.evaluator.benchmark_runner import QueryResult, StrategyResult


def _extract_symbols_from_content(content: str) -> Set[str]:
    """Extract function and class names from Python source code."""
    symbols = set()
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.add(node.name)
            elif isinstance(node, ast.ClassDef):
                symbols.add(node.name)
    except SyntaxError:
        # Fallback to regex
        for m in re.finditer(r'(?:^|\n)def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', content):
            symbols.add(m.group(1))
        for m in re.finditer(r'(?:^|\n)class\s+([A-Z][a-zA-Z0-9_]*)', content):
            symbols.add(m.group(1))
    return symbols


def _load_file_content(codebase_dir: str, rel_path: str) -> str:
    """Load file content from codebase directory."""
    full_path = os.path.join(codebase_dir, rel_path)
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, FileNotFoundError):
        return ""


def context_completeness_score(
    retrieved_files: List[str],
    relevant_files: List[str],
    codebase_dir: str,
) -> float:
    """Compute Context Completeness Score (CCS).

    CCS = |retrieved_symbols intersection required_symbols| / |required_symbols|

    Measures what fraction of the symbols defined in ground-truth
    relevant files also appear in the retrieved context.

    Args:
        retrieved_files: Files retrieved by the strategy
        relevant_files: Ground-truth relevant files
        codebase_dir: Root directory of the codebase

    Returns:
        CCS score in [0.0, 1.0]
    """
    # Extract required symbols from relevant files
    required_symbols: Set[str] = set()
    for fpath in relevant_files:
        content = _load_file_content(codebase_dir, fpath)
        if content:
            required_symbols.update(_extract_symbols_from_content(content))

    if not required_symbols:
        return 1.0  # No symbols to match

    # Extract symbols present in retrieved context
    retrieved_symbols: Set[str] = set()
    for fpath in retrieved_files:
        content = _load_file_content(codebase_dir, fpath)
        if content:
            retrieved_symbols.update(_extract_symbols_from_content(content))

    return len(retrieved_symbols & required_symbols) / len(required_symbols)


def answer_supportability_score(
    query_text: str,
    retrieved_files: List[str],
    relevant_files: List[str],
    codebase_dir: str,
) -> float:
    """Compute Answer Supportability Score (ASS) for a single query.

    Heuristic: checks whether the key terms from the query and
    the symbols from relevant files are present in the retrieved context.

    Args:
        query_text: The query text
        retrieved_files: Files retrieved by the strategy
        relevant_files: Ground-truth relevant files
        codebase_dir: Root directory of the codebase

    Returns:
        Supportability score in [0.0, 1.0]
    """
    # Extract query keywords (non-stopword tokens)
    stopwords = {
        "find", "show", "the", "and", "for", "all", "code", "related",
        "to", "about", "what", "how", "does", "are", "is", "this",
        "that", "with", "from", "module", "modules", "needed", "fully",
        "understand", "definition", "implementation", "function", "class",
        "its", "we", "discussed", "previously", "show",
    }
    query_keywords = set()
    for word in re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', query_text.lower()):
        if word not in stopwords and len(word) > 2:
            query_keywords.add(word)

    if not query_keywords:
        return 1.0

    # Concatenate retrieved content
    retrieved_content = ""
    for fpath in retrieved_files:
        content = _load_file_content(codebase_dir, fpath)
        retrieved_content += " " + content.lower()

    # Check how many query keywords appear in retrieved content
    found = sum(1 for kw in query_keywords if kw in retrieved_content)
    keyword_coverage = found / len(query_keywords)

    # Also check if at least one relevant file is retrieved
    file_overlap = len(set(retrieved_files) & set(relevant_files)) > 0
    file_bonus = 0.3 if file_overlap else 0.0

    # Combined score (keyword coverage weighted + file bonus)
    score = min(1.0, keyword_coverage * 0.7 + file_bonus)
    return score


def compute_downstream_metrics(
    strategy_result: StrategyResult,
    codebase_dir: str,
) -> Dict[str, float]:
    """Compute CCS and ASS across all queries in a strategy result.

    Args:
        strategy_result: Results from running one strategy
        codebase_dir: Root directory of the codebase

    Returns:
        Dictionary with mean_ccs and mean_ass
    """
    ccs_scores = []
    ass_scores = []

    for qr in strategy_result.query_results:
        ccs = context_completeness_score(
            retrieved_files=qr.retrieved_files,
            relevant_files=qr.relevant_files,
            codebase_dir=codebase_dir,
        )
        ccs_scores.append(ccs)

        ass = answer_supportability_score(
            query_text=qr.query_text,
            retrieved_files=qr.retrieved_files,
            relevant_files=qr.relevant_files,
            codebase_dir=codebase_dir,
        )
        ass_scores.append(ass)

    mean_ccs = sum(ccs_scores) / len(ccs_scores) if ccs_scores else 0.0
    mean_ass = sum(ass_scores) / len(ass_scores) if ass_scores else 0.0

    return {
        "mean_ccs": mean_ccs,
        "mean_ass": mean_ass,
        "ccs_scores": ccs_scores,
        "ass_scores": ass_scores,
    }
