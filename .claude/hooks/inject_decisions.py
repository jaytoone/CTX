#!/usr/bin/env python3
"""
UserPromptSubmit hook: Inject previous technical decisions into Claude's context.

Reads .omc/world-model.json (dead-ends, known facts) and outputs additionalContext.
This is the G1 "decision memory" — deterministic, <1s, no LLM cost.

Replaces: mcp__memory__ (requires MCP call, non-deterministic)
          CLAUDE.md instructions (advisory, can be ignored)
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
    wm_path = os.path.join(project_dir, ".omc", "world-model.json")

    if not os.path.exists(wm_path):
        sys.exit(0)

    try:
        with open(wm_path) as f:
            wm = json.load(f)
    except Exception:
        sys.exit(0)

    lines = []

    # Dead-ends: things that failed — prevent re-exploration
    dead_ends = wm.get("dead_ends", [])
    if dead_ends:
        lines.append("[DEAD-ENDS — do not retry these approaches]")
        for de in dead_ends[-5:]:
            lines.append(f"  x {de.get('goal', '')[:60]} — {de.get('reason', '')[:80]}")

    # Known facts: confirmed truths
    known_facts = wm.get("known_facts", [])
    fact_lines = []
    for f in known_facts:
        if isinstance(f, dict):
            fact_lines.append(f"  * {f['fact'][:80]}")
        elif isinstance(f, str) and not f.startswith("paper:") and not f.startswith("README:") and not f.startswith("uncertain:"):
            fact_lines.append(f"  * {f[:80]}")
    if fact_lines:
        lines.append("[KNOWN FACTS]")
        lines.extend(fact_lines[-8:])

    # Current goal
    current_goal = wm.get("current_goal", "")
    if current_goal:
        lines.append(f"[CURRENT GOAL] {current_goal}")

    if lines:
        context = "\n".join(lines)
        output = {"additionalContext": context}
        json.dump(output, sys.stdout)

if __name__ == "__main__":
    main()
