# Claude Code Hook — Python Requirements
**Date**: 2026-04-29  **Machine**: lt-1 (be2ja, Windows-native)

Python 3.12 must be installed and `python3` must resolve to it.
See `20260429-windows-native-claude-code-setup.md` for Windows setup steps.

## pip packages

```bash
pip install sqlite-vec rank-bm25
```

| Package | Version (verified) | Required by | Purpose |
|---|---|---|---|
| `sqlite-vec` | 0.1.9 | `chat-memory.py` | Vec0 vector extension for vault.db hybrid search |
| `rank-bm25` | 0.2.2 | `bm25-memory.py` | BM25Okapi scoring for G1/G2 memory retrieval |
| `numpy` | 2.4.4 | `chat-memory.py` | Cosine similarity for vec0 results (auto-installed as rank-bm25 dep) |

No other third-party packages are required — all other hooks use stdlib only (`json`, `sqlite3`, `subprocess`, `re`, `socket`, `pathlib`).

## Hook inventory

| File | Event | Deps |
|---|---|---|
| `chat-memory.py` | UserPromptSubmit | `sqlite-vec`, `numpy` |
| `bm25-memory.py` | UserPromptSubmit | `rank-bm25` |
| `memory-keyword-trigger.py` | UserPromptSubmit | stdlib only |
| `g2-fallback.py` | PostToolUse (Grep) | stdlib only |
| `stop-decision-capture.py` | Stop / PreCompact | stdlib only |
| `subagent_tracker.py` | SubagentStart / SubagentStop | stdlib only |
| `utility-rate.py` | Stop | stdlib only |

## Verification

```bash
python3 -c "import sqlite_vec; print('sqlite_vec', sqlite_vec.__version__)"
python3 -c "from rank_bm25 import BM25Okapi; print('rank_bm25 ok')"

# Smoke-test each hook
for f in ~/.claude/hooks/*.py; do
    echo '{"session_id":"test","prompt":"hello","cwd":"'"$PWD"'"}' \
        | timeout 5 python3 "$f" 2>&1 | head -1
    echo "$(basename $f) → exit:$?"
done
```

## Windows-specific notes

- `sqlite-vec` ships a pre-built `.pyd` wheel for Windows — no compiler needed.
- `rank-bm25` is pure Python — installs cleanly on all platforms.
- If `python3` resolves to the Microsoft Store stub, disable the App Execution Alias:  
  Settings → Apps → Advanced app settings → App execution aliases → turn off `python3.exe`  
  Then: `cp Python312/python.exe Python312/python3.exe`
- `codebase-memory-mcp` (used by `bm25-memory.py` for background reindex) is **not** available on Windows — the hook falls back gracefully with a warning message.
