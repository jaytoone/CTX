"""
session.py — Session-scoped helpers for bm25-memory orchestrator.

Provides:
  get_world_model(project_dir) -> (dead_ends, facts)
  get_session_decisions(project_dir) -> list[str]
  consume_pending_decisions(project_dir) -> list[str]
"""
import json
from pathlib import Path


def get_world_model(project_dir):
    """Load dead-ends and facts from .omc/world-model.json (--rich mode)."""
    wm_path = Path(project_dir) / ".omc" / "world-model.json"
    if not wm_path.exists():
        return [], []
    try:
        wm = json.loads(wm_path.read_text())
    except Exception:
        return [], []
    raw_de = wm.get("dead_ends", [])
    if isinstance(raw_de, dict):
        raw_de = []
    dead_ends = [
        f"  x {de.get('goal','')[:60]} -- {de.get('reason','')[:80]}"
        for de in raw_de[-5:]
    ]
    facts = []
    for fact in wm.get("known_facts", []):
        if isinstance(fact, dict):
            facts.append(f"  * {fact['fact'][:80]}")
        elif isinstance(fact, str) and not any(
            fact.startswith(p) for p in ("paper:", "README:", "uncertain:")
        ):
            facts.append(f"  * {fact[:80]}")
    return dead_ends, facts[-8:]


def get_session_decisions(project_dir):
    """Read .omc/session-decisions.md for uncommitted decisions."""
    p = Path(project_dir) / ".omc" / "session-decisions.md"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().split("\n")
        return [l.strip() for l in lines if l.strip().startswith(">")][-5:]
    except Exception:
        return []


def consume_pending_decisions(project_dir: str):
    """
    이전 세션 stop-decision-capture.py가 남긴 .pending-decisions.json 읽고 삭제.
    Returns list of formatted strings for additionalContext injection, or [].
    """
    slug = project_dir.replace("/", "-")
    pending_path = (
        Path.home() / ".claude" / "projects" / slug / "memory" / ".pending-decisions.json"
    )
    if not pending_path.exists():
        return []

    try:
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        captured_at = payload.get("captured_at", "")[:16]  # "2026-04-14T12:34"
    except Exception:
        try:
            pending_path.unlink(missing_ok=True)
        except Exception:
            pass
        return []

    # 읽은 즉시 삭제 (1회성 전달)
    try:
        pending_path.unlink(missing_ok=True)
    except Exception:
        pass

    if not decisions:
        return []

    lines = [f"[PENDING MEMORY] 이전 세션({captured_at}) 결정 후보 — MEMORY.md 업데이트 필요 여부 판단:"]
    for d in decisions:
        tag = d.get("tag", "")
        ctx = d.get("context", "")
        lines.append(f"  [{tag}] {ctx}")
    lines.append("→ 위 항목 중 MEMORY.md에 없는 중요한 결정이 있으면 즉시 Edit tool로 기록하세요.")
    return lines
