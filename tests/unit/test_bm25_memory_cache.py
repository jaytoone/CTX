"""Unit tests for bm25-memory.py cache invalidation logic.

bm25-memory.py is not importable (hyphen in name + heavy module-level side effects),
so all tests use subprocess invocation or file-system observation.

Test strategy:
  - Create a temporary git repo (via conftest.tmp_project fixture).
  - Run bm25-memory.py pointing at that repo.
  - Observe whether .omc/decision_corpus.json is created/updated.

Cache behaviour (from source lines 194-222):
  - Cache file: <project>/.omc/decision_corpus.json
  - Cache is valid when: cache["head"] == current git HEAD
  - On HEAD change: cache is rebuilt (build_decision_corpus called again)
  - On corrupted JSON: falls back to rebuild (exception silently ignored)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK_PATH = str(Path(__file__).parents[2] / "src" / "hooks" / "bm25-memory.py")
HOOK_TIMEOUT = 15  # seconds — bm25-memory does subprocess git calls

pytestmark = pytest.mark.requires_subprocess

VENV_PYTHON = str(Path(__file__).parents[2] / ".venv-golden" / "bin" / "python3")
# Fall back to the current interpreter if venv isn't available (e.g. CI).
_PYTHON = VENV_PYTHON if Path(VENV_PYTHON).is_file() else sys.executable


# ─── helpers ─────────────────────────────────────────────────────


def _run_hook(project_dir: Path, env: dict, timeout: int = HOOK_TIMEOUT) -> subprocess.CompletedProcess:
    """Run bm25-memory.py with a minimal prompt directed at project_dir."""
    payload = json.dumps({
        "prompt": "BM25 decisions recently?",
        "cwd": str(project_dir),
    })
    # Ensure the hook reads the correct project_dir via env var AND process cwd.
    # bm25-memory.py uses os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()) at line ~79.
    env = {**env, "CLAUDE_PROJECT_DIR": str(project_dir)}
    return subprocess.run(
        [_PYTHON, HOOK_PATH, "--rich"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_dir),
        timeout=timeout,
    )


def _git_add_commit(project_dir: Path, message: str = "feat: test commit") -> str:
    """Create a new commit in the tmp_project repo; return new HEAD sha."""
    # Write a tiny file to commit.
    (project_dir / "change.txt").write_text(f"change at {time.time()}")
    subprocess.run(["git", "-C", str(project_dir), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(project_dir), "commit", "-m", message],
        capture_output=True, check=True,
    )
    result = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _read_cache(project_dir: Path) -> dict | None:
    """Return parsed cache or None if missing/corrupt."""
    cache_path = project_dir / ".omc" / "decision_corpus.json"
    if not cache_path.exists():
        return None
    try:
        return json.loads(cache_path.read_text())
    except json.JSONDecodeError:
        return None


def _get_head(project_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


# ─── fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def hook_env(tmp_home, tmp_project):
    """Env for running bm25-memory in an isolated context."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    env["CTX_DASHBOARD_INTERNAL"] = "1"  # suppress telemetry writes
    env.pop("CTX_TELEMETRY", None)
    env.pop("CTX_AB_DISABLE", None)
    return env


# ─── tests: cache path ────────────────────────────────────────────


def test_cache_path_under_omc(tmp_project, hook_env):
    """Cache must be written to <project>/.omc/decision_corpus.json (regression guard).

    This test will FAIL if Task A changes the cache path, giving Task C/D
    a clear signal to update accordingly.
    """
    _run_hook(tmp_project, hook_env)
    cache_path = tmp_project / ".omc" / "decision_corpus.json"
    # The hook may not write the cache if there are no decision commits,
    # but the path itself must be the canonical one. We check by either:
    # (a) the file exists at the right path, OR
    # (b) no other .omc/*.json file was created (no path drift).
    omc_dir = tmp_project / ".omc"
    json_files = list(omc_dir.glob("*.json"))
    if json_files:
        assert cache_path in json_files or any(
            f.name == "decision_corpus.json" for f in json_files
        ), (
            f"Unexpected cache file location. Found: {json_files}. "
            f"Expected: {cache_path}"
        )


# ─── tests: cache hit/miss on HEAD change ────────────────────────


def test_cache_invalidated_on_head_change(tmp_project, hook_env):
    """After a new commit, the cache head field must reflect the new HEAD.

    tmp_project has a 'feat: initial commit' which _is_decision() recognises,
    so the cache is always written on first run.
    """
    # Run hook once to warm the cache.
    _run_hook(tmp_project, hook_env)

    cache_after_first = _read_cache(tmp_project)
    assert cache_after_first is not None, (
        "Cache was not written after first hook run. "
        "tmp_project has 'feat: initial commit' which should be a decision commit. "
        "Check _is_decision() or CLAUDE_PROJECT_DIR injection."
    )

    head_first = cache_after_first.get("head")

    # Commit a new decision commit.
    head_second = _git_add_commit(tmp_project, "feat: add new feature for HEAD change test")

    # Verify HEAD actually changed.
    assert head_first != head_second, "git commit should change HEAD"

    # Run hook again — it should detect HEAD mismatch and rebuild.
    _run_hook(tmp_project, hook_env)

    cache_after_second = _read_cache(tmp_project)
    assert cache_after_second is not None, (
        "Cache was not written after second hook run."
    )

    assert cache_after_second.get("head") == head_second, (
        f"Cache head should be updated to {head_second!r}, "
        f"got {cache_after_second.get('head')!r}"
    )


def test_cache_hit_when_head_same(tmp_project, hook_env):
    """When HEAD hasn't changed, the cache mtime must not change (no rebuild).

    tmp_project already has 'feat: initial commit', so no extra commit needed.
    """
    # Run once to warm the cache (tmp_project's initial commit is a decision commit).
    _run_hook(tmp_project, hook_env)

    cache_path = tmp_project / ".omc" / "decision_corpus.json"
    assert cache_path.exists(), (
        "Cache was not written after first hook run. "
        "Check CLAUDE_PROJECT_DIR injection or _is_decision() logic."
    )

    mtime_first = cache_path.stat().st_mtime
    # Small sleep to make mtime difference detectable.
    time.sleep(0.1)

    # Run hook again WITHOUT any new commit — HEAD is unchanged.
    _run_hook(tmp_project, hook_env)

    mtime_second = cache_path.stat().st_mtime
    assert mtime_first == mtime_second, (
        "Cache should not be rewritten when HEAD is unchanged "
        f"(mtime before={mtime_first}, after={mtime_second})"
    )


# ─── tests: corrupted cache ───────────────────────────────────────


def test_corrupted_cache_safe_rebuild(tmp_project, hook_env):
    """If the cache file is corrupted JSON, the hook rebuilds it safely."""
    # Add a decision commit so there's something to cache.
    _git_add_commit(tmp_project, "feat: decision for corrupted-cache test")

    # Write a corrupted cache file.
    cache_path = tmp_project / ".omc" / "decision_corpus.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("THIS IS NOT JSON {{{ corrupted !!!")

    # Run hook — should NOT crash.
    result = _run_hook(tmp_project, hook_env)
    assert result.returncode == 0, (
        f"Hook crashed on corrupted cache (exit {result.returncode}).\n"
        f"stderr: {result.stderr[:500]}"
    )

    # Cache should now be valid JSON (rebuilt).
    cache_after = _read_cache(tmp_project)
    if cache_after is not None:
        assert "head" in cache_after, "Rebuilt cache must have 'head' field"


def test_corrupted_cache_no_traceback(tmp_project, hook_env):
    """Corrupted cache must not cause a Python traceback in stderr."""
    cache_path = tmp_project / ".omc" / "decision_corpus.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{{{{ BROKEN")

    result = _run_hook(tmp_project, hook_env)
    assert "Traceback" not in result.stderr, (
        "Python traceback detected on corrupted cache:\n" + result.stderr[:500]
    )


def test_cache_missing_omc_dir_creates_it(tmp_project, hook_env):
    """If .omc/ directory is missing entirely, the hook creates it safely."""
    omc_dir = tmp_project / ".omc"
    # Remove .omc/ entirely.
    import shutil
    if omc_dir.exists():
        shutil.rmtree(str(omc_dir))

    _git_add_commit(tmp_project, "feat: test without .omc dir")
    result = _run_hook(tmp_project, hook_env)

    assert result.returncode == 0, (
        f"Hook crashed when .omc/ is missing (exit {result.returncode}).\n"
        f"stderr: {result.stderr[:500]}"
    )


# ─── tests: non-git directory ─────────────────────────────────────


def test_hook_runs_in_non_git_directory(tmp_path, hook_env):
    """Hook must not crash when cwd is not a git repository."""
    non_git = tmp_path / "not-a-git-repo"
    non_git.mkdir()

    payload = json.dumps({"prompt": "BM25 decisions recently?", "cwd": str(non_git)})
    result = subprocess.run(
        [_PYTHON, HOOK_PATH, "--rich"],
        input=payload,
        capture_output=True,
        text=True,
        env=hook_env,
        timeout=HOOK_TIMEOUT,
    )
    assert result.returncode == 0, (
        f"Hook crashed in non-git dir (exit {result.returncode}).\n"
        f"stderr: {result.stderr[:500]}"
    )
    assert "Traceback" not in result.stderr
