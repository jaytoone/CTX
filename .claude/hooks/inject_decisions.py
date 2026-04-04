#!/usr/bin/env python3
"""
UserPromptSubmit hook: Inject project decision history into Claude's context.

Primary source: git log (always exists, auto-generated)
Secondary source: .omc/world-model.json (if exists, structured dead-ends/facts)
Tertiary source: CLAUDE.md first section (if exists, project overview)

No manual data entry required — git log is the universal decision record.
"""
import json
import os
import subprocess
import sys


def get_git_decisions(project_dir, n=10):
    """Extract decision-bearing commits from git log."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--format=%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        commits = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        # Filter: keep commits with decision signals (pivots, failures, choices)
        decision_keywords = [
            "pivot", "revert", "dead-end", "rejected", "chose", "switched",
            "CONVERGED", "failed", "success", "fix", "improvement",
            "→", "↑", "↓", "+", "benchmark", "eval", "decision",
        ]
        decisions = []
        for c in commits:
            # All commits are useful context, but decision-bearing ones get priority
            is_decision = any(kw.lower() in c.lower() for kw in decision_keywords)
            decisions.append(("D" if is_decision else "W", c[:80]))
        return decisions
    except Exception:
        return []


def get_world_model(project_dir):
    """Load structured dead-ends and facts from world-model.json if it exists."""
    wm_path = os.path.join(project_dir, ".omc", "world-model.json")
    if not os.path.exists(wm_path):
        return [], []
    try:
        with open(wm_path) as f:
            wm = json.load(f)
    except Exception:
        return [], []

    dead_ends = []
    for de in wm.get("dead_ends", [])[-5:]:
        dead_ends.append(f"  x {de.get('goal', '')[:60]} -- {de.get('reason', '')[:80]}")

    facts = []
    for fact in wm.get("known_facts", []):
        if isinstance(fact, dict):
            facts.append(f"  * {fact['fact'][:80]}")
        elif isinstance(fact, str) and not any(fact.startswith(p) for p in ("paper:", "README:", "uncertain:")):
            facts.append(f"  * {fact[:80]}")

    return dead_ends, facts[-8:]


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

    # 1. Project overview (CLAUDE.md or README.md)
    overview = get_project_overview(project_dir)
    if overview:
        lines.append(f"[PROJECT] {overview}")

    # 2. Git-based decision history (always available)
    git_decisions = get_git_decisions(project_dir, n=10)
    if git_decisions:
        decision_commits = [msg for tag, msg in git_decisions if tag == "D"]
        work_commits = [msg for tag, msg in git_decisions if tag == "W"]
        if decision_commits:
            lines.append("[RECENT DECISIONS (from git)]")
            for d in decision_commits[:5]:
                lines.append(f"  > {d}")
        if work_commits:
            lines.append("[RECENT WORK]")
            for w in work_commits[:3]:
                lines.append(f"  - {w}")

    # 3. World-model dead-ends + facts (if exists — bonus, not required)
    dead_ends, facts = get_world_model(project_dir)
    if dead_ends:
        lines.append("[DEAD-ENDS -- do not retry]")
        lines.extend(dead_ends)
    if facts:
        lines.append("[KNOWN FACTS]")
        lines.extend(facts)

    if lines:
        output = {"additionalContext": "\n".join(lines)}
        json.dump(output, sys.stdout)


if __name__ == "__main__":
    main()
