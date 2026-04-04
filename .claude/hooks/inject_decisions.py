#!/usr/bin/env python3
"""
UserPromptSubmit hook: Inject project decision history into Claude's context.

Source: git log ONLY. No dependency on world-model.json or any manual files.
Git log is the universal, auto-generated decision record for any project.
"""
import json
import os
import subprocess
import sys


def get_git_decisions(project_dir, n=15):
    """Extract decision-bearing commits from git log."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--format=%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
    except Exception:
        return []

    commits = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    decision_keywords = [
        "pivot", "revert", "dead-end", "rejected", "chose", "switched",
        "CONVERGED", "failed", "success", "fix", "improvement",
        "benchmark", "eval", "decision",
    ]
    decisions = []
    work = []
    for c in commits:
        is_decision = any(kw.lower() in c.lower() for kw in decision_keywords)
        if is_decision:
            decisions.append(c[:80])
        else:
            work.append(c[:80])
    return decisions[:7], work[:3]


def get_project_overview(project_dir):
    """Extract first meaningful line from CLAUDE.md or README.md."""
    for fname in ["CLAUDE.md", "README.md"]:
        fpath = os.path.join(project_dir, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("---"):
                            return line[:100]
            except Exception:
                pass
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    lines = []

    # 1. Project overview
    overview = get_project_overview(project_dir)
    if overview:
        lines.append(f"[PROJECT] {overview}")

    # 2. Git-based decision history (the ONLY required source)
    decisions, work = get_git_decisions(project_dir, n=30)
    if decisions:
        lines.append("[RECENT DECISIONS (from git)]")
        for d in decisions:
            lines.append(f"  > {d}")
    if work:
        lines.append("[RECENT WORK]")
        for w in work:
            lines.append(f"  - {w}")

    if lines:
        output = {"additionalContext": "\n".join(lines)}
        json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
