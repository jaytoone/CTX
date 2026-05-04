"""test_code_search_sort.py — deterministic sort guarantee for search_files_by_grep.

Verifies that search_files_by_grep() returns results in (-count, path) order:
  1. Higher-count files rank first.
  2. Ties are broken by lexicographic path order.
  3. Repeated calls with identical input produce identical output.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure src package is importable regardless of PYTHONPATH
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT / "src" / "hooks"))

from _bm25.code_search import search_files_by_grep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_grep_stdout(entries: list[tuple[str, int]]) -> str:
    """Build fake `git grep -c` stdout from (path, count) pairs."""
    return "\n".join(f"{path}:{count}" for path, count in entries) + "\n"


def _run_with_mock_grep(entries: list[tuple[str, int]], keywords: list[str], limit: int = 5) -> list[str]:
    """Run search_files_by_grep with mocked subprocess output."""
    fake_stdout = _make_grep_stdout(entries)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = fake_stdout

    with patch("subprocess.run", return_value=mock_result):
        return search_files_by_grep("/fake/project", keywords, limit=limit)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchFilesByGrepSort:
    """search_files_by_grep returns deterministic (-count, path) order."""

    def test_higher_count_ranks_first(self):
        """Files with more matches appear before files with fewer matches."""
        entries = [
            ("src/retrieval/adaptive_trigger.py", 3),
            ("src/hooks/bm25-memory.py", 10),
            ("tests/unit/test_bm25.py", 1),
        ]
        result = _run_with_mock_grep(entries, ["bm25"])
        assert result[0] == "src/hooks/bm25-memory.py"
        assert result[1] == "src/retrieval/adaptive_trigger.py"
        assert result[2] == "tests/unit/test_bm25.py"

    def test_ties_broken_by_path_lexicographic(self):
        """When two files have the same count, alphabetically earlier path ranks first."""
        entries = [
            ("src/zoo.py", 5),
            ("src/alpha.py", 5),
            ("src/middle.py", 5),
        ]
        result = _run_with_mock_grep(entries, ["bm25"])
        assert result == ["src/alpha.py", "src/middle.py", "src/zoo.py"]

    def test_mixed_count_and_tie(self):
        """Combined: primary sort by count desc, secondary by path asc."""
        entries = [
            ("b/high2.py", 10),
            ("a/high1.py", 10),
            ("c/low.py", 2),
            ("a/mid.py", 5),
        ]
        result = _run_with_mock_grep(entries, ["search"], limit=10)
        assert result[0] == "a/high1.py"   # count=10, alpha first
        assert result[1] == "b/high2.py"   # count=10, alpha second
        assert result[2] == "a/mid.py"     # count=5
        assert result[3] == "c/low.py"     # count=2

    def test_deterministic_repeated_calls(self):
        """Five consecutive calls with the same input return the same result."""
        entries = [
            ("src/z_file.py", 4),
            ("src/a_file.py", 4),
            ("src/m_file.py", 7),
            ("src/b_file.py", 4),
        ]
        first = _run_with_mock_grep(entries, ["token"])
        for _ in range(4):
            subsequent = _run_with_mock_grep(entries, ["token"])
            assert subsequent == first, "Results must be identical across calls"

    def test_limit_respected(self):
        """Result length does not exceed the requested limit."""
        entries = [(f"src/file{i}.py", i) for i in range(1, 11)]
        result = _run_with_mock_grep(entries, ["bm25"], limit=3)
        assert len(result) == 3

    def test_empty_grep_returns_empty(self):
        """If grep returns nothing, result is an empty list."""
        mock_result = MagicMock()
        mock_result.returncode = 1  # non-zero → no matches
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = search_files_by_grep("/fake/project", ["bm25"])
        assert result == []

    def test_short_keywords_filtered(self):
        """Keywords shorter than 4 chars are ignored (long_kws filter)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run") as mock_run:
            result = search_files_by_grep("/fake/project", ["ab", "x"])
            # subprocess.run should NOT be called because no long keywords
            mock_run.assert_not_called()
        assert result == []
