"""Unit tests for --uninstall file cleanup logic.

Covers _cleanup_hook_files() and cmd_uninstall() in src/cli/install.py:
  - Normal uninstall: hook files and _bm25/ removed when hashes match.
  - User-modified file: kept (not removed) unless --force.
  - _bm25/ with extra files: kept unless --force.
  - --force: removes everything regardless of hash.
  - dry_run: nothing deleted.
  - not_found: missing files reported cleanly.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

# Make install.py importable without package install.
_CLI_DIR = str(Path(__file__).parents[2] / "src" / "cli")
if _CLI_DIR not in sys.path:
    sys.path.insert(0, _CLI_DIR)

import install as _install


# ─── helpers ─────────────────────────────────────────────────────────


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, content: bytes = b"# hook content") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _make_args(**kwargs) -> SimpleNamespace:
    defaults = {"dry_run": False, "force": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _override_hooks_dir(monkeypatch, tmp_home: Path):
    """Redirect CLAUDE_HOOKS_DIR to an isolated tmp location."""
    hooks_dir = tmp_home / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_install, "CLAUDE_HOOKS_DIR", hooks_dir)
    monkeypatch.setattr(_install, "CLAUDE_SETTINGS", tmp_home / ".claude" / "settings.json")
    return hooks_dir


# ─── tests: _cleanup_hook_files ──────────────────────────────────────


def test_cleanup_removes_matching_files(tmp_path, monkeypatch):
    """Files with matching hash against package source are removed."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)

    # Write a hook file whose content matches what we'll pretend is the source.
    content = b"# canonical hook\n"
    hook_file = hooks_dir / "chat-memory.py"
    _write(hook_file, content)

    # Build a fake package source directory with the same file.
    src_dir = tmp_path / "pkg_hooks"
    src_dir.mkdir()
    (src_dir / "chat-memory.py").write_bytes(content)

    # Redirect only the hook we care about for this test.
    monkeypatch.setattr(_install, "CTX_HOOKS", [
        ("chat-memory.py", "UserPromptSubmit", False),
    ])

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=False, dry_run=False)

    assert "chat-memory.py" in result["removed"], "Matching-hash file must be removed"
    assert not hook_file.exists(), "File must be deleted from disk"


def test_cleanup_keeps_user_modified_file(tmp_path, monkeypatch):
    """User-modified files (hash mismatch) must NOT be deleted when force=False."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)

    original_content = b"# original hook\n"
    modified_content = b"# user modified this\n"

    hook_file = hooks_dir / "chat-memory.py"
    _write(hook_file, modified_content)

    src_dir = tmp_path / "pkg_hooks"
    src_dir.mkdir()
    (src_dir / "chat-memory.py").write_bytes(original_content)

    monkeypatch.setattr(_install, "CTX_HOOKS", [
        ("chat-memory.py", "UserPromptSubmit", False),
    ])

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=False, dry_run=False)

    assert "chat-memory.py" in result["kept"], "Modified file must be kept"
    assert hook_file.exists(), "Modified file must not be deleted"
    assert "chat-memory.py" not in result["removed"]


def test_cleanup_force_removes_modified_file(tmp_path, monkeypatch):
    """--force removes user-modified files without hash check."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)

    hook_file = hooks_dir / "chat-memory.py"
    _write(hook_file, b"# user modified\n")

    src_dir = tmp_path / "pkg_hooks"
    src_dir.mkdir()
    (src_dir / "chat-memory.py").write_bytes(b"# original\n")

    monkeypatch.setattr(_install, "CTX_HOOKS", [
        ("chat-memory.py", "UserPromptSubmit", False),
    ])

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=True, dry_run=False)

    assert "chat-memory.py" in result["removed"]
    assert not hook_file.exists(), "--force must delete even user-modified files"


def test_cleanup_dry_run_does_not_delete(tmp_path, monkeypatch):
    """dry_run=True must not actually delete any files."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)

    content = b"# hook\n"
    hook_file = hooks_dir / "chat-memory.py"
    _write(hook_file, content)

    src_dir = tmp_path / "pkg_hooks"
    src_dir.mkdir()
    (src_dir / "chat-memory.py").write_bytes(content)

    monkeypatch.setattr(_install, "CTX_HOOKS", [
        ("chat-memory.py", "UserPromptSubmit", False),
    ])

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=False, dry_run=True)

    # Reported as removed but file must still exist.
    assert "chat-memory.py" in result["removed"]
    assert hook_file.exists(), "dry_run must not delete files"


def test_cleanup_not_found_reported(tmp_path, monkeypatch):
    """Missing files are reported in 'not_found', not 'removed' or 'kept'."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)
    # Do not create any hook file.
    monkeypatch.setattr(_install, "CTX_HOOKS", [
        ("chat-memory.py", "UserPromptSubmit", False),
    ])

    src_dir = tmp_path / "pkg_hooks"
    src_dir.mkdir()

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=False, dry_run=False)

    assert "chat-memory.py" in result["not_found"]
    assert "chat-memory.py" not in result["removed"]


def test_cleanup_bm25_dir_removed_when_clean(tmp_path, monkeypatch):
    """_bm25/ directory is removed when all files match package source."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(_install, "CTX_HOOKS", [])

    content = b"# bm25 module\n"
    bm25_dst = hooks_dir / "_bm25"
    bm25_dst.mkdir()
    (bm25_dst / "tokenizer.py").write_bytes(content)

    src_dir = tmp_path / "pkg_hooks"
    src_bm25 = src_dir / "_bm25"
    src_bm25.mkdir(parents=True)
    (src_bm25 / "tokenizer.py").write_bytes(content)

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=False, dry_run=False)

    assert "_bm25/" in result["removed"]
    assert not bm25_dst.exists(), "_bm25/ must be deleted when all files match"


def test_cleanup_bm25_dir_kept_when_extra_files(tmp_path, monkeypatch):
    """_bm25/ with extra files (not from CTX) is kept when force=False."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(_install, "CTX_HOOKS", [])

    content = b"# bm25 module\n"
    bm25_dst = hooks_dir / "_bm25"
    bm25_dst.mkdir()
    (bm25_dst / "tokenizer.py").write_bytes(content)
    (bm25_dst / "user_extra.py").write_bytes(b"# user added this\n")

    src_dir = tmp_path / "pkg_hooks"
    src_bm25 = src_dir / "_bm25"
    src_bm25.mkdir(parents=True)
    (src_bm25 / "tokenizer.py").write_bytes(content)

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=False, dry_run=False)

    assert "_bm25/" in result["kept"], "_bm25/ with extra files must be kept"
    assert bm25_dst.exists(), "_bm25/ must not be deleted when it has extra files"


def test_cleanup_bm25_dir_force_removes_with_extra_files(tmp_path, monkeypatch):
    """--force removes _bm25/ even when extra files exist."""
    hooks_dir = _override_hooks_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(_install, "CTX_HOOKS", [])

    bm25_dst = hooks_dir / "_bm25"
    bm25_dst.mkdir()
    (bm25_dst / "user_extra.py").write_bytes(b"# user file\n")

    src_dir = tmp_path / "pkg_hooks"
    src_bm25 = src_dir / "_bm25"
    src_bm25.mkdir(parents=True)

    with patch.object(_install, "_pkg_hooks_dir", return_value=src_dir):
        result = _install._cleanup_hook_files(force=True, dry_run=False)

    assert "_bm25/" in result["removed"]
    assert not bm25_dst.exists(), "--force must remove _bm25/ unconditionally"


# ─── tests: cmd_uninstall integration ────────────────────────────────


def test_cmd_uninstall_calls_cleanup(tmp_path, monkeypatch):
    """cmd_uninstall must call _cleanup_hook_files (integration smoke test)."""
    _override_hooks_dir(monkeypatch, tmp_path)

    # Mock unpatch_settings to succeed immediately.
    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.summary.return_value = "  removed 0 command(s)"

    with (
        patch.object(_install, "unpatch_settings", return_value=mock_result),
        patch.object(_install, "_cleanup_hook_files", return_value={
            "removed": [], "kept": [], "not_found": [],
        }) as mock_cleanup,
    ):
        args = _make_args()
        ret = _install.cmd_uninstall(args)

    assert ret == 0
    mock_cleanup.assert_called_once_with(force=False, dry_run=False)


def test_cmd_uninstall_force_flag_passed(tmp_path, monkeypatch):
    """--force flag is forwarded to _cleanup_hook_files."""
    _override_hooks_dir(monkeypatch, tmp_path)

    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.summary.return_value = "  removed 0"

    with (
        patch.object(_install, "unpatch_settings", return_value=mock_result),
        patch.object(_install, "_cleanup_hook_files", return_value={
            "removed": [], "kept": [], "not_found": [],
        }) as mock_cleanup,
    ):
        args = _make_args(force=True)
        ret = _install.cmd_uninstall(args)

    assert ret == 0
    mock_cleanup.assert_called_once_with(force=True, dry_run=False)
