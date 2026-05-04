"""
hooks_search.py — G2-HOOKS ~/.claude/hooks/*.py BM25 search for bm25-memory.

Provides:
  _build_hook_doc(py_path) -> str
  search_hooks_files(query, limit=3) -> list[tuple[Path, float]]
  _has_hooks_keywords(prompt) -> bool
"""
from pathlib import Path

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    BM25Okapi = None  # type: ignore
    _HAS_BM25 = False

from .tokenizer import tokenize

# ── Hooks dir config ─────────────────────────────────────────────────────────

_HOOKS_DIR = Path.home() / ".claude" / "hooks"
_HOOKS_TRIGGER_KWS = frozenset({
    # English
    "hook", "hooks", "bm25-memory", "bm25_memory", "git-memory", "git_memory",
    "auto-index", "auto_index", "g2-augment", "g2_augment",
    "userPromptSubmit", "sessionstart", "posttooluse",
    # Korean
    "훅", "후크",
})


def _build_hook_doc(py_path: Path) -> str:
    """Extract file name + docstring + function/class signatures from a hook file."""
    try:
        src = py_path.read_text(errors="replace")
    except Exception:
        return ""
    lines = src.split("\n")
    header_lines = []
    in_docstring = False
    docstring_done = False
    for line in lines[:80]:
        stripped = line.strip()
        if not docstring_done:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                header_lines.append(stripped[:200])
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    in_docstring = False
                    docstring_done = True
                continue
            if in_docstring:
                header_lines.append(stripped[:200])
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                    docstring_done = True
                continue
            else:
                docstring_done = True
        if stripped.startswith("def ") or stripped.startswith("class "):
            header_lines.append(stripped[:120])
    return f"{py_path.name}\n" + "\n".join(header_lines)


def search_hooks_files(query: str, limit: int = 3):
    """BM25-search ~/.claude/hooks/*.py for hook function/filename matches."""
    if not _HOOKS_DIR.exists() or not _HAS_BM25:
        return []
    py_files = sorted(_HOOKS_DIR.glob("*.py"))
    if not py_files:
        return []
    docs = [(p, _build_hook_doc(p)) for p in py_files]
    docs = [(p, d) for p, d in docs if d]
    if not docs:
        return []
    tokenized = [tokenize(d) for _, d in docs]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    return [(docs[i][0], scores[i]) for i in ranked[:limit] if scores[i] > 0]


def _has_hooks_keywords(prompt: str) -> bool:
    """Return True if prompt mentions hook-related terms."""
    low = prompt.lower()
    return any(kw in low for kw in _HOOKS_TRIGGER_KWS)
