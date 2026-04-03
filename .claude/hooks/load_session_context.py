#!/usr/bin/env python3
"""
SessionStart hook: Load project context at session start.

Injects: architecture overview, recent decisions, and dead-ends.
Fires on startup and resume (not compact — that's handled by CLAUDE.md).
"""
import json
import os
import sys

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    lines = []

    # 1. Project identity from CLAUDE.md first line
    claude_md = os.path.join(project_dir, "CLAUDE.md")
    if os.path.exists(claude_md):
        with open(claude_md) as f:
            first_lines = []
            for line in f:
                first_lines.append(line.strip())
                if len(first_lines) >= 3:
                    break
        if first_lines:
            lines.append(f"[PROJECT] {' '.join(first_lines[:2])}")

    # 2. Architecture from codebase-memory-mcp index (if cached)
    index_status = os.path.join(project_dir, ".codebase-memory", "index.json")
    if os.path.exists(index_status):
        lines.append("[CODEBASE] Indexed by codebase-memory-mcp (use search_graph/trace_call_path)")

    # 3. Dead-ends summary
    wm_path = os.path.join(project_dir, ".omc", "world-model.json")
    if os.path.exists(wm_path):
        try:
            with open(wm_path) as f:
                wm = json.load(f)
            dead_ends = wm.get("dead_ends", [])
            if dead_ends:
                lines.append(f"[WORLD MODEL] {len(dead_ends)} dead-ends, {len(wm.get('tried_strategies', []))} strategies tracked")
        except Exception:
            pass

    # 4. Recent git activity (last 3 commits)
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            lines.append("[RECENT COMMITS]")
            for commit_line in result.stdout.strip().split("\n")[:3]:
                lines.append(f"  {commit_line}")
    except Exception:
        pass

    if lines:
        print("\n".join(lines))  # stdout → additionalContext for SessionStart

if __name__ == "__main__":
    main()
