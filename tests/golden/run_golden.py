#!/usr/bin/env python3
"""
Golden fixture runner for bm25-memory.py pre-decomposition regression guard.

Usage:
    python3 tests/golden/run_golden.py            # read-only verify
    python3 tests/golden/run_golden.py --update   # overwrite expected outputs

Exit codes:
    0  — all fixtures matched (or --update completed)
    1  — one or more fixtures differ from expected

Environment:
    Each fixture carries its own env dict.  The runner merges it on top of
    the current process environment (so PATH / PYTHONPATH are inherited).
    HOME is overridden to /tmp/ctx_golden_home to isolate side effects.

Note on HAS_BM25:
    rank_bm25 is not installed in the default Python 3.14 (Homebrew) environment
    used by this machine.  G1 / G2-DOCS BM25 ranking therefore returns [] and
    only G2-GREP (git grep) + Session Notes + World Model are emitted.
    The fixtures capture that fallback behaviour faithfully — they will continue
    to pass after Task A decomposition as long as the same code paths execute.
    If rank_bm25 is later installed, run with --update to refresh expected outputs.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


FIXTURE_PATH = Path(__file__).parent / "bm25_memory_outputs.jsonl"
HOOK_PATH = Path(__file__).parent.parent.parent / "src" / "hooks" / "bm25-memory.py"
PROJECT_DIR = str(Path(__file__).parent.parent.parent.resolve())


def _ensure_golden_home() -> None:
    """Create /tmp/ctx_golden_home skeleton if absent."""
    home = Path("/tmp/ctx_golden_home/.claude")
    home.mkdir(parents=True, exist_ok=True)
    # No ctx-auto-tune.json → auto-tune disabled (consistent with capture)
    vault = Path("/tmp/ctx_golden_home/.local/share/claude-vault")
    vault.mkdir(parents=True, exist_ok=True)


def _build_env(fixture_env: dict) -> dict:
    """Merge fixture env on top of current process env."""
    env = {**os.environ}
    env.update(fixture_env)
    # Always ensure CLAUDE_PROJECT_DIR points to the actual project
    env["CLAUDE_PROJECT_DIR"] = PROJECT_DIR
    return env


def run_fixture(record: dict) -> tuple[str, int]:
    """Run a single fixture, return (stdout, exit_code)."""
    stdin_bytes = json.dumps(record["stdin"], ensure_ascii=False).encode("utf-8")
    cmd = [sys.executable, str(HOOK_PATH)] + record.get("argv", [])
    env = _build_env(record["env"])

    result = subprocess.run(
        cmd,
        input=stdin_bytes,
        capture_output=True,
        env=env,
        cwd=PROJECT_DIR,
    )
    return result.stdout.decode("utf-8", errors="replace"), result.returncode


def _diff_summary(expected: str, actual: str) -> str:
    """Return a compact unified-diff-style summary of mismatches."""
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    diff_lines = []
    max_lines = max(len(exp_lines), len(act_lines))
    for i in range(max_lines):
        e = exp_lines[i] if i < len(exp_lines) else "<missing>"
        a = act_lines[i] if i < len(act_lines) else "<missing>"
        if e != a:
            diff_lines.append(f"  line {i+1}")
            diff_lines.append(f"  - {e[:120]}")
            diff_lines.append(f"  + {a[:120]}")
        if len(diff_lines) > 30:
            diff_lines.append("  ... (truncated)")
            break
    return "\n".join(diff_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run golden fixtures for bm25-memory.py")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Overwrite expected outputs with current hook output (explicit consent required).",
    )
    args = parser.parse_args()

    if not FIXTURE_PATH.exists():
        print(f"ERROR: fixture file not found: {FIXTURE_PATH}", file=sys.stderr)
        return 1

    if not HOOK_PATH.exists():
        print(f"ERROR: hook not found: {HOOK_PATH}", file=sys.stderr)
        return 1

    _ensure_golden_home()

    records = []
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("ERROR: no fixtures found in JSONL file", file=sys.stderr)
        return 1

    failures = []
    updated = []

    for rec in records:
        fid = rec["id"]
        cat = rec["category"]
        actual_stdout, actual_exit = run_fixture(rec)

        expected_stdout = rec["expected_stdout"]
        expected_exit = rec["expected_exit_code"]

        stdout_ok = actual_stdout == expected_stdout
        exit_ok = actual_exit == expected_exit

        if stdout_ok and exit_ok:
            print(f"  PASS  [{cat}] {fid}")
        elif args.update:
            rec["expected_stdout"] = actual_stdout
            rec["expected_exit_code"] = actual_exit
            rec["elapsed_ms_observed"] = rec.get("elapsed_ms_observed", 0)
            print(f"  UPDATE [{cat}] {fid}  (exit: {expected_exit}→{actual_exit}, stdout_changed={not stdout_ok})")
            updated.append(fid)
        else:
            msg_parts = []
            if not exit_ok:
                msg_parts.append(f"exit expected={expected_exit} actual={actual_exit}")
            if not stdout_ok:
                diff = _diff_summary(expected_stdout, actual_stdout)
                msg_parts.append(f"stdout mismatch:\n{diff}")
            print(f"  FAIL  [{cat}] {fid}:", file=sys.stderr)
            for m in msg_parts:
                print(f"    {m}", file=sys.stderr)
            failures.append(fid)

    if args.update and updated:
        with FIXTURE_PATH.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\nUpdated {len(updated)} fixture(s) in {FIXTURE_PATH}")
        return 0

    total = len(records)
    passed = total - len(failures)
    print(f"\n{passed}/{total} fixtures passed")

    if failures:
        print(f"FAILED: {failures}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
