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

python_bin field (optional):
    Each fixture may carry a "python_bin" field specifying the interpreter to
    use.  Relative paths are resolved from the project root.  Absolute paths
    are used as-is.  If the field is absent, sys.executable (the interpreter
    running this script) is used.  If the specified interpreter does not exist
    the fixture is an immediate FAIL — it is never silently skipped.

    Fallback fixtures (no python_bin):  system Python, the BM25 library absent →
        HAS_BM25=False path, G1/G2-DOCS return [] (only G2-GREP emitted).
    BM25-path fixtures (python_bin=".venv-golden/bin/python"):  BM25 library
        present (v0.2.2) → HAS_BM25=True path, G1 [RECENT DECISIONS] + G2-DOCS
        blocks emitted alongside G2-GREP.

Note on HAS_BM25:
    The BM25 library (package name: rank-bm25) is not installed in the default
    Python 3.14 (Homebrew) environment used by this machine.  G1 / G2-DOCS BM25
    ranking therefore returns [] and only G2-GREP (git grep) + Session Notes +
    World Model are emitted.  The fixtures capture that fallback behaviour
    faithfully — they will continue to pass after Task A decomposition as long as
    the same code paths execute.
    BM25-path fixtures (suffix _bm25path) use .venv-golden/bin/python where the
    BM25 library is installed; these capture the full G1+G2-DOCS output.
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

# Frozen decision corpus for BM25-path fixtures.
# Captured at commit b398ee8 (220 entries, embeddings stripped).
# Injected into .omc/decision_corpus.json before each _bm25path fixture run,
# with the current git HEAD written into the "head" field so bm25-memory.py
# treats it as a valid cache hit and skips rebuilding from git log.
# This isolates BM25-path fixtures from future git commits.
FROZEN_CORPUS_PATH = Path(__file__).parent / "bm25_path_corpus_frozen.json"


def _get_git_head() -> str:
    """Return the current git HEAD SHA, or empty string on failure."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_DIR,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def _inject_frozen_corpus() -> None:
    """Write frozen corpus into .omc/decision_corpus.json with current HEAD.

    bm25-memory.py checks cache_path head == current HEAD to decide whether
    to use the cache.  By injecting the frozen corpus with the current HEAD,
    we make the hook use our fixed corpus regardless of new git commits.
    """
    if not FROZEN_CORPUS_PATH.exists():
        return
    head = _get_git_head()
    frozen = json.loads(FROZEN_CORPUS_PATH.read_text())
    cache_path = Path(PROJECT_DIR) / ".omc" / "decision_corpus.json"
    cache_path.parent.mkdir(exist_ok=True)
    cache_path.write_text(json.dumps({
        "head": head,
        "corpus": frozen["corpus"],
        "emb_head": "",  # no embeddings → dense path disabled, BM25-only
    }, ensure_ascii=False))


def _ensure_golden_home() -> None:
    """Create HOME skeleton directories for both fallback and BM25-path fixtures."""
    for home_root in ("/tmp/ctx_golden_home", "/tmp/ctx_golden_home_bm25"):
        home = Path(home_root) / ".claude"
        home.mkdir(parents=True, exist_ok=True)
        # No ctx-auto-tune.json → auto-tune disabled (consistent with capture)
        vault = Path(home_root) / ".local/share/claude-vault"
        vault.mkdir(parents=True, exist_ok=True)


def _resolve_python_bin(python_bin: str | None) -> str:
    """Resolve python_bin field to an absolute path.

    Relative paths are resolved from the project root (PROJECT_DIR).
    If python_bin is None, fall back to sys.executable.
    Raises FileNotFoundError if the resolved path does not exist.
    """
    if python_bin is None:
        return sys.executable
    p = Path(python_bin)
    if not p.is_absolute():
        p = Path(PROJECT_DIR) / p
    if not p.exists():
        raise FileNotFoundError(
            f"python_bin interpreter not found: {p}\n"
            f"  (original value: {python_bin!r})\n"
            f"  Ensure .venv-golden is set up: pip install rank-bm25 numpy"
        )
    return str(p)


def _build_env(fixture_env: dict) -> dict:
    """Merge fixture env on top of current process env."""
    env = {**os.environ}
    env.update(fixture_env)
    # Always ensure CLAUDE_PROJECT_DIR points to the actual project
    env["CLAUDE_PROJECT_DIR"] = PROJECT_DIR
    return env


def run_fixture(record: dict) -> tuple[str, str, int]:
    """Run a single fixture, return (stdout, stderr, exit_code).

    Uses the interpreter specified by the fixture's optional "python_bin" field.
    Relative paths are resolved from PROJECT_DIR.  Missing interpreter → FAIL.

    For BM25-path fixtures (python_bin set), injects frozen decision corpus
    before running so G1 BM25 ranking is stable across git commits.
    """
    stdin_bytes = json.dumps(record["stdin"], ensure_ascii=False).encode("utf-8")
    python_bin = _resolve_python_bin(record.get("python_bin"))
    cmd = [python_bin, str(HOOK_PATH)] + record.get("argv", [])
    env = _build_env(record["env"])

    # Inject frozen corpus for BM25-path fixtures to prevent G1 rank drift
    # caused by new commits being added to the decision corpus.
    if record.get("python_bin"):
        _inject_frozen_corpus()

    result = subprocess.run(
        cmd,
        input=stdin_bytes,
        capture_output=True,
        env=env,
        cwd=PROJECT_DIR,
    )
    return (
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
        result.returncode,
    )


import re as _re


def _normalize_g2grep_str(text: str) -> str:
    """Apply G2-GREP normalization to a plain string (may be embedded in JSON context)."""
    def _replace_block(m: _re.Match) -> str:
        header = m.group(1)       # e.g. "[G2-GREP] Files matching '...' (grep):"
        file_lines = m.group(2)   # the file list lines
        start_line = m.group(3)   # "  Start with: ..." line
        count = len([l for l in file_lines.strip().splitlines() if l.strip()])
        return f"{header}\n  <{count} file(s) — paths normalized>\n{start_line}"

    # Pattern: header + 1+ indented file lines + "Start with:" line
    pattern = (
        r'(\[G2-GREP\] Files matching \'[^\']*\' \(grep\):)'  # group 1: header
        r'(\n(?:  [^\n]+\n)+)'                                  # group 2: file lines
        r'(  Start with:[^\n]*)'                               # group 3: start-with line
    )
    return _re.sub(pattern, _replace_block, text)


def _normalize_g2grep(text: str) -> str:
    """Normalize G2-GREP blocks in hook output so file list changes don't cause drift.

    The hook emits a single JSON line whose 'hookSpecificOutput.additionalContext'
    field contains the rendered context block (with G2-GREP sections).  This
    function parses the JSON, normalizes G2-GREP file lists inside the context
    string, and re-serialises so that exact file path changes (from new files
    being added to the repo) don't fail fixtures.

    What is still validated:
      - G2-GREP header line (keyword and format) is unchanged
      - Number of matched files is unchanged
      - "Start with: ..." line presence
    What is NOT validated:
      - Which specific files appear in the list (only count checked)
    """
    try:
        data = json.loads(text)
        ctx = data.get("hookSpecificOutput", {}).get("additionalContext", "")
        if ctx and "[G2-GREP]" in ctx:
            data["hookSpecificOutput"]["additionalContext"] = _normalize_g2grep_str(ctx)
        return json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, AttributeError):
        # Fallback: treat as plain text (e.g., error output)
        return _normalize_g2grep_str(text)


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
        try:
            actual_stdout, actual_stderr, actual_exit = run_fixture(rec)
        except FileNotFoundError as exc:
            print(f"  FAIL  [{cat}] {fid}: interpreter missing — {exc}", file=sys.stderr)
            failures.append(fid)
            continue

        expected_stdout = rec["expected_stdout"]
        expected_exit = rec["expected_exit_code"]
        # expected_stderr is optional — absent means "skip stderr check" (backward-compat).
        expected_stderr: str | None = rec.get("expected_stderr")

        # Normalize G2-GREP file lists before comparison to prevent drift
        # from new files being added to the repo.
        norm_expected = _normalize_g2grep(expected_stdout)
        norm_actual = _normalize_g2grep(actual_stdout)

        stdout_ok = norm_actual == norm_expected
        exit_ok = actual_exit == expected_exit
        # stderr comparison: only when fixture has explicit expected_stderr field.
        stderr_ok = (expected_stderr is None) or (actual_stderr == expected_stderr)

        if stdout_ok and exit_ok and stderr_ok:
            print(f"  PASS  [{cat}] {fid}")
        elif args.update:
            rec["expected_stdout"] = actual_stdout
            rec["expected_exit_code"] = actual_exit
            # Update expected_stderr only if the fixture already had the field.
            if expected_stderr is not None:
                rec["expected_stderr"] = actual_stderr
            rec["elapsed_ms_observed"] = rec.get("elapsed_ms_observed", 0)
            stderr_changed = (expected_stderr is not None) and (actual_stderr != expected_stderr)
            print(
                f"  UPDATE [{cat}] {fid}  (exit: {expected_exit}→{actual_exit},"
                f" stdout_changed={not stdout_ok}, stderr_changed={stderr_changed})"
            )
            updated.append(fid)
        else:
            msg_parts = []
            if not exit_ok:
                msg_parts.append(f"exit expected={expected_exit} actual={actual_exit}")
            if not stdout_ok:
                diff = _diff_summary(norm_expected, norm_actual)
                msg_parts.append(f"stdout mismatch (G2-GREP normalized):\n{diff}")
            if not stderr_ok:
                diff = _diff_summary(expected_stderr or "", actual_stderr)
                msg_parts.append(f"stderr mismatch:\n{diff}")
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
