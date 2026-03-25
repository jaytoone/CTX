# CTX → Claude Code Integration

## Overview

CTX can be deployed as a Claude Code `UserPromptSubmit` hook to provide
trigger-driven context injection for every coding session.

## How It Works

```
User prompt → [ctx_loader.py hook]
                    ↓
             classify_trigger()
                    ↓
        EXPLICIT_SYMBOL → symbol index lookup (precision)
        SEMANTIC_CONCEPT → ASCII keyword scoring (recall)
        IMPLICIT_CONTEXT → BFS import graph traversal (coverage)
        TEMPORAL_HISTORY → skip (memory MCP handles)
                    ↓
         inject file paths + symbol summary
         as additionalContext
```

## Installation

```bash
# 1. Copy hook
cp /home/jayone/Project/CTX/docs/ctx_loader_hook.py ~/.claude/hooks/ctx_loader.py

# 2. Add to ~/.claude/settings.json UserPromptSubmit hooks:
{
  "type": "command",
  "command": "python3 $HOME/.claude/hooks/ctx_loader.py"
}
```

The hook is self-contained (no external CTX imports required).

## Hook Behavior

| Trigger Type | Strategy | k (default) |
|---|---|---|
| EXPLICIT_SYMBOL | Symbol index exact/partial match | 2–3 |
| SEMANTIC_CONCEPT | ASCII keyword frequency scoring | 4–6 |
| IMPLICIT_CONTEXT | BFS from seeds (depth ≤ 2) | 5–8 |
| TEMPORAL_HISTORY | Skipped (memory MCP) | — |

## Skip Conditions

- Prompt < 15 chars
- Starts with `/` (slash command)
- Contains `[noctx]` or `[raw]` tag
- Codebase has < 3 Python files
- cwd is inside `.claude/` (meta-hook)

## Output Format

```
[CTX] Trigger: EXPLICIT_SYMBOL | Query: TriggerClassifier | Confidence: 0.90
Relevant files (1/88 total):
• src/trigger/trigger_classifier.py [TriggerType, Trigger, TriggerClassifier]
  Trigger classifier for CTX experiment.
```

## A/B Test Design

To measure the impact of the CTX hook on Claude Code session quality:

### Metric
- Task completion accuracy (human-scored 1–5)
- Turns to first correct answer
- Files read unnecessarily (wasted reads)

### Protocol
1. **Baseline session** (hook disabled): solve 10 coding tasks in a Python project
2. **CTX session** (hook enabled): solve same 10 tasks
3. Score each session independently

### Expected hypothesis
Based on LLM quality experiments (CTX pass@1=0.733 vs Full=0.200):
- CTX hook should reduce turns-to-answer by 20–40%
- CTX hook should reduce unnecessary file reads by 50–70%

## Performance

| Project size | Indexing time |
|---|---|
| 88 .py files | ~40ms |
| 215 .py files | ~165ms |
| >2000 .py files | skipped (venv detection) |
