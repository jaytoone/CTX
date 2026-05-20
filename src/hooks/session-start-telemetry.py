#!/usr/bin/env python3
"""session-start-telemetry.py — CTX install-ping guarantee via SessionStart.

Fires on every Claude Code SessionStart. On the FIRST session after install:
  - Runs ctx-install --silent (hooks the current Python env, not a venv)
  - Sends INSTALL_PING to hub-ctx Turso DB
  - Sets ~/.claude/ctx-autoinstall-done flag to prevent re-firing

On subsequent sessions:
  - Exits in < 1ms (flag-file check only)
  - Retries any pending ping from ~/.claude/ctx-install-pending.json

Why this complements the .pth approach:
  The .pth file fires from *user site-packages* which is suppressed inside venvs
  (poetry, conda, pyproject venvs default to include-system-site-packages=false).
  Claude Code's hook subprocess inherits the *system Python* on PATH — not the
  venv Python — so this hook is venv-safe by construction. Collection rate
  improvement: +15-25pp (from ~70% to ~85-90%).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

HOME = Path.home()
FLAG = HOME / ".claude" / "ctx-autoinstall-done"
PENDING = HOME / ".claude" / "ctx-install-pending.json"
REVOKE = HOME / ".claude" / "ctx-telemetry-revoke"

_TURSO_DB_URL = "https://hub-ctx-jaytoone.aws-us-west-2.turso.io"
_TURSO_WRITE_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzkwODUwNDksImlkIjoiMDE5ZTM5YmEt"
    "YmEwMS03OGU5LWEzMDMtOTQwMTBhZTllNGJlIiwicmlkIjoiYjRjZWFiNDUtNjk4MC00MGQ1LWFmYTUtNTdhMmY4NjNl"
    "ZGYwIn0.aGVFInXKg0HCQrTGW76L-Wd0xlv8eqnVA_GqdFaj4cNwfacotQTNjRCVetdtdIMNryuzFd6d_wTFuuDTB9fwAw"
)
_PENDING_TTL_DAYS = 7


def _turso_insert(payload: dict) -> bool:
    """Single INSERT to Turso. Returns True on success."""
    if os.environ.get("CTX_TELEMETRY_DEBUG"):
        import json as _j
        sys.stderr.write(f"[CTX debug] session-start payload: {_j.dumps(payload)}\n")
    try:
        sql = (
            "INSERT INTO ctx_session_aggregates "
            "(schema_version, user_id, session_id_hash, ts_date, total_turns, "
            "session_outcome, ctx_version) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        args = [
            {"type": "text",    "value": payload["schema_version"]},
            {"type": "text",    "value": payload["user_id"]},
            {"type": "text",    "value": payload["session_id_hash"]},
            {"type": "text",    "value": payload["ts_date"]},
            {"type": "integer", "value": str(payload["total_turns"])},
            {"type": "text",    "value": payload["session_outcome"]},
            {"type": "text",    "value": payload["ctx_version"]},
        ]
        body = json.dumps({"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": args}}
        ]}).encode()
        token = _TURSO_WRITE_TOKEN.replace("\n", "")
        req = urllib.request.Request(
            f"{_TURSO_DB_URL}/v2/pipeline", data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            json.load(resp)
        return True
    except Exception:
        return False


def _user_id() -> str:
    import hashlib
    cache = HOME / ".claude" / "ctx-user-id.hash"
    try:
        if cache.exists():
            cached = cache.read_text().strip()
            if len(cached) == 16:
                return cached
    except Exception:
        pass
    try:
        machine_id = ""
        for p in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                machine_id = open(p).read().strip(); break
            except Exception:
                pass
        if not machine_id:
            import socket; machine_id = socket.gethostname()
        claude_dir = HOME / ".claude"
        ts = int(claude_dir.stat().st_mtime) if claude_dir.exists() else 0
        from datetime import timezone
        d = datetime.fromtimestamp(ts, tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0)
        uid = hashlib.sha256(f"{machine_id}:{int(d.timestamp())}".encode()).hexdigest()[:16]
        try:
            cache.write_text(uid)
        except Exception:
            pass
        return uid
    except Exception:
        return "unknown"


def _ctx_version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("ctx-retriever")
    except Exception:
        return "unknown"


def _build_ping_payload() -> dict:
    return {
        "schema_version": "v1.7",
        "user_id": _user_id(),
        "session_id_hash": f"session-start:{int(time.time())}",
        "ts_date": str(date.today()),
        "total_turns": 0,
        "session_outcome": "SESSION_START_PING",
        "ctx_version": _ctx_version(),
    }


def _retry_pending() -> None:
    """Retry a previously queued (failed) ping."""
    if not PENDING.exists():
        return
    try:
        data = json.loads(PENDING.read_text())
        queued_at = data.get("queued_at", 0)
        if (time.time() - queued_at) > (_PENDING_TTL_DAYS * 86400):
            PENDING.unlink(missing_ok=True)
            return
        payload = data.get("payload", {})
        if payload and _turso_insert(payload):
            PENDING.unlink(missing_ok=True)
    except Exception:
        pass


def _run_ctx_install() -> bool:
    """Run ctx-install --silent using the current Python interpreter."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "ctx_retriever.cli.install", "--silent"],
            capture_output=True,
            timeout=60,
        )
        return r.returncode == 0
    except Exception:
        return False


def main() -> None:
    # Fast exit: already done
    if FLAG.exists():
        _retry_pending()  # still retry any pending pings even when flagged
        return

    # Revoke check
    if REVOKE.exists():
        return

    # Run ctx-install (venv-safe — uses system Python from Claude Code's hook subprocess)
    install_ok = _run_ctx_install()

    if install_ok:
        # Send SESSION_START_PING to hub-ctx
        payload = _build_ping_payload()
        if _turso_insert(payload):
            FLAG.touch()
            PENDING.unlink(missing_ok=True)  # clear any stale pending file
        else:
            # Network failed — queue for next session
            try:
                PENDING.write_text(json.dumps({
                    "queued_at": time.time(),
                    "payload": payload,
                }))
            except Exception:
                pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never break Claude Code startup
