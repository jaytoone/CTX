"""Unit tests for _bm25 package-level re-exports.

Verifies that:
  - All names in __all__ are importable from the package root.
  - Key functions are callable after import.
  - Module-level state variables are intentionally NOT re-exported.
  - No circular import occurs when importing the package.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# Ensure the hooks directory is on sys.path (mirrors how bm25-memory.py operates).
_HOOKS_DIR = str(Path(__file__).parents[2] / "src" / "hooks")
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)


# ─── helpers ─────────────────────────────────────────────────────────


def _fresh_import(module_name: str):
    """Import (or re-import) a module, bypassing the cache.

    Forces a clean import to test that the package-level __init__ triggers
    no import-time errors on a cold load.
    """
    for key in list(sys.modules.keys()):
        if key == module_name or key.startswith(module_name + "."):
            del sys.modules[key]
    return importlib.import_module(module_name)


# ─── tests: basic importability ──────────────────────────────────────


def test_reexport_tokenize_callable():
    """tokenize must be importable and callable from package root."""
    from _bm25 import tokenize
    assert callable(tokenize), "tokenize must be callable"
    result = tokenize("hello world")
    assert isinstance(result, list)


def test_reexport_score_corpus_bm25_callable():
    """score_corpus_bm25 must be importable and callable from package root."""
    from _bm25 import score_corpus_bm25
    assert callable(score_corpus_bm25), "score_corpus_bm25 must be callable"


def test_reexport_bm25_rank_decisions_callable():
    """bm25_rank_decisions must be importable and callable."""
    from _bm25 import bm25_rank_decisions
    assert callable(bm25_rank_decisions)


# ─── tests: __all__ completeness ────────────────────────────────────


def test_reexport_all_listed_functions():
    """Every name in __all__ must be importable from _bm25 and be callable."""
    import _bm25
    assert hasattr(_bm25, "__all__"), "_bm25 must define __all__"
    assert len(_bm25.__all__) > 0, "__all__ must be non-empty"

    for name in _bm25.__all__:
        obj = getattr(_bm25, name, None)
        assert obj is not None, f"_bm25.{name} is listed in __all__ but not present"
        assert callable(obj), f"_bm25.{name} is listed in __all__ but not callable"


# ─── tests: no circular import ───────────────────────────────────────


def test_no_circular_import():
    """Importing _bm25 must not raise ImportError or RecursionError."""
    try:
        _fresh_import("_bm25")
    except (ImportError, RecursionError) as exc:
        pytest.fail(f"Circular or broken import detected: {exc}")


def test_package_loads_without_exception_on_cold_import():
    """Cold import of _bm25 must succeed without side-effect exceptions."""
    mod = _fresh_import("_bm25")
    assert mod is not None


# ─── tests: module-level state NOT re-exported ───────────────────────


def test_auto_tune_not_reexported():
    """AUTO_TUNE must NOT be accessible directly from _bm25 package root.

    Reason: AUTO_TUNE is a module-level dict in autotune.py that is populated
    at import time by reading a file.  Re-exporting it creates confusing
    binding semantics — callers must use the submodule path.
    """
    import _bm25
    assert not hasattr(_bm25, "AUTO_TUNE"), (
        "AUTO_TUNE must not be re-exported from _bm25; use 'from _bm25.autotune import AUTO_TUNE'"
    )


def test_auto_tune_active_not_reexported():
    """AUTO_TUNE_ACTIVE must NOT be accessible directly from _bm25."""
    import _bm25
    assert not hasattr(_bm25, "AUTO_TUNE_ACTIVE"), (
        "AUTO_TUNE_ACTIVE must not be re-exported from _bm25"
    )


def test_last_retrieval_scores_not_reexported():
    """last_retrieval_scores (ranker module state) must NOT be re-exported.

    It is a mutable module-level dict used for inter-module telemetry.
    Exporting it by name would create a confusing secondary reference.
    """
    import _bm25
    assert not hasattr(_bm25, "last_retrieval_scores"), (
        "last_retrieval_scores must not be re-exported; use 'from _bm25.ranker import last_retrieval_scores'"
    )


# ─── tests: submodule imports still work ────────────────────────────


def test_submodule_import_still_works():
    """Original submodule-path imports must remain functional (no regression)."""
    from _bm25.tokenizer import tokenize, expand_query_tokens  # noqa: F401
    from _bm25.ranker import score_corpus_bm25, rrf_merge  # noqa: F401
    from _bm25.corpus import get_decision_corpus  # noqa: F401
    from _bm25.output import emit_output  # noqa: F401
