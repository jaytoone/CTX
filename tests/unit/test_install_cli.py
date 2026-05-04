"""Unit tests for src/cli/install.py.

Coverage targets:
  - _new_hooks_block() produces correct event/matcher structure
  - UserPromptSubmit hooks all present
  - PostToolUse has Grep matcher for g2-fallback
  - --dry-run flag: no file changes
  - Install to empty/missing settings.json
  - Install merges with pre-existing hooks from other tools
  - Idempotent install (two runs, no duplicate entries)
  - Uninstall removes only CTX hooks
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Allow import without package install.
sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "cli"))
import install as install_mod
from install import _new_hooks_block, _hook_entry, CTX_HOOKS
from settings_patcher import patch_settings, unpatch_settings


# ─── helpers ─────────────────────────────────────────────────────


def _all_commands_in_block(block: dict) -> list[str]:
    """Flatten all command strings from a hooks block."""
    cmds = []
    for entries in block.values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if cmd:
                    cmds.append(cmd)
    return cmds


def _all_commands_in_settings(settings: dict) -> list[str]:
    return _all_commands_in_block(settings.get("hooks", {}))


# ─── tests: _new_hooks_block ─────────────────────────────────────


def test_new_hooks_block_includes_all_required():
    """All 5 CTX hooks must appear in _new_hooks_block()."""
    block = _new_hooks_block()
    cmds = _all_commands_in_block(block)
    # Every hook filename from CTX_HOOKS must appear in some command.
    for spec in CTX_HOOKS:
        fname = spec[0]
        assert any(fname in cmd for cmd in cmds), (
            f"Hook '{fname}' missing from _new_hooks_block()"
        )


def test_new_hooks_block_user_prompt_submit_events():
    """UserPromptSubmit entries must cover chat-memory, bm25-memory, memory-keyword-trigger."""
    block = _new_hooks_block()
    ups_entries = block.get("UserPromptSubmit", [])
    ups_cmds = [
        hook["command"]
        for entry in ups_entries
        for hook in entry.get("hooks", [])
    ]
    for fname in ["chat-memory.py", "bm25-memory.py", "memory-keyword-trigger.py"]:
        assert any(fname in cmd for cmd in ups_cmds), (
            f"'{fname}' missing from UserPromptSubmit entries"
        )


def test_new_hooks_block_post_tool_use_grep_matcher():
    """g2-fallback.py must be registered under PostToolUse with matcher='Grep'."""
    block = _new_hooks_block()
    post_entries = block.get("PostToolUse", [])
    grep_entries = [e for e in post_entries if e.get("matcher") == "Grep"]
    assert len(grep_entries) > 0, "No Grep matcher entry in PostToolUse"

    grep_cmds = [
        hook["command"]
        for entry in grep_entries
        for hook in entry.get("hooks", [])
    ]
    assert any("g2-fallback.py" in cmd for cmd in grep_cmds), (
        "g2-fallback.py not found in Grep matcher group"
    )


def test_new_hooks_block_bm25_includes_rich_flag():
    """bm25-memory.py command must include the '--rich' argument."""
    block = _new_hooks_block()
    cmds = _all_commands_in_block(block)
    bm25_cmds = [c for c in cmds if "bm25-memory.py" in c]
    assert len(bm25_cmds) > 0
    assert any("--rich" in cmd for cmd in bm25_cmds), (
        "bm25-memory.py must include '--rich' flag"
    )


def test_hook_entry_command_format():
    """_hook_entry returns dict with correct 'type' and 'command' keys."""
    entry = _hook_entry("chat-memory.py")
    assert entry["type"] == "command"
    assert "chat-memory.py" in entry["command"]
    assert "$HOME/.claude/hooks/" in entry["command"]


def test_hook_entry_with_extra_args():
    """_hook_entry with extra_args appends them to the command."""
    entry = _hook_entry("bm25-memory.py", ["--rich"])
    assert "--rich" in entry["command"]


# ─── tests: install to empty/missing settings ─────────────────────


def test_install_to_empty_settings(tmp_path):
    """patch_settings on a non-existent file creates it with all CTX hooks."""
    settings_file = tmp_path / "settings.json"
    block = _new_hooks_block()
    result = patch_settings(settings_file, block)
    assert result.ok
    assert len(result.added) > 0
    saved = json.loads(settings_file.read_text())
    cmds = _all_commands_in_settings(saved)
    for spec in CTX_HOOKS:
        fname = spec[0]
        assert any(fname in cmd for cmd in cmds), f"'{fname}' missing from saved settings"


def test_install_merges_with_existing_hooks(tmp_path):
    """Install should preserve hooks from other tools already in settings.json."""
    settings_file = tmp_path / "settings.json"
    existing = {
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "python3 /other/foreign-hook.py"}]}
            ]
        }
    }
    settings_file.write_text(json.dumps(existing), encoding="utf-8")

    block = _new_hooks_block()
    result = patch_settings(settings_file, block)
    assert result.ok

    saved = json.loads(settings_file.read_text())
    cmds = _all_commands_in_settings(saved)
    assert "python3 /other/foreign-hook.py" in cmds, "Foreign hook must be preserved"
    # CTX hooks must also be present.
    for spec in CTX_HOOKS:
        fname = spec[0]
        assert any(fname in cmd for cmd in cmds), f"'{fname}' missing after merge"


def test_install_idempotent(tmp_path):
    """Running patch_settings twice produces no duplicate commands."""
    settings_file = tmp_path / "settings.json"
    block = _new_hooks_block()

    patch_settings(settings_file, block)  # first install
    result2 = patch_settings(settings_file, block)  # second install

    assert result2.ok
    assert len(result2.added) == 0, "Second install should add nothing"
    assert len(result2.skipped) > 0, "Second install should skip all CTX hooks"

    saved = json.loads(settings_file.read_text())
    cmds = _all_commands_in_settings(saved)
    assert len(cmds) == len(set(cmds)), "Duplicate commands detected after second install"


# ─── tests: dry_run flag via cmd_install ─────────────────────────


def test_dry_run_prints_summary_no_write(tmp_path):
    """cmd_install with --dry-run writes nothing but prints a summary."""
    settings_file = tmp_path / "settings.json"

    # Patch all step functions that touch the file system.
    with (
        patch.object(install_mod, "CLAUDE_SETTINGS", settings_file),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", tmp_path / ".claude" / "hooks"),
        patch("install.step_copy_hooks", return_value=(3, 0, 0, [])),
        patch("install.step_copy_daemons", return_value=(0, 0, [])),
        patch("install.step_verify_hooks_present", return_value=(True, ["chat-memory.py"], [])),
        patch("install.step_smoke_test", return_value=(True, "smoke OK")),
    ):
        import argparse
        args = argparse.Namespace(dry_run=True, uninstall=False, command=None,
                                  force_hooks=False, no_update_hooks=False)
        rc = install_mod.cmd_install(args)

    # Dry run always returns 0 and must not create the settings file.
    assert rc == 0
    assert not settings_file.exists(), "dry_run must not create settings.json"


# ─── tests: uninstall ─────────────────────────────────────────────


def test_uninstall_removes_ctx_hooks_only(tmp_path):
    """cmd_uninstall removes CTX-registered hooks and leaves foreign hooks intact."""
    settings_file = tmp_path / "settings.json"
    # Build a settings file with CTX hooks + a foreign hook.
    block = _new_hooks_block()
    settings = {"hooks": {}}
    for event, entries in block.items():
        settings["hooks"].setdefault(event, []).extend(entries)
    settings["hooks"].setdefault("UserPromptSubmit", []).append(
        {"hooks": [{"type": "command", "command": "python3 /foreign/tool.py"}]}
    )
    settings_file.write_text(json.dumps(settings), encoding="utf-8")

    # Build remove list the same way cmd_uninstall does.
    remove = []
    for spec in CTX_HOOKS:
        filename = spec[0]
        extra = spec[3] if len(spec) >= 4 else None
        remove.append(_hook_entry(filename, extra)["command"])

    result = unpatch_settings(settings_file, remove)
    assert result.ok

    saved = json.loads(settings_file.read_text())
    cmds = _all_commands_in_settings(saved)
    # Foreign hook must survive.
    assert "python3 /foreign/tool.py" in cmds
    # All CTX hooks must be gone.
    for cmd in remove:
        assert cmd not in cmds, f"CTX hook still present after uninstall: {cmd}"


# ─── tests: step functions ───────────────────────────────────────


def test_step_copy_hooks_no_package_returns_error():
    """step_copy_hooks returns (0, 0, 0, [error]) when package hooks dir not found."""
    with patch("install._pkg_hooks_dir", return_value=None):
        copied, updated, skipped, errors = install_mod.step_copy_hooks()
    assert copied == 0
    assert updated == 0
    assert skipped == 0
    assert len(errors) == 1
    assert "ctx-retriever" in errors[0].lower() or "not found" in errors[0].lower()


def test_step_copy_hooks_dry_run_counts_but_no_write(tmp_path):
    """step_copy_hooks with dry_run=True counts files but copies nothing."""
    # Create a fake source dir with a hook file.
    fake_src = tmp_path / "pkg_hooks"
    fake_src.mkdir()
    (fake_src / "chat-memory.py").write_text("# fake hook")

    fake_dst = tmp_path / "claude_hooks"
    fake_dst.mkdir()

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_dst),
    ):
        copied, updated, skipped, errors = install_mod.step_copy_hooks(dry_run=True)

    assert copied > 0
    assert errors == []
    # In dry_run, no file should exist in fake_dst.
    assert not (fake_dst / "chat-memory.py").exists()


def test_step_copy_hooks_skips_already_present(tmp_path):
    """step_copy_hooks with identical content reports unchanged (skipped) and does not copy."""
    fake_src = tmp_path / "pkg_hooks"
    fake_src.mkdir()
    content = "# fake bm25 — identical content"
    (fake_src / "bm25-memory.py").write_text(content)

    fake_dst = tmp_path / "claude_hooks"
    fake_dst.mkdir()
    # Pre-create the destination file with identical content (same hash → unchanged).
    (fake_dst / "bm25-memory.py").write_text(content)

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_dst),
    ):
        copied, updated, skipped, errors = install_mod.step_copy_hooks()

    assert skipped > 0
    assert copied == 0
    assert updated == 0


def test_step_copy_hooks_updates_changed_file(tmp_path):
    """step_copy_hooks updates an existing file when hash differs (creates backup)."""
    fake_src = tmp_path / "pkg_hooks"
    fake_src.mkdir()
    (fake_src / "bm25-memory.py").write_text("# NEW VERSION")

    fake_dst = tmp_path / "claude_hooks"
    fake_dst.mkdir()
    # Pre-create the destination file with different content.
    (fake_dst / "bm25-memory.py").write_text("# OLD VERSION")

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_dst),
    ):
        copied, updated, skipped, errors = install_mod.step_copy_hooks()

    assert updated > 0
    assert copied == 0
    assert errors == []
    # Destination should now have new content.
    assert (fake_dst / "bm25-memory.py").read_text() == "# NEW VERSION"
    # A backup should have been created.
    backups = list(fake_dst.glob("bm25-memory.backup_*.py"))
    assert len(backups) == 1
    assert backups[0].read_text() == "# OLD VERSION"


def test_step_copy_hooks_no_update_skips_changed(tmp_path):
    """--no-update-hooks skips even when hash differs."""
    fake_src = tmp_path / "pkg_hooks"
    fake_src.mkdir()
    (fake_src / "bm25-memory.py").write_text("# NEW VERSION")

    fake_dst = tmp_path / "claude_hooks"
    fake_dst.mkdir()
    (fake_dst / "bm25-memory.py").write_text("# OLD VERSION")

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_dst),
    ):
        copied, updated, skipped, errors = install_mod.step_copy_hooks(no_update=True)

    assert skipped > 0
    assert updated == 0
    # File must remain unchanged.
    assert (fake_dst / "bm25-memory.py").read_text() == "# OLD VERSION"


def test_step_copy_hooks_force_overwrites(tmp_path):
    """--force-hooks overwrites even when hash is identical."""
    fake_src = tmp_path / "pkg_hooks"
    fake_src.mkdir()
    content = "# same content"
    (fake_src / "bm25-memory.py").write_text(content)

    fake_dst = tmp_path / "claude_hooks"
    fake_dst.mkdir()
    (fake_dst / "bm25-memory.py").write_text(content)

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_dst),
    ):
        copied, updated, skipped, errors = install_mod.step_copy_hooks(force=True)

    # force=True → "updated" path even if hashes match
    assert updated > 0


def test_step_verify_hooks_present_detects_missing(tmp_path):
    """step_verify_hooks_present reports missing files correctly."""
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()
    # Put only ONE hook file; others will be missing.
    (fake_hooks / "chat-memory.py").write_text("# present")

    with patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks):
        ok, found, missing = install_mod.step_verify_hooks_present()

    assert not ok
    assert "chat-memory.py" in found
    assert len(missing) > 0


def test_step_verify_hooks_present_all_ok(tmp_path):
    """step_verify_hooks_present returns True when all hooks are in place."""
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()
    for spec in CTX_HOOKS:
        (fake_hooks / spec[0]).write_text("# stub")

    with patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks):
        ok, found, missing = install_mod.step_verify_hooks_present()

    assert ok
    assert missing == []


def test_step_smoke_test_missing_hook(tmp_path):
    """step_smoke_test returns False when bm25-memory.py is missing."""
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()
    # Deliberately do NOT create bm25-memory.py.

    with patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks):
        ok, msg = install_mod.step_smoke_test()

    assert not ok
    assert "missing" in msg.lower() or "bm25" in msg.lower()


def test_cmd_status_runs_without_crash(tmp_path, capsys):
    """cmd_status completes without raising; printed output is non-empty."""
    fake_settings = tmp_path / "settings.json"
    fake_settings.write_text(json.dumps({"hooks": {}}), encoding="utf-8")
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()
    fake_vault = tmp_path / "claude-vault"
    fake_vault.mkdir()

    with (
        patch.object(install_mod, "CLAUDE_SETTINGS", fake_settings),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks),
        patch.object(install_mod, "CLAUDE_VAULT_DIR", fake_vault),
    ):
        import argparse
        args = argparse.Namespace(dry_run=False, uninstall=False, command="status")
        rc = install_mod.cmd_status(args)

    assert rc == 0
    captured = capsys.readouterr()
    assert "status" in captured.out.lower() or "hooks" in captured.out.lower()


def test_cmd_uninstall_dry_run(tmp_path, capsys):
    """cmd_uninstall with --dry-run does not modify settings.json."""
    settings_file = tmp_path / "settings.json"
    block = _new_hooks_block()
    settings = {"hooks": {}}
    for event, entries in block.items():
        settings["hooks"].setdefault(event, []).extend(entries)
    settings_file.write_text(json.dumps(settings), encoding="utf-8")
    mtime_before = settings_file.stat().st_mtime

    import time; time.sleep(0.05)
    with patch.object(install_mod, "CLAUDE_SETTINGS", settings_file):
        import argparse
        args = argparse.Namespace(dry_run=True, uninstall=True, command=None)
        rc = install_mod.cmd_uninstall(args)

    assert rc == 0
    assert settings_file.stat().st_mtime == mtime_before


def test_step_copy_daemons_no_package():
    """step_copy_daemons returns (0, 0, []) when package hooks dir not found."""
    with patch("install._pkg_hooks_dir", return_value=None):
        copied, skipped, errors = install_mod.step_copy_daemons()
    assert copied == 0
    assert skipped == 0
    assert errors == []  # non-fatal: daemons are optional


def test_step_copy_daemons_dry_run(tmp_path):
    """step_copy_daemons with dry_run=True counts would-copy but doesn't write."""
    fake_src = tmp_path / "pkg"
    fake_src.mkdir()
    (fake_src / "vec-daemon.py").write_text("# fake vec-daemon")

    fake_vault = tmp_path / "claude-vault"
    fake_vault.mkdir()

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_VAULT_DIR", fake_vault),
    ):
        copied, skipped, errors = install_mod.step_copy_daemons(dry_run=True)

    assert copied > 0
    assert errors == []
    assert not (fake_vault / "vec-daemon.py").exists()


def test_step_copy_daemons_actual_copy(tmp_path):
    """step_copy_daemons actually copies daemon files when dry_run=False."""
    fake_src = tmp_path / "pkg"
    fake_src.mkdir()
    (fake_src / "vec-daemon.py").write_text("# fake vec-daemon")

    fake_vault = tmp_path / "claude-vault"
    fake_vault.mkdir()

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_VAULT_DIR", fake_vault),
    ):
        copied, skipped, errors = install_mod.step_copy_daemons(dry_run=False)

    assert copied > 0
    assert errors == []
    assert (fake_vault / "vec-daemon.py").exists()


def test_step_copy_daemons_skips_existing(tmp_path):
    """step_copy_daemons skips daemons that already exist in vault dir."""
    fake_src = tmp_path / "pkg"
    fake_src.mkdir()
    (fake_src / "vec-daemon.py").write_text("# new")

    fake_vault = tmp_path / "claude-vault"
    fake_vault.mkdir()
    (fake_vault / "vec-daemon.py").write_text("# already there")

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_VAULT_DIR", fake_vault),
    ):
        copied, skipped, errors = install_mod.step_copy_daemons()

    assert skipped > 0
    assert copied == 0


def test_step_copy_hooks_actual_copy(tmp_path):
    """step_copy_hooks copies a hook file and sets it executable."""
    fake_src = tmp_path / "pkg"
    fake_src.mkdir()
    (fake_src / "chat-memory.py").write_text("#!/usr/bin/env python3\n# hook")

    fake_dst = tmp_path / "hooks"
    fake_dst.mkdir()

    with (
        patch("install._pkg_hooks_dir", return_value=fake_src),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_dst),
    ):
        copied, updated, skipped, errors = install_mod.step_copy_hooks(dry_run=False)

    assert copied > 0
    assert errors == []
    dst_file = fake_dst / "chat-memory.py"
    assert dst_file.exists()
    # Check executable bit is set.
    assert dst_file.stat().st_mode & 0o111


def test_cmd_install_smoke_test_fail_returns_4(tmp_path, capsys):
    """cmd_install returns exit code 4 when smoke test fails."""
    settings_file = tmp_path / "settings.json"
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()
    fake_vault = tmp_path / "claude-vault"
    fake_vault.mkdir()

    with (
        patch.object(install_mod, "CLAUDE_SETTINGS", settings_file),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks),
        patch.object(install_mod, "CLAUDE_VAULT_DIR", fake_vault),
        patch("install.step_copy_hooks", return_value=(2, 0, 0, [])),
        patch("install.step_copy_daemons", return_value=(0, 0, [])),
        patch("install.step_verify_hooks_present", return_value=(True, list(spec[0] for spec in CTX_HOOKS), [])),
        patch("install.step_smoke_test", return_value=(False, "bm25-memory.py missing")),
    ):
        import argparse
        args = argparse.Namespace(dry_run=False, uninstall=False, command=None,
                                  force_hooks=False, no_update_hooks=False)
        rc = install_mod.cmd_install(args)

    assert rc == 4


def test_cmd_install_hook_copy_failure_returns_2(tmp_path, capsys):
    """cmd_install returns exit code 2 when hook copy errors out."""
    settings_file = tmp_path / "settings.json"
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()

    with (
        patch.object(install_mod, "CLAUDE_SETTINGS", settings_file),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks),
        patch("install.step_copy_hooks", return_value=(0, 0, 0, ["copy chat-memory.py: Permission denied"])),
        patch("install.step_copy_daemons", return_value=(0, 0, [])),
        patch("install.step_verify_hooks_present", return_value=(True, [], [])),
    ):
        import argparse
        args = argparse.Namespace(dry_run=False, uninstall=False, command=None,
                                  force_hooks=False, no_update_hooks=False)
        rc = install_mod.cmd_install(args)

    assert rc == 2


def test_cmd_install_missing_hooks_after_copy_returns_2(tmp_path, capsys):
    """cmd_install returns 2 when hooks are still missing after copy step."""
    settings_file = tmp_path / "settings.json"
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()

    with (
        patch.object(install_mod, "CLAUDE_SETTINGS", settings_file),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks),
        patch("install.step_copy_hooks", return_value=(0, 0, 0, [])),
        patch("install.step_copy_daemons", return_value=(0, 0, [])),
        patch("install.step_verify_hooks_present", return_value=(False, [], ["bm25-memory.py"])),
    ):
        import argparse
        args = argparse.Namespace(dry_run=False, uninstall=False, command=None,
                                  force_hooks=False, no_update_hooks=False)
        rc = install_mod.cmd_install(args)

    assert rc == 2


def test_cmd_install_success_returns_0(tmp_path, capsys):
    """cmd_install returns 0 on full success."""
    settings_file = tmp_path / "settings.json"
    fake_hooks = tmp_path / "hooks"
    fake_hooks.mkdir()

    with (
        patch.object(install_mod, "CLAUDE_SETTINGS", settings_file),
        patch.object(install_mod, "CLAUDE_HOOKS_DIR", fake_hooks),
        patch.object(install_mod, "CLAUDE_VAULT_DIR", tmp_path / "vault"),
        patch("install.step_copy_hooks", return_value=(5, 0, 0, [])),
        patch("install.step_copy_daemons", return_value=(2, 0, [])),
        patch("install.step_verify_hooks_present", return_value=(True, list(spec[0] for spec in CTX_HOOKS), [])),
        patch("install.step_smoke_test", return_value=(True, "hook fired OK")),
    ):
        import argparse
        args = argparse.Namespace(dry_run=False, uninstall=False, command=None,
                                  force_hooks=False, no_update_hooks=False)
        rc = install_mod.cmd_install(args)

    assert rc == 0
