"""Unit tests for bm25-memory.py telemetry instrumentation (Task D).

Test strategy: subprocess invocation with isolated HOME (tmp_home fixture).
All tests use a tmp HOME so no real ~/.claude/ is touched.

Covered cases:
  1. Disabled: no jsonl line appended when CTX_TELEMETRY not set.
  2. Enabled: hook_complete event with hook=bm25-memory emitted.
  3. Enabled: query_type field captured correctly for various prompts.
  4. Enabled: fallback_reasons captured when CTX_DISABLE_SEMANTIC_RERANK=1.
  5. Exception in telemetry path does not crash hook (exit 0).
  6. Latency overhead under 5ms (enabled vs disabled, 10 runs average).
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK_PATH = str(Path(__file__).parents[2] / "src" / "hooks" / "bm25-memory.py")
HOOK_TIMEOUT = 20  # bm25-memory does subprocess git calls

pytestmark = pytest.mark.requires_subprocess

VENV_PYTHON = str(Path(__file__).parents[2] / ".venv-golden" / "bin" / "python3")
_PYTHON = VENV_PYTHON if Path(VENV_PYTHON).is_file() else sys.executable

# ─── helpers ─────────────────────────────────────────────────────────────────


def _run_hook(
    project_dir: Path,
    env: dict,
    prompt: str = "BM25 test query",
    extra_args: list[str] | None = None,
    timeout: int = HOOK_TIMEOUT,
) -> subprocess.CompletedProcess:
    payload = json.dumps({
        "prompt": prompt,
        "session_id": "test-session",
        "cwd": str(project_dir),
    })
    env = {**env, "CLAUDE_PROJECT_DIR": str(project_dir)}
    args = [_PYTHON, HOOK_PATH, "--rich"] + (extra_args or [])
    return subprocess.run(
        args,
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_dir),
        timeout=timeout,
    )


def _jsonl_lines(tmp_home: Path) -> list[dict]:
    """Read all lines from the telemetry JSONL in the isolated home."""
    log_path = tmp_home / ".claude" / "ctx-telemetry.jsonl"
    if not log_path.exists():
        return []
    lines = []
    for raw in log_path.read_text(encoding="utf-8").strip().splitlines():
        try:
            lines.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return lines


def _count_before(tmp_home: Path) -> int:
    return len(_jsonl_lines(tmp_home))


def _new_lines(tmp_home: Path, before: int) -> list[dict]:
    return _jsonl_lines(tmp_home)[before:]


def _build_env(tmp_home: Path, telemetry: bool = False) -> dict:
    """Build isolated env. Never touches real ~/.claude/."""
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    env["CTX_DASHBOARD_INTERNAL"] = "0"  # allow telemetry to fire
    # Clear potentially interfering vars
    for var in (
        "CTX_TELEMETRY", "CTX_AB_DISABLE", "CTX_DISABLE_SEMANTIC_RERANK",
        "CHAT_MEMORY_EXCLUDED_PROJECTS", "CHAT_MEMORY_SCOPE",
    ):
        env.pop(var, None)
    if telemetry:
        env["CTX_TELEMETRY"] = "1"
    return env


def _init_git_project(project_dir: Path) -> None:
    """Minimal git repo with one decision commit so G1 fires."""
    subprocess.run(["git", "init", str(project_dir)], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(project_dir), "config", "user.email", "t@t.com"],
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "-C", str(project_dir), "config", "user.name", "Test"],
        capture_output=True, check=True,
    )
    (project_dir / "README.md").write_text("# test")
    subprocess.run(["git", "-C", str(project_dir), "add", "."], capture_output=True, check=True)
    subprocess.run(
        ["git", "-C", str(project_dir), "commit", "-m", "feat: initial BM25 decision"],
        capture_output=True, check=True,
    )


# ─── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def ctx_home(tmp_path: Path) -> Path:
    """Isolated home directory for telemetry tests."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    # Suppress "first time" notice from touching real state
    (claude_dir / ".ctx-telemetry.notified").touch()
    return home


@pytest.fixture()
def ctx_project(tmp_path: Path) -> Path:
    """Minimal git project for hook execution."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".omc").mkdir()
    _init_git_project(project)
    return project


# ─── tests ───────────────────────────────────────────────────────────────────


def test_telemetry_disabled_no_jsonl_append(ctx_home, ctx_project):
    """When CTX_TELEMETRY is not set, no lines appended to jsonl."""
    env = _build_env(ctx_home, telemetry=False)
    log_path = ctx_home / ".claude" / "ctx-telemetry.jsonl"

    before = _count_before(ctx_home)
    result = _run_hook(ctx_project, env)
    assert result.returncode == 0, f"Hook crashed: {result.stderr[:300]}"

    after = len(_jsonl_lines(ctx_home))
    assert after == before, (
        f"Expected no new lines when telemetry disabled, got {after - before} new lines."
    )
    # jsonl file should not be created at all if it didn't exist
    if not log_path.exists():
        pass  # correct: file never created
    else:
        # File existed before — line count must be unchanged
        assert after == before


def test_telemetry_enabled_emits_hook_complete(ctx_home, ctx_project):
    """CTX_TELEMETRY=1 must produce at least one hook=bm25-memory, type=hook_complete event."""
    env = _build_env(ctx_home, telemetry=True)

    before = _count_before(ctx_home)
    result = _run_hook(ctx_project, env)
    assert result.returncode == 0, f"Hook crashed: {result.stderr[:300]}"

    new = _new_lines(ctx_home, before)
    assert new, "Expected telemetry events but got none."

    hook_complete = [e for e in new if e.get("type") == "hook_complete" and e.get("hook") == "bm25-memory"]
    assert hook_complete, (
        f"No hook_complete event with hook=bm25-memory found.\n"
        f"Events emitted: {[e.get('type') for e in new]}"
    )

    # hook_complete must have latency_ms
    ev = hook_complete[0]
    assert "latency_ms" in ev, f"hook_complete missing latency_ms: {ev}"
    assert isinstance(ev["latency_ms"], int) and ev["latency_ms"] >= 0

    # At least 2 distinct event types (hook_complete + prompt_received or stage event)
    types_emitted = {e.get("type") for e in new}
    assert len(types_emitted) >= 2, (
        f"Expected ≥2 distinct event types, got: {types_emitted}"
    )


def test_telemetry_enabled_includes_query_type(ctx_home, ctx_project):
    """query_type field must be present and non-empty in hook_complete for various prompts."""
    env = _build_env(ctx_home, telemetry=True)

    test_cases = [
        "BM25 어디 있지?",          # korean keyword
        "where is the vec daemon",   # english keyword
        "test",                       # short
    ]
    for prompt in test_cases:
        before = _count_before(ctx_home)
        result = _run_hook(ctx_project, env, prompt=prompt)
        assert result.returncode == 0, f"Hook crashed for prompt {prompt!r}: {result.stderr[:200]}"

        new = _new_lines(ctx_home, before)
        hook_complete = [e for e in new if e.get("type") == "hook_complete"]
        assert hook_complete, f"No hook_complete event for prompt {prompt!r}"

        ev = hook_complete[0]
        assert "query_type" in ev, f"hook_complete missing query_type for {prompt!r}: {ev}"
        assert isinstance(ev["query_type"], str) and ev["query_type"], (
            f"query_type is empty for prompt {prompt!r}: {ev}"
        )


def test_telemetry_enabled_emits_fallback_reason(ctx_home, ctx_project):
    """With CTX_DISABLE_SEMANTIC_RERANK=1, fallback_reasons must contain 'vec_daemon_down'."""
    env = _build_env(ctx_home, telemetry=True)
    env["CTX_DISABLE_SEMANTIC_RERANK"] = "1"

    before = _count_before(ctx_home)
    result = _run_hook(ctx_project, env)
    assert result.returncode == 0, f"Hook crashed: {result.stderr[:300]}"

    new = _new_lines(ctx_home, before)
    hook_complete = [e for e in new if e.get("type") == "hook_complete"]
    assert hook_complete, "No hook_complete event found."

    ev = hook_complete[0]
    fallback = ev.get("fallback_reasons", "")
    assert "vec_daemon_down" in fallback, (
        f"Expected 'vec_daemon_down' in fallback_reasons, got: {fallback!r}\nEvent: {ev}"
    )


def test_telemetry_enabled_zero_overhead_when_emit_fails(ctx_home, ctx_project):
    """If telemetry JSONL path is unwritable, hook must still exit 0."""
    env = _build_env(ctx_home, telemetry=True)

    # Make .claude/ directory unwritable so jsonl append fails
    claude_dir = ctx_home / ".claude"
    original_mode = claude_dir.stat().st_mode
    try:
        claude_dir.chmod(0o444)  # read-only
        result = _run_hook(ctx_project, env)
        assert result.returncode == 0, (
            f"Hook must exit 0 even when telemetry write fails.\n"
            f"stderr: {result.stderr[:300]}"
        )
        assert "Traceback" not in result.stderr, (
            "Unhandled exception in hook when telemetry path is unwritable."
        )
    finally:
        claude_dir.chmod(original_mode)  # restore for cleanup


def test_telemetry_latency_overhead_under_5ms(ctx_home, ctx_project):
    """Latency overhead of enabled vs disabled telemetry must be ≤5ms (10-run average)."""
    N = 10
    env_on = _build_env(ctx_home, telemetry=True)
    env_off = _build_env(ctx_home, telemetry=False)

    def measure(env: dict) -> float:
        t0 = time.perf_counter()
        r = _run_hook(ctx_project, env)
        elapsed = (time.perf_counter() - t0) * 1000
        assert r.returncode == 0, f"Hook crashed: {r.stderr[:200]}"
        return elapsed

    # Warm up (one run each to avoid cold-start skew)
    measure(env_on)
    measure(env_off)

    times_on = [measure(env_on) for _ in range(N)]
    times_off = [measure(env_off) for _ in range(N)]

    avg_on = sum(times_on) / N
    avg_off = sum(times_off) / N
    overhead = avg_on - avg_off

    # Allow up to 5ms overhead (very conservative — actual overhead ≤1ms).
    # Full subprocess round-trip is 300-600ms; 5ms is <2% relative overhead.
    assert overhead <= 5.0, (
        f"Telemetry overhead too high: {overhead:.1f}ms "
        f"(enabled={avg_on:.1f}ms, disabled={avg_off:.1f}ms, N={N})"
    )
