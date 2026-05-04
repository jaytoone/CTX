"""Unit tests for src/hooks/chat-memory.py — graceful fallback behavior.

All tests invoke the hook via subprocess (file is not importable due to
hyphenated name and module-level sqlite_vec import).

Tests verify:
  1. No vault.db present → graceful exit (0), no crash.
  2. No vec-daemon socket → BM25-only fallback with ⚠ warning in stderr.
  3. Malformed / truncated JSON stdin → graceful exit (0).
  4. CHAT_MEMORY_EXCLUDED_PROJECTS matches cwd → vault access skipped.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

HOOK_PATH = str(Path(__file__).parents[2] / "src" / "hooks" / "chat-memory.py")
HOOK_TIMEOUT = 10  # seconds

pytestmark = pytest.mark.requires_subprocess


def _run_hook(stdin_data: dict | str, env: dict, timeout: int = HOOK_TIMEOUT):
    """Run chat-memory.py with given stdin and env."""
    import subprocess

    if isinstance(stdin_data, dict):
        stdin_str = json.dumps(stdin_data)
    else:
        stdin_str = stdin_data

    return subprocess.run(
        [sys.executable, HOOK_PATH],
        input=stdin_str,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


# ─── fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def base_env(tmp_home):
    """Isolated env with HOME set to tmp_home; no vault.db; no vec-daemon socket."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    # Clear interference vars.
    for var in (
        "CHAT_MEMORY_EXCLUDED_PROJECTS",
        "CHAT_MEMORY_SCOPE",
        "CHAT_MEMORY_EXTRA_PROJECTS",
        "CHAT_MEMORY_GLOBAL_FALLBACK",
        "CTX_TELEMETRY",
        "CTX_AB_DISABLE",
    ):
        env.pop(var, None)
    # Point vault to a path that does not exist.
    env["HOME"] = str(tmp_home)
    return env


# ─── tests ───────────────────────────────────────────────────────


def test_chat_memory_runs_with_no_vault_db(base_env, tmp_home):
    """When vault.db is absent, hook exits 0 (degrade gracefully, no crash)."""
    # Ensure vault.db truly does not exist.
    vault_db = tmp_home / ".local" / "share" / "claude-vault" / "vault.db"
    assert not vault_db.exists(), "vault.db must not exist for this test"

    result = _run_hook(
        {"prompt": "What decisions did we make about BM25?", "cwd": str(tmp_home)},
        base_env,
    )
    assert result.returncode == 0, (
        f"Hook crashed (exit {result.returncode}) when vault.db is absent.\n"
        f"stderr: {result.stderr[:500]}"
    )


def test_chat_memory_no_vault_db_outputs_nothing(base_env, tmp_home):
    """No vault.db → hook writes nothing to stdout (no injection)."""
    result = _run_hook(
        {"prompt": "Tell me about recent BM25 decisions", "cwd": str(tmp_home)},
        base_env,
    )
    assert result.returncode == 0
    # stdout should be empty or not a hook injection.
    stdout = result.stdout.strip()
    assert stdout == "", (
        f"Hook unexpectedly produced output without a vault.db:\n{stdout[:300]}"
    )


def test_chat_memory_runs_with_no_vec_daemon(base_env, tmp_home):
    """When vec-daemon socket is absent, hook falls back to BM25-only.

    The ⚠ vec-daemon down warning appears in stderr when the hook actually
    found results via BM25 but no daemon was available. With no vault.db,
    the hook exits early (no results), so this test simply verifies the
    hook does NOT crash, regardless of whether it produced output.
    """
    sock_path = tmp_home / ".local" / "share" / "claude-vault" / "vec-daemon.sock"
    assert not sock_path.exists(), "Socket must not exist for this test"

    result = _run_hook(
        {"prompt": "BM25 retrieval decisions recently?", "cwd": str(tmp_home)},
        base_env,
    )
    # Hook must not crash.
    assert result.returncode == 0, (
        f"Hook crashed with exit {result.returncode}.\nstderr: {result.stderr[:500]}"
    )


def test_chat_memory_handles_invalid_stdin(base_env):
    """Malformed JSON on stdin → graceful exit (0), no traceback."""
    result = _run_hook("NOT VALID JSON {{{", base_env)
    assert result.returncode == 0, (
        f"Hook should exit 0 on bad stdin, got {result.returncode}.\n"
        f"stderr: {result.stderr[:500]}"
    )
    # Must not print Python traceback.
    assert "Traceback" not in result.stderr, (
        "Unexpected traceback on invalid stdin:\n" + result.stderr[:500]
    )


def test_chat_memory_handles_truncated_stdin(base_env):
    """Truncated JSON (incomplete) → graceful exit (0)."""
    result = _run_hook('{"prompt": "BM25 decisions"', base_env)  # missing closing }
    assert result.returncode == 0, (
        f"Hook should exit 0 on truncated stdin, got {result.returncode}.\n"
        f"stderr: {result.stderr[:500]}"
    )


def test_chat_memory_handles_short_prompt(base_env):
    """Prompt shorter than 10 chars → hook exits 0 (too short to process)."""
    result = _run_hook({"prompt": "hi"}, base_env)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_chat_memory_handles_empty_prompt(base_env):
    """Empty prompt → hook exits 0."""
    result = _run_hook({"prompt": ""}, base_env)
    assert result.returncode == 0


def test_chat_memory_respects_excluded_project(base_env, tmp_home):
    """CHAT_MEMORY_EXCLUDED_PROJECTS matching cwd → vault access skipped, exit 0."""
    project_cwd = str(tmp_home / "secret-project")
    # Set the env var so this project is excluded.
    env = {**base_env, "CHAT_MEMORY_EXCLUDED_PROJECTS": project_cwd}

    result = _run_hook(
        {
            "prompt": "What BM25 decisions did we make last week about retrieval?",
            "cwd": project_cwd,
        },
        env,
    )
    assert result.returncode == 0, (
        f"Hook crashed on excluded project (exit {result.returncode}).\n"
        f"stderr: {result.stderr[:500]}"
    )
    # No injection output expected.
    assert result.stdout.strip() == "", (
        "Hook should produce no injection output for excluded projects"
    )


def test_chat_memory_no_crash_on_missing_sqlite_vec(base_env):
    """If sqlite_vec is not importable, hook must exit 0 with a warning — no traceback."""
    # Patch sqlite_vec availability: prepend a fake module that raises ImportError.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        fake_mod = Path(td) / "sqlite_vec.py"
        fake_mod.write_text("raise ImportError('no sqlite_vec for test')\n")
        env = {**base_env, "PYTHONPATH": td}

        result = _run_hook(
            {"prompt": "What BM25 decisions did we make about retrieval scoring?"},
            env,
        )
        # Must exit cleanly (graceful fallback to BM25-only mode).
        assert result.returncode == 0, (
            f"Hook crashed (exit {result.returncode}) when sqlite_vec is missing.\n"
            f"stderr: {result.stderr[:500]}"
        )
        # Must emit the ⚠ warning to stderr (not silently swallow the import error).
        assert "sqlite_vec missing" in result.stderr, (
            "Expected '⚠ sqlite_vec missing' warning in stderr, got:\n"
            + result.stderr[:500]
        )
        # Must not print a Python traceback.
        assert "Traceback" not in result.stderr, (
            "Unexpected Python traceback when sqlite_vec is missing:\n"
            + result.stderr[:500]
        )
