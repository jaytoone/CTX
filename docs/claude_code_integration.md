# CTX → Claude Code Integration

## Overview

CTX can be deployed as a Claude Code `UserPromptSubmit` hook to provide
trigger-driven context injection for every coding session.

## How It Works

```
User prompt → [ctx_real_loader.py hook]
                    ↓
             classify_trigger()
                    ↓
        EXPLICIT_SYMBOL → symbol index lookup (precision)
        SEMANTIC_CONCEPT → BM25 keyword scoring (recall)
        IMPLICIT_CONTEXT → BFS import graph traversal (coverage)
        TEMPORAL_HISTORY → session log lookup (ctx_session_tracker)
                    ↓
         inject file paths + symbol summary
         as additionalContext
```

## Supported Languages

| Language | Extensions |
|---|---|
| Python | `.py` |
| TypeScript | `.ts`, `.tsx` |
| JavaScript | `.js`, `.jsx` |
| Go | `.go` |
| Rust | `.rs` |
| Java | `.java` |
| C/C++ | `.c`, `.cpp`, `.h` |

Primary language auto-detected by file count. Related extensions co-indexed (e.g. `.ts` + `.tsx` together).

## Installation

```bash
# 1. Copy hooks
cp hooks/ctx_real_loader.py hooks/ctx_session_tracker.py ~/.claude/hooks/

# 2. Set your CTX path (line 25 in ctx_real_loader.py)
# CTX_PROJECT = "/path/to/your/CTX"   ← edit this

# 3. Register in ~/.claude/settings.json (see README)
```

The hook requires CTX to be available: edit `CTX_PROJECT` on line 25 to point to your CTX
clone, or install via `pip install ctx-retriever` and update the import path accordingly.
If the import fails, the hook silently falls back to no-op (safe for production use).

## Hook Behavior

| Trigger Type | Strategy | k (default) |
|---|---|---|
| `EXPLICIT_SYMBOL` | Symbol index exact/partial match | 2–3 |
| `SEMANTIC_CONCEPT` | BM25 keyword scoring | 4–6 |
| `IMPLICIT_CONTEXT` | BFS from seeds (depth ≤ 2) | 5–8 |
| `TEMPORAL_HISTORY` | Session log from `ctx_session_tracker.py` (PostToolUse hook) | 4 |

## Skip Conditions

- Prompt < 15 chars
- Starts with `/` (slash command)
- Contains `[noctx]` or `[raw]` tag
- Codebase has < 3 source files
- cwd is inside `.claude/` (meta-hook)

## User Tags

| Tag | Effect |
|---|---|
| `[noctx]` | Disable CTX entirely for this prompt |
| `[raw]` | Same as `[noctx]` (alias) |
| `[fix]` | Enable Fix/Replace mode — injects anti-anchoring guidance |

Fix/Replace mode is also auto-detected when the prompt starts with `fix:`, `bug:`, `refactor:`, or `replace:`.

## Output Format

```
[CTX] SEMANTIC_CONCEPT | 4/88 files — ~95% tokens saved | conf 0.72
Code files (★ core  · aux):
★ src/retrieval/adaptive_trigger.py [score=0.821]
★ src/trigger/trigger_classifier.py [score=0.754]
★ src/retrieval/full_context.py [score=0.641]
· tests/test_adaptive_trigger.py [score=0.412]
Recent session (2 files, <2h):
• hooks/ctx_real_loader.py
(Use the prompt intent to decide how to treat this context.)
```

When `SEMANTIC_CONCEPT` confidence < 0.5:
```
[CTX] SEMANTIC_CONCEPT | 4/88 files — ~95% tokens saved | conf 0.41 ⚠ low
  ⚠ Low confidence — for sharper results, name a specific file or symbol (e.g. "adaptive_trigger")
```

When Fix/Replace mode is active:
```
⚠ Fix/Replace mode: the files above show the CURRENT implementation.
  Treat it as the target to change — do NOT anchor on it as correct.
```

## A/B Test Design

To measure the impact of the CTX hook on Claude Code session quality:

### Metric
- Task completion accuracy (human-scored 1–5)
- Turns to first correct answer
- Files read unnecessarily (wasted reads)

### Protocol
1. **Baseline session** (hook disabled): solve 10 coding tasks in a Python/TS project
2. **CTX session** (hook enabled): solve same 10 tasks
3. Score each session independently

### Expected hypothesis
Based on LLM code generation experiments (CTX pass@1=0.265 vs Full=0.102, n=49; paper Section 4.7):
- CTX hook should reduce turns-to-answer by 20–40%
- CTX hook should reduce unnecessary file reads by 50–70%

## Performance

| Project | Language | Files | Time |
|---|---|---|---|
| CTX | Python | 88 | ~40ms |
| AgentNode | Python | 215 | ~165ms |
| OneViral | TypeScript | 651 | ~270ms |
| >2000 files | any | — | skipped (dir exclusion) |

## Related
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/decisions/20260326-path-derived-module-to-file|20260326-path-derived-module-to-file]]
