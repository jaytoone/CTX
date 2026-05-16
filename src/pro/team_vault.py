from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

from .gate import ProGate, team_id_from_key

_LOCAL_VAULT = Path.home() / ".local" / "share" / "claude-vault" / "vault.db"

# Turso table DDL (idempotent — run on first push/pull)
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ctx_team_vault (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id       TEXT    NOT NULL,
    source_hash   TEXT    NOT NULL,
    role          TEXT    NOT NULL,
    content       TEXT    NOT NULL,
    project       TEXT    DEFAULT '',
    session_id    TEXT    DEFAULT '',
    created_at    TEXT    NOT NULL,
    UNIQUE(team_id, source_hash)
)
"""


def _turso_execute(url: str, token: str, statements: list[dict]) -> dict:
    body = json.dumps({"requests": statements}).encode()
    req = urllib.request.Request(
        f"{url}/v2/pipeline",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _stmt(sql: str, args: list[Any] | None = None) -> dict:
    s: dict = {"type": "execute", "stmt": {"sql": sql}}
    if args:
        s["stmt"]["args"] = [{"type": "text", "value": str(a)} for a in args]
    return s


class TeamVault:
    def __init__(self, gate: ProGate):
        self._gate = gate

    def is_available(self) -> bool:
        return self._gate.tier() in ("pro", "team")

    def _vault_config(self) -> tuple[str, str, str]:
        """Return (team_id, turso_url, turso_token). Raises if not configured."""
        if not self.is_available():
            raise RuntimeError("Pro license required for team vault")
        info = self._gate.info()
        url = info.get("team_vault_url", "")
        token = info.get("team_vault_token", "")
        if not url or not token:
            raise RuntimeError(
                "Team vault not configured. Run:\n"
                "  ctx-pro team-vault init --url <turso-url> --token <token>"
            )
        key = info.get("license_key", "")
        tid = team_id_from_key(key)
        return tid, url, token

    def _ensure_table(self, url: str, token: str) -> None:
        _turso_execute(url, token, [_stmt(_CREATE_TABLE_SQL), {"type": "close"}])

    def push(self, limit: int = 200) -> dict:
        """Push recent vault.db messages to the team Turso table."""
        tid, url, token = self._vault_config()
        self._ensure_table(url, token)

        if not _LOCAL_VAULT.exists():
            return {"pushed": 0, "skipped": 0, "error": "local vault.db not found"}

        conn = sqlite3.connect(str(_LOCAL_VAULT))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT m.role, m.content, s.project, m.session_id "
                "FROM messages m LEFT JOIN sessions s ON m.session_id = s.session_id "
                "ORDER BY m.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return {"pushed": 0, "skipped": 0}

        stmts: list[dict] = []
        for r in rows:
            content = r["content"] or ""
            if not content.strip():
                continue
            src_hash = hashlib.sha256(f"{tid}:{content}".encode()).hexdigest()[:32]
            created_at = "now"
            stmts.append(_stmt(
                "INSERT OR IGNORE INTO ctx_team_vault "
                "(team_id, source_hash, role, content, project, session_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                [tid, src_hash, r["role"], content,
                 r["project"] or "", r["session_id"] or ""],
            ))
        stmts.append({"type": "close"})

        result = _turso_execute(url, token, stmts)
        pushed = sum(
            r.get("response", {}).get("result", {}).get("affected_row_count", 0)
            for r in result.get("results", [])
            if r.get("type") == "ok"
        )
        return {"pushed": pushed, "total": len(rows)}

    def pull(self, limit: int = 500) -> dict:
        """Pull team messages from Turso into local vault.db."""
        tid, url, token = self._vault_config()
        self._ensure_table(url, token)

        result = _turso_execute(url, token, [
            _stmt(
                "SELECT role, content, project, session_id, created_at "
                "FROM ctx_team_vault WHERE team_id = ? "
                "ORDER BY id DESC LIMIT ?",
                [tid, limit],
            ),
            {"type": "close"},
        ])

        rows_raw = (
            result.get("results", [{}])[0]
            .get("response", {})
            .get("result", {})
            .get("rows", [])
        )
        if not rows_raw:
            return {"pulled": 0}

        cols_raw = (
            result.get("results", [{}])[0]
            .get("response", {})
            .get("result", {})
            .get("cols", [])
        )
        cols = [c["name"] for c in cols_raw]

        if not _LOCAL_VAULT.exists():
            return {"pulled": 0, "error": "local vault.db not found"}

        conn = sqlite3.connect(str(_LOCAL_VAULT))
        inserted = 0
        try:
            team_session_id = f"team-pull-{tid}"
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, project, started_at, imported_at) "
                "VALUES (?, 'team-vault', datetime('now'), datetime('now'))",
                (team_session_id,),
            )
            for row in rows_raw:
                rd = dict(zip(cols, [v["value"] if isinstance(v, dict) else v for v in row]))
                content = rd.get("content", "")
                if not content:
                    continue
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO messages (session_id, role, content) "
                        "VALUES (?, ?, ?)",
                        (team_session_id, rd.get("role", "assistant"), content),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
        finally:
            conn.close()

        return {"pulled": inserted, "total": len(rows_raw)}

    def status(self) -> str:
        if not self.is_available():
            return "unavailable (Pro license required)"
        info = self._gate.info()
        url = info.get("team_vault_url", "")
        if not url:
            return "not configured  (run: ctx-pro team-vault init --url <url> --token <token>)"
        return f"configured  (url={url})"
