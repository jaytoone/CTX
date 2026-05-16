#!/bin/bash
# Idempotent autostart for vec-daemon + bge-daemon (SessionStart hook).
# Wired into ~/.claude/settings.json by ctx-install.
# Spawns missing daemons in background; exits immediately so session start isn't blocked.
#
# Python interpreter detection (priority order):
#   1. pipx env:     ~/.local/pipx/venvs/ctx-retriever/bin/python    (pip install path)
#   2. venv:         ~/.local/share/claude-vault/venv/bin/python     (plugin Setup path)
#   3. (none)        graceful exit — hook stays BM25-only
# Daemon spawn requires `sentence_transformers` importable in the chosen interpreter.
#
# Liveness check: pgrep is the source of truth. A stale socket file alone (e.g.
# from a daemon SIGKILL'd, system reboot, or terminal close) does not count as
# "alive" — we unlink it and respawn. This avoids the "dead daemon, stale sock,
# script silently skips spawn forever" failure mode.

set -u
DAEMON_DIR="$HOME/.local/share/claude-vault"
LOG_DIR="$HOME/.cache/claude-vault-daemons"
mkdir -p "$LOG_DIR"

PIPX_PY="$HOME/.local/pipx/venvs/ctx-retriever/bin/python"
VENV_PY="$DAEMON_DIR/venv/bin/python"

PY=""
if [ -x "$PIPX_PY" ] && "$PIPX_PY" -c "import sentence_transformers" 2>/dev/null; then
  PY="$PIPX_PY"
elif [ -x "$VENV_PY" ] && "$VENV_PY" -c "import sentence_transformers" 2>/dev/null; then
  PY="$VENV_PY"
fi

# Graceful degradation: no usable interpreter → BM25-only, no spawn
if [ -z "$PY" ]; then
  exit 0
fi

# vec-daemon — spawn if process not alive (pgrep authoritative, socket can be stale)
if ! pgrep -f "vec-daemon.py" >/dev/null 2>&1; then
  rm -f "$DAEMON_DIR/vec-daemon.sock" "$DAEMON_DIR/vec-daemon.pid"
  if [ -f "$DAEMON_DIR/vec-daemon.py" ]; then
    nohup "$PY" "$DAEMON_DIR/vec-daemon.py" \
      >"$LOG_DIR/vec-daemon.log" 2>&1 &
    disown
  fi
fi

# bge-daemon — opt-in via CTX_BGE_ENABLE=1 (semantic rerank, ~58s first-run model load)
if [ "${CTX_BGE_ENABLE:-0}" = "1" ]; then
  if ! pgrep -f "bge-daemon.py" >/dev/null 2>&1; then
    rm -f "$DAEMON_DIR/bge-daemon.sock" "$DAEMON_DIR/bge-daemon.pid"
    if [ -f "$DAEMON_DIR/bge-daemon.py" ]; then
      nohup "$PY" "$DAEMON_DIR/bge-daemon.py" \
        >"$LOG_DIR/bge-daemon.log" 2>&1 &
      disown
    fi
  fi
fi

exit 0
