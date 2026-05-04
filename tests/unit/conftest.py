"""conftest.py — shared fixtures for CTX unit tests.

Fixtures:
  tmp_home        — isolated home directory (simulates ~/.claude/)
  tmp_project     — isolated project directory with .omc/ structure
  settings_path   — path to a writable settings.json inside tmp_home
  isolated_env    — os.environ copy with HOME overridden to tmp_home
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# ─── Core fixtures ───────────────────────────────────────────────


@pytest.fixture()
def tmp_home(tmp_path: Path) -> Path:
    """An isolated home directory with ~/.claude/ structure.

    Use this instead of the real HOME to avoid touching the user's actual
    ~/.claude/settings.json during tests.
    """
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "hooks").mkdir()
    return home


@pytest.fixture()
def settings_path(tmp_home: Path) -> Path:
    """Path to settings.json inside the isolated tmp_home (file does not exist yet)."""
    return tmp_home / ".claude" / "settings.json"


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """An isolated project directory with .omc/ structure.

    Used for bm25-memory cache tests: provides a git repo-like structure
    without touching the actual CTX working tree.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / ".omc").mkdir()

    # Initialise a minimal git repo so git commands don't fail.
    subprocess.run(["git", "init", str(project)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(project), "config", "user.email", "test@test.com"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "config", "user.name", "Test User"],
        capture_output=True, check=True,
    )
    # Create an initial commit so HEAD resolves.
    init_file = project / "README.md"
    init_file.write_text("# test repo")
    subprocess.run(["git", "-C", str(project), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(project), "commit", "-m", "feat: initial commit"],
        capture_output=True, check=True,
    )
    return project


@pytest.fixture()
def isolated_env(tmp_home: Path) -> dict:
    """A copy of os.environ with HOME set to the isolated tmp_home.

    Also clears variables that would make hooks touch the real system:
      - CHAT_MEMORY_EXCLUDED_PROJECTS
      - CTX_TELEMETRY / CTX_AB_DISABLE
    """
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    # Clear potentially interfering vars
    for var in (
        "CHAT_MEMORY_EXCLUDED_PROJECTS",
        "CHAT_MEMORY_SCOPE",
        "CHAT_MEMORY_EXTRA_PROJECTS",
        "CTX_TELEMETRY",
        "CTX_AB_DISABLE",
        "CTX_DISABLE_SEMANTIC_RERANK",
        "CHAT_MEMORY_GLOBAL_FALLBACK",
    ):
        env.pop(var, None)
    return env


# ─── Helper functions ─────────────────────────────────────────────


def run_hook(hook_path: str, stdin_data: dict, env: dict, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a hook script via subprocess with JSON stdin.

    Args:
        hook_path: Absolute path to the hook .py file.
        stdin_data: Dict that gets JSON-encoded as stdin.
        env: Environment variables dict (use `isolated_env` fixture).
        timeout: Max seconds to wait (default 10).

    Returns:
        CompletedProcess with stdout, stderr, returncode.
    """
    return subprocess.run(
        [sys.executable, hook_path],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
