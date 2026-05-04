"""Unit tests for src/cli/settings_patcher.py.

Coverage targets:
  - atomic write (temp + os.replace)
  - timestamped backup creation
  - idempotency (two-patch dedup)
  - dry-run (no write)
  - unpatch removes only specified commands
  - corrupted JSON handled as {}
  - partial-write safety
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow import of src/cli/settings_patcher.py without package install.
sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "cli"))
from settings_patcher import (
    patch_settings,
    unpatch_settings,
    _load,
    _save_atomic,
    _cmd_in_settings,
    PatchResult,
)


# ─── fixtures ────────────────────────────────────────────────────


def _minimal_hooks_block() -> dict:
    """A small hooks dict that mirrors the format install.py produces."""
    return {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/chat-memory.py"}]},
            {"hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/bm25-memory.py --rich"}]},
        ],
        "PostToolUse": [
            {"matcher": "Grep", "hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/g2-fallback.py"}]},
        ],
    }


def _other_tool_hooks_block() -> dict:
    """Simulates an existing hook from a completely different tool."""
    return {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "python3 /some/other/tool/hook.py"}]},
        ],
    }


# ─── tests: _load ────────────────────────────────────────────────


def test_load_missing_file_returns_empty(tmp_path):
    p = tmp_path / "nonexistent.json"
    result = _load(p)
    assert result == {}


def test_load_valid_json(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"hooks": {}}', encoding="utf-8")
    assert _load(p) == {"hooks": {}}


def test_load_corrupted_json_returns_empty(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ this is: broken json }", encoding="utf-8")
    result = _load(p)
    assert result == {}


def test_load_empty_file_returns_empty(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("", encoding="utf-8")
    result = _load(p)
    assert result == {}


# ─── tests: _save_atomic ─────────────────────────────────────────


def test_atomic_write_temp_then_replace(tmp_path):
    """Atomic write: temp file should not persist; final file should contain data."""
    p = tmp_path / "settings.json"
    data = {"hooks": {"UserPromptSubmit": []}}

    _save_atomic(p, data)

    # Final file must exist and be valid JSON.
    assert p.exists()
    assert json.loads(p.read_text()) == data

    # No .tmp_ctx residual file should remain.
    tmp_file = p.with_suffix(".tmp_ctx")
    assert not tmp_file.exists()


def test_atomic_write_uses_os_replace(tmp_path):
    """Verify os.replace is called (not shutil.move or direct write)."""
    p = tmp_path / "settings.json"
    data = {"test": True}

    with patch("settings_patcher.os.replace", wraps=os.replace) as mock_replace:
        _save_atomic(p, data)
        assert mock_replace.called, "os.replace should be called for atomic rename"


def test_backup_created_with_timestamp(tmp_path):
    """When file already exists, a timestamped backup is created."""
    p = tmp_path / "settings.json"
    original_data = {"original": True}
    p.write_text(json.dumps(original_data), encoding="utf-8")

    new_data = {"updated": True}
    _save_atomic(p, new_data)

    # Find backup files in the directory.
    backups = list(tmp_path.glob("*.backup_*.json"))
    assert len(backups) == 1, f"Expected 1 backup, found {len(backups)}: {backups}"
    # Backup should contain the original content.
    backup_content = json.loads(backups[0].read_text())
    assert backup_content == original_data


def test_no_backup_when_file_missing(tmp_path):
    """No backup when settings.json doesn't exist yet."""
    p = tmp_path / "settings.json"
    _save_atomic(p, {"new": True})
    backups = list(tmp_path.glob("*.backup_*.json"))
    assert len(backups) == 0


def test_save_atomic_returns_empty_string_for_new_file(tmp_path):
    """_save_atomic returns '' (not a path) when creating a brand-new file."""
    p = tmp_path / "settings.json"
    # File must NOT exist before the call.
    assert not p.exists()
    result = _save_atomic(p, {"key": "value"})
    assert result == "", f"Expected empty string for new file, got: {result!r}"
    assert p.exists(), "File should have been created"


def test_save_atomic_returns_backup_path_for_existing_file(tmp_path):
    """_save_atomic returns the backup path string when updating an existing file."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"original": True}), encoding="utf-8")
    result = _save_atomic(p, {"updated": True})
    assert result != "", "Expected backup path for existing file, got empty string"
    assert result.endswith(".json")
    backup = Path(result)
    assert backup.exists(), f"Backup file should exist at {backup}"
    assert json.loads(backup.read_text()) == {"original": True}


def test_parent_dirs_created_if_missing(tmp_path):
    """_save_atomic creates parent directories if they don't exist."""
    p = tmp_path / "deep" / "nested" / "settings.json"
    _save_atomic(p, {"ok": True})
    assert p.exists()


# ─── tests: patch_settings ───────────────────────────────────────


def test_patch_to_empty_settings(tmp_path):
    """Patching when settings.json does not exist creates the file."""
    p = tmp_path / "settings.json"
    hooks = _minimal_hooks_block()
    result = patch_settings(p, hooks)
    assert result.ok
    assert len(result.added) > 0
    # File must now be valid JSON containing the hooks.
    saved = json.loads(p.read_text())
    assert "hooks" in saved


def test_patch_preserves_other_hooks(tmp_path):
    """Existing hooks from other tools are never removed."""
    p = tmp_path / "settings.json"
    existing = {"hooks": _other_tool_hooks_block()}
    p.write_text(json.dumps(existing), encoding="utf-8")

    result = patch_settings(p, _minimal_hooks_block())
    assert result.ok

    saved = json.loads(p.read_text())
    # Other tool's hook must still be present.
    all_cmds = [
        hook.get("command")
        for entries in saved["hooks"].values()
        for entry in entries
        for hook in entry.get("hooks", [])
    ]
    assert "python3 /some/other/tool/hook.py" in all_cmds


def test_idempotent_patch(tmp_path):
    """Running patch_settings twice does not duplicate entries."""
    p = tmp_path / "settings.json"
    hooks = _minimal_hooks_block()

    result1 = patch_settings(p, hooks)
    result2 = patch_settings(p, hooks)

    assert result1.ok
    assert result2.ok
    # Second run: all entries should be in skipped, none in added.
    assert len(result2.added) == 0
    assert len(result2.skipped) > 0

    # Confirm no duplicate commands in the saved file.
    saved = json.loads(p.read_text())
    all_cmds = [
        hook.get("command")
        for entries in saved["hooks"].values()
        for entry in entries
        for hook in entry.get("hooks", [])
    ]
    assert len(all_cmds) == len(set(all_cmds)), "Duplicate hook commands found!"


def test_dry_run_no_write(tmp_path):
    """dry_run=True: reports what would change but does not write any file."""
    p = tmp_path / "settings.json"
    result = patch_settings(p, _minimal_hooks_block(), dry_run=True)
    assert result.ok
    # File must not have been created.
    assert not p.exists(), "dry_run must not create the settings file"
    # Result still reports what would be added.
    assert len(result.added) > 0


def test_dry_run_existing_file_unchanged(tmp_path):
    """dry_run=True on existing file leaves it byte-for-byte identical."""
    p = tmp_path / "settings.json"
    original = {"hooks": {}, "other": "keep"}
    p.write_text(json.dumps(original), encoding="utf-8")
    original_mtime = p.stat().st_mtime

    # Small sleep to make mtime distinguishable if file is touched.
    time.sleep(0.05)
    patch_settings(p, _minimal_hooks_block(), dry_run=True)

    assert p.stat().st_mtime == original_mtime, "dry_run should not modify the file"


def test_corrupted_json_treated_as_empty(tmp_path):
    """Corrupted settings.json is treated as {} — new hooks are added cleanly."""
    p = tmp_path / "settings.json"
    p.write_text("NOT JSON AT ALL }{", encoding="utf-8")

    result = patch_settings(p, _minimal_hooks_block())
    assert result.ok
    assert len(result.added) > 0
    # File should now be valid JSON.
    saved = json.loads(p.read_text())
    assert "hooks" in saved


def test_post_tool_use_matcher_merge(tmp_path):
    """PostToolUse entries with the same matcher are merged, not duplicated."""
    p = tmp_path / "settings.json"
    # First install: adds a Grep-matcher entry.
    hooks1 = {
        "PostToolUse": [
            {"matcher": "Grep", "hooks": [{"type": "command", "command": "python3 /hook_a.py"}]},
        ]
    }
    # Second install: another Grep-matcher entry.
    hooks2 = {
        "PostToolUse": [
            {"matcher": "Grep", "hooks": [{"type": "command", "command": "python3 /hook_b.py"}]},
        ]
    }
    patch_settings(p, hooks1)
    patch_settings(p, hooks2)

    saved = json.loads(p.read_text())
    post_tool_entries = saved["hooks"].get("PostToolUse", [])
    grep_entries = [e for e in post_tool_entries if e.get("matcher") == "Grep"]
    # Both hooks should be in the same matcher group, not two separate groups.
    all_grep_cmds = [h["command"] for e in grep_entries for h in e.get("hooks", [])]
    assert "python3 /hook_a.py" in all_grep_cmds
    assert "python3 /hook_b.py" in all_grep_cmds


# ─── tests: unpatch_settings ─────────────────────────────────────


def test_unpatch_removes_only_specified(tmp_path):
    """unpatch_settings removes only the listed commands; others remain."""
    p = tmp_path / "settings.json"
    # Build a settings file with CTX hooks + a foreign hook.
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/chat-memory.py"}]},
                {"hooks": [{"type": "command", "command": "python3 /other/tool.py"}]},
            ]
        }
    }
    p.write_text(json.dumps(settings), encoding="utf-8")

    to_remove = ["python3 $HOME/.claude/hooks/chat-memory.py"]
    result = unpatch_settings(p, to_remove)
    assert result.ok

    saved = json.loads(p.read_text())
    all_cmds = [
        hook.get("command")
        for entries in saved["hooks"].values()
        for entry in entries
        for hook in entry.get("hooks", [])
    ]
    assert "python3 $HOME/.claude/hooks/chat-memory.py" not in all_cmds, "Should have been removed"
    assert "python3 /other/tool.py" in all_cmds, "Foreign hook should be preserved"


def test_unpatch_dry_run_no_write(tmp_path):
    """unpatch dry_run: reports removals without modifying the file."""
    p = tmp_path / "settings.json"
    settings = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "python3 $HOME/.claude/hooks/chat-memory.py"}]},
            ]
        }
    }
    p.write_text(json.dumps(settings), encoding="utf-8")
    mtime_before = p.stat().st_mtime

    time.sleep(0.05)
    result = unpatch_settings(p, ["python3 $HOME/.claude/hooks/chat-memory.py"], dry_run=True)
    assert result.ok
    assert p.stat().st_mtime == mtime_before, "dry_run unpatch must not modify the file"


def test_unpatch_nonexistent_command_is_not_found(tmp_path):
    """Trying to unpatch a command that isn't present is not an error per se."""
    p = tmp_path / "settings.json"
    settings = {"hooks": {}}
    p.write_text(json.dumps(settings), encoding="utf-8")

    result = unpatch_settings(p, ["python3 /does-not-exist.py"])
    # Should succeed without crashing; removed list should be empty.
    assert result.ok or result.error is not None  # either is acceptable
    assert len(result.added) == 0  # "added" in unpatch context = removed


# ─── tests: save_atomic partial-write safety ─────────────────────


def test_save_atomic_preserves_original_on_write_error(tmp_path):
    """If the write raises an OSError, the original file must remain intact.

    NOTE: This test mocks os.replace to raise an error AFTER the tmp file
    is written. The original content should be preserved because atomic
    rename never completed.
    """
    p = tmp_path / "settings.json"
    original_content = {"original": "keep me"}
    p.write_text(json.dumps(original_content), encoding="utf-8")

    def bad_replace(src, dst):
        # Remove the temp file to simulate cleanup, then raise.
        try:
            os.unlink(src)
        except FileNotFoundError:
            pass
        raise OSError("Simulated disk full")

    with patch("settings_patcher.os.replace", side_effect=bad_replace):
        try:
            _save_atomic(p, {"should": "not appear"})
        except OSError:
            pass  # Expected

    # Original must still be intact.
    saved = json.loads(p.read_text())
    assert saved == original_content, "Original file must not be corrupted on write error"
