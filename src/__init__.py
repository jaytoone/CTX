"""ctx_retriever — Context Bootstrapper for Claude Code."""

from __future__ import annotations

import threading
from pathlib import Path

_MARKER = Path.home() / ".claude" / "ctx-first-use.done"
_SETTINGS = Path.home() / ".claude" / "settings.json"

# Key hook that must be present for CTX to be active
_ACTIVATION_SENTINEL = "bm25-memory.py"


def _hooks_active() -> bool:
    """Return True if CTX hooks are wired into ~/.claude/settings.json."""
    try:
        import json
        if not _SETTINGS.exists():
            return False
        cfg = json.loads(_SETTINGS.read_text())
        hooks_block = cfg.get("hooks", {})
        return _ACTIVATION_SENTINEL in str(hooks_block)
    except Exception:
        return False


def _auto_activate() -> None:
    """If Claude Code is installed but CTX hooks are absent, run ctx-install silently."""
    if not _SETTINGS.exists():
        return  # Claude Code not installed — nothing to activate
    if _hooks_active():
        return  # already wired
    import subprocess
    import sys
    try:
        print(
            "[CTX] Claude Code detected but CTX hooks not found in settings.json.\n"
            "[CTX] Running ctx-install to activate context injection...",
            flush=True,
        )
        subprocess.run(
            [sys.executable, "-m", "ctx_retriever.cli.install"],
            check=False,
            timeout=30,
        )
    except Exception:
        pass  # silent — never block any ctx command


def _first_use_ping() -> None:
    """Fire a one-time Turso ping on first import of any CTX command.

    Runs in a daemon thread — zero latency impact on CLI startup.
    Marker file prevents duplicate pings. Silent on all failures.
    Includes hooks_active boolean so the funnel is measurable.
    """
    already_done = _MARKER.exists()
    hooks_up = _hooks_active()

    if already_done and hooks_up:
        return  # fully activated, no ping needed
    if already_done:
        return  # marker exists — don't spam; hooks_active change tracked elsewhere

    try:
        import hashlib
        import json
        import time
        import urllib.request
        from datetime import date, datetime, timezone

        machine_id = ""
        for mid_path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                machine_id = open(mid_path).read().strip()
                break
            except OSError:
                pass
        if not machine_id:
            import socket
            machine_id = socket.gethostname()

        claude_dir = Path.home() / ".claude"
        try:
            install_ts = int(claude_dir.stat().st_mtime) if claude_dir.exists() else 0
        except OSError:
            install_ts = 0
        d = datetime.fromtimestamp(install_ts, tz=timezone.utc).replace(
            day=1, hour=0, minute=0, second=0
        )
        install_month_epoch = str(int(d.timestamp()))
        user_id = hashlib.sha256(
            f"{machine_id}:{install_month_epoch}".encode()
        ).hexdigest()[:16]

        try:
            import importlib.metadata as _meta
            ctx_ver = _meta.version("ctx-retriever")
        except Exception:
            ctx_ver = "unknown"

        _TURSO_DB_URL = "https://frwp-jaytoone.aws-us-west-2.turso.io"
        _TURSO_WRITE_TOKEN = (
            "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NzYxMzQ4MjksImlkIjoiMDE5Y2VjYzIt"
            "MWMwMS03MGNjLWJjMzktMTA2NjlhODhlOTgxIiwicmlkIjoiNTgwNzNiZjgtNDc4My00YjhiLWI4ZjAt"
            "ZDY0ZWU2ZDRkYzcxIn0.AjxxxM0v4fcz0mONEdpI2t6ulp1NvUM87FLMUuWyvFa0wx0qavjzBGf6HnS9B"
            "--DepuT0EbhwRRuc9HHRTGXAA"
        )

        # hooks_active=1 means fully activated, 0 means pip-installed but not ctx-installed
        hooks_flag = "1" if hooks_up else "0"
        outcome = "FIRST_USE_PING" if hooks_up else "FIRST_USE_NO_HOOKS"

        sql = (
            "INSERT INTO ctx_session_aggregates "
            "(schema_version, user_id, session_id_hash, ts_date, total_turns, "
            "session_outcome, ctx_version) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        args_list = [
            {"type": "text",    "value": "v1.7"},
            {"type": "text",    "value": user_id},
            {"type": "text",    "value": f"first-use:{int(time.time())}:{hooks_flag}"},
            {"type": "text",    "value": str(date.today())},
            {"type": "integer", "value": "0"},
            {"type": "text",    "value": outcome},
            {"type": "text",    "value": ctx_ver},
        ]
        payload = json.dumps({"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": args_list}},
            {"type": "close"},
        ]}).encode()
        token = _TURSO_WRITE_TOKEN.replace("\n", "")
        req = urllib.request.Request(
            f"{_TURSO_DB_URL}/v2/pipeline",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        _MARKER.parent.mkdir(parents=True, exist_ok=True)
        _MARKER.write_text(f"{user_id}:{ctx_ver}:{date.today()}:{hooks_flag}")
    except Exception:
        pass  # never break the import


# ── Startup sequence (daemon threads — zero CLI latency impact) ───────────────

# 1. Auto-activate if Claude Code is present but hooks are missing
import sys as _sys
_running_install = any("install" in a for a in _sys.argv)
if not _running_install:  # skip when ctx-install itself is running (avoid loop)
    _t_activate = threading.Thread(target=_auto_activate, daemon=True)
    _t_activate.start()

# 2. First-use telemetry ping
_t_ping = threading.Thread(target=_first_use_ping, daemon=True)
_t_ping.start()
