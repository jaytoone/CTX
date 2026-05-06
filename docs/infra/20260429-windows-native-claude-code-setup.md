# Windows-Native Claude Code Setup — CTX Hooks Migration from WSL2
**Date**: 2026-04-29  **Machine**: lt-1 (be2ja, Tailscale `100.125.152.31`)

## Context

The WSL2 host (desktop-8hiuju8, `100.66.30.40`) was wiped during a Windows 11 reinstall. This document records the process of reproducing the full CTX hook stack on a Windows-native machine (no WSL2, no zellij) running Claude Code CLI via Git Bash (MSYS2/MINGW64).

## Architecture Difference: WSL2 vs Windows-Native

| Aspect | WSL2 (before) | Windows-Native (now) |
|---|---|---|
| Shell | Linux bash | Git Bash (MSYS2/MINGW64) |
| Python | System python3 | `winget install Python.Python.3.12` |
| Node.js | System node | Not installed (Claude Code bundles its own) |
| Popup mechanism | WSL→PowerShell.exe WinForms inline | POST to local listener at `localhost:6789` |
| Tailscale fan-out | `tailscale status --json` → POST to peers | Same (Tailscale CLI available in Git Bash) |
| Zellij / celi | zellij + `~/scripts/zellij-csk.sh` alias | Not applicable (no WSL2) |
| Path conversion | `wslpath -w` | `cygpath -w` |
| Unix sockets | Available (vec-daemon, bge-daemon) | Not available on Windows |

## What Was Set Up

### 1. Notify Listener (port 6789)

`claude-notify-listener.ps1` at `C:\Users\be2ja\` — installed via the WSL2 bootstrap script before the wipe. HTTP.sys-based, handles `/notify`, `/close`, `/clipboard`, `/health`, `/expose`, `/unexpose`.

**Auto-start**: Not yet registered as a Scheduled Task (needs admin PowerShell). Listener was started manually; survives until reboot.

### 2. Claude Code Hooks

All hooks copied from `D:\Desk-Home\wsl\claude\hooks\` (the WSL2 backup) to `C:\Users\be2ja\.claude\hooks\`.

#### Bash hooks (work as-is, zero deps)

| Hook | Event | File |
|---|---|---|
| `windows-notify.sh` | PermissionRequest / Notification | POSTs to `localhost:6789/notify` + Tailscale fan-out |
| `windows-stop.sh` | Stop | POSTs kind=stop + console green banner |
| `close-popup.sh` | UserPromptSubmit (async) | POSTs `/close` to dismiss existing popups |
| `pre-compact-save.sh` | PreCompact | **Ported from JS** — writes `.compact-marker` + `.memory-update-hint.md` |
| `stop-playwright-detect.sh` | Stop | Checks git diff for UI file changes |
| `post-write-doc-index.sh` | PostToolUse (Write\|Edit) | Enforces DOC_INDEX.md update |
| `session-end-hint.sh` | SessionEnd | Creates MEMORY.md update hint |

#### Python hooks (need Python 3.12 installed)

| Hook | Event | File |
|---|---|---|
| `chat-memory.py` | UserPromptSubmit | CM: vault.db FTS5 hybrid search |
| `bm25-memory.py` | UserPromptSubmit | G1 + G2-DOCS + G2-PREFETCH + G2-HOOKS |
| `memory-keyword-trigger.py` | UserPromptSubmit | Decision keyword detection → MEMORY.md |
| `stop-decision-capture.py` | PreCompact / Stop | Captures decisions to file |
| `subagent_tracker.py` | SubagentStart/Stop | Tracks subagent lifecycle |
| `utility-rate.py` | Stop (async) | Rates response utility |
| `g2-fallback.py` | PostToolUse (Grep) | Fallback search on Grep miss |

### 3. Skills & Agents

Copied from WSL2 backup:
- **81 skills** in `~/.claude/skills/`
- **54 agents** in `~/.claude/agents/`

### 4. Settings & Permissions

`C:\Users\be2ja\.claude\settings.json` configured with:
- All hooks wired (matching WSL2 settings.json structure)
- Permission allowlist for common bash commands
- Env vars: timeouts, model defaults, output limits

## Windows-Specific Fixes Required

### Fix 1: Python 3 Resolution (`python3` command)

**Problem**: Windows Python 3.12 installs as `python.exe` only. The Microsoft Store "App Execution Alias" registers a stub `python3.exe` in `WindowsApps` that opens the Store instead of running Python.

**Solution** (both steps needed):
1. Disable App Execution Alias: Settings → Apps → Advanced app settings → App execution aliases → turn off `python3.exe`
2. Copy the real executable: `cp Python312/python.exe Python312/python3.exe`

```bash
cp "/c/Users/be2ja/AppData/Local/Programs/Python/Python312/python.exe" \
   "/c/Users/be2ja/AppData/Local/Programs/Python/Python312/python3.exe"
```

### Fix 2: Python in PATH

Python 3.12 installer adds to Windows user PATH but not to Git Bash PATH. Add to `~/.bashrc`:

```bash
export PATH="/c/Users/be2ja/AppData/Local/Programs/Python/Python312:/c/Users/be2ja/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
```

### Fix 3: `pre-compact-save.js` → `.sh`

The original `pre-compact-save.js` requires Node.js. Since Claude Code on Windows may not expose `node` to hook subprocesses, it was rewritten as pure bash:

```bash
#!/bin/bash
input=$(cat)
trigger=$(echo "$input" | grep -oP '"trigger"\s*:\s*"\K[^"]*')
session_id=$(echo "$input" | grep -oP '"session_id"\s*:\s*"\K[^"]*')
# ... write marker file, hint file, call save-work-progress.sh
```

JSON parsing uses `grep -oP` for flat top-level fields. Acceptable here because PreCompact payloads are simple flat JSON.

### Fix 4: Popup hooks simplified

WSL2 hooks spawned PowerShell WinForms inline (`/mnt/c/.../powershell.exe -STA -Command "..."`). Windows hooks simply POST to the local listener at `localhost:6789`, which handles the WinForms popup.

## Remaining Gaps (vs WSL2)

| Gap | Impact | Path to fix |
|---|---|---|
| SessionStart vec-daemon + bge-daemon | No dense/semantic search — CM falls back to BM25-only | Requires Unix sockets (AF_UNIX) — not available on Windows without WSL2 |
| `claude-vault-incremental.sh` | No vault backup at PreCompact/Stop | Needs `~/.local/share/claude-vault/` system |
| `jq` not installed | Some hooks use `grep -oP` fallback instead | `winget install jqlang.jq` |
| Listener auto-start | Dies on reboot | Register Scheduled Task (needs admin PS once) |

## Python Package Dependencies

```bash
pip install sqlite-vec   # Required by chat-memory.py
pip install rank-bm25    # Required by bm25-memory.py (if running retriever locally)
```

## Verification Commands

```bash
# Test all bash hooks
for f in ~/.claude/hooks/*.sh; do
    echo '{}' | timeout 3 bash "$f" 2>&1 | head -1
    echo "$(basename $f) → exit:$?"
done

# Test all python hooks
for f in ~/.claude/hooks/*.py; do
    echo '{}' | timeout 3 python3 "$f" 2>&1 | head -1
    echo "$(basename $f) → exit:$?"
done

# Test listener
curl -sf http://127.0.0.1:6789/health  # expect: ok
```

## Key Lesson: Cross-Platform Hook Strategy

From the research done during this migration (see expert-research output in session):

1. **Node.js is always available** on Claude Code machines — it's a runtime dependency. For cross-platform hooks targeting beginners, Node.js is the safest language.
2. **BM25 is not bashable** — floating-point IDF math + inverted indexes have no pure-bash implementation. Keep these in Python or rewrite in JS.
3. **Bash works for I/O hooks** — keyword detection, file writes, curl POSTs, git status checks.
4. **Graceful degradation** — Python hooks that fail (missing deps) exit 0 and don't block Claude. This is the correct pattern for optional hooks.
