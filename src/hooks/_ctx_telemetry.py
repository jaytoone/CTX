#!/usr/bin/env python3
"""
_ctx_telemetry.py — opt-in event telemetry for CTX hooks.

Purpose: produce the data substrate for value-metric validation and dashboard
product design. Without event logs, there's no way to tell which hook paths
fire, how often, or whether users experience observable value (mode switches,
daemon warnings, stale-index repairs).

Privacy contract (non-negotiable):
- NEVER logs prompt content, file contents, retrieval result text, keywords, DB rows.
- Logs ONLY event types, counts, durations, ages, mode tags, coarse project id.
- Local-first (JSONL at ~/.claude/ctx-telemetry.jsonl); no network; no upload.

Opt-in gate (OFF by default):
- Env var:    CTX_TELEMETRY=1
- Or file:    ~/.claude/ctx-telemetry.enabled  (presence enables)
- When enabled: first call per process emits one-line stderr notice.

Usage from other hooks:
    from _ctx_telemetry import log_event
    log_event("mode_switch", {"hook": "chat-memory", "mode": "hybrid"})
    log_event("warning_fired", {"hook": "git-memory", "kind": "daemon_down"})
    log_event("auto_index", {"status": "indexed", "age_hours": 83})
"""
import json
import os
import sys
import time
from pathlib import Path

_HOME = Path(os.path.expanduser("~"))
_LOG = _HOME / ".claude" / "ctx-telemetry.jsonl"
_GATE_FILE = _HOME / ".claude" / "ctx-telemetry.enabled"
_NOTICE_STATE = _HOME / ".claude" / ".ctx-telemetry.notified"

# Schema version — bump on payload shape change
_SCHEMA = 1

# Coarse project id: last segment of CWD (no full path — avoids user/dir leaks)
def _project_id() -> str:
    try:
        cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        return Path(cwd).name[:40] or "unknown"
    except Exception:
        return "unknown"


def is_enabled() -> bool:
    """Telemetry fires only when explicitly opted in.

    Escape hatch for internal invocations (e.g., ctx-dashboard computing
    sample recalls): if CTX_DASHBOARD_INTERNAL=1 is set, suppress telemetry.
    Without this, dashboard-initiated hook calls would emit telemetry events,
    which the dashboard's reactive refresh would then detect as "new user
    events" → trigger another sample recompute → feedback loop.
    """
    if os.environ.get("CTX_DASHBOARD_INTERNAL") == "1":
        return False
    if os.environ.get("CTX_TELEMETRY") == "1":
        return True
    if _GATE_FILE.exists():
        return True
    return False


def ab_disabled() -> bool:
    """Return True if CTX hook injection should be skipped (A/B control arm).

    Controlled by CTX_AB_DISABLE=1 env var. When set, UserPromptSubmit hooks
    emit a lightweight 'ab_skipped' telemetry event and exit without producing
    any CTX block — simulating a session that never installed CTX.

    This is the *scaffold* for a time-saved A/B test: the operator flips this
    flag between sessions and the dashboard splits utility metrics by ab_group.
    """
    return os.environ.get("CTX_AB_DISABLE") == "1"


def ab_group() -> str:
    """Return the current A/B group tag.

    Priority: explicit CTX_AB_GROUP env var > inferred from CTX_AB_DISABLE.
    Values: 'control' (CTX off) | 'treatment' (CTX on) | 'ungrouped' (neither set).
    """
    g = os.environ.get("CTX_AB_GROUP", "").strip().lower()
    if g in ("control", "treatment"):
        return g
    if os.environ.get("CTX_AB_DISABLE") == "1":
        return "control"
    if os.environ.get("CTX_AB_GROUP") or _GATE_FILE.exists():
        # Gate file implies the operator is running an A/B; default the
        # treatment arm when no explicit group is set.
        return "treatment"
    return "ungrouped"


def _maybe_notify_once():
    """Print one-line notice to stderr the first time telemetry fires per user."""
    try:
        if _NOTICE_STATE.exists():
            return
        print(
            "[CTX telemetry enabled — logging to ~/.claude/ctx-telemetry.jsonl "
            "(opt out: unset CTX_TELEMETRY or rm ~/.claude/ctx-telemetry.enabled)]",
            file=sys.stderr,
        )
        _NOTICE_STATE.parent.mkdir(parents=True, exist_ok=True)
        _NOTICE_STATE.touch()
    except Exception:
        pass


# Whitelist of allowed payload keys per event type.
# Anything NOT in the whitelist is stripped before write (privacy guard).
_ALLOWED_KEYS = {
    "mode_switch": {"hook", "from_mode", "to_mode", "duration_ms"},
    "warning_fired": {"hook", "kind", "duration_ms"},
    "auto_index": {"status", "age_hours", "duration_ms"},
    "hook_invoked": {"hook", "path", "duration_ms", "prompt_len"},
    # bm25-memory: each CTX block that fired in a single invocation
    "block_fired": {"hook", "block", "count", "duration_ms"},
    # memory-keyword-trigger: decision keyword matched
    "decision_captured": {"hook", "category", "pattern_id"},
    # g2-fallback: grep result signal (0 results / test-only / sparse)
    "grep_signal": {"hook", "signal", "result_count"},
    # P1: utility-rate Stop hook — did assistant reference injected context?
    # by_block is a nested dict {block: {total, referenced}} — still counts-only,
    # no content. Sanitizer relaxes primitive guard for this event only.
    "utility_measured": {"total_items", "referenced_items", "by_block", "by_age", "response_len",
                         "hits_by_mode", "referenced_by", "tool_params_len", "semantic_available"},
    # Activation-moment trigger (Wow toast): high-utility + old-decision recall
    "wow_fired": {"total_items", "referenced_items", "response_len"},
    # A/B scaffold: UserPromptSubmit hook skipped injection because CTX_AB_DISABLE=1.
    # Presence of these events lets the dashboard compute control-arm sample counts.
    "ab_skipped": {"hook", "reason"},
}


def _sanitize(event_type: str, payload: dict) -> dict:
    """Strip any key not in the whitelist for this event type.
    Defensive: blocks accidental content leakage if a caller adds unsafe fields."""
    allowed = _ALLOWED_KEYS.get(event_type, set())
    # utility_measured's by_block / by_age / hits_by_mode / referenced_by are 1-level nested dicts of counts
    allow_nested_dict_for = {"utility_measured": {"by_block", "by_age", "hits_by_mode", "referenced_by"}}
    out = {}
    for k, v in (payload or {}).items():
        if k not in allowed:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            if isinstance(v, str) and len(v) > 80:
                v = v[:80]
            out[k] = v
            continue
        # Allow ONE level of nested dict for whitelisted keys (counts only).
        if (isinstance(v, dict)
                and k in allow_nested_dict_for.get(event_type, set())):
            safe_inner = {}
            for ik, iv in v.items():
                if not isinstance(ik, str) or len(ik) > 40:
                    continue
                if isinstance(iv, dict):
                    # 2nd level: must be primitive counts
                    safe_inner[ik] = {
                        jk: jv for jk, jv in iv.items()
                        if isinstance(jk, str) and isinstance(jv, (int, float))
                    }
                elif isinstance(iv, (int, float)):
                    safe_inner[ik] = iv
            out[k] = safe_inner
    return out


def log_event(event_type: str, payload: dict = None) -> None:
    """Append one JSONL line per event. Fails silent on any error — telemetry
    MUST NOT break the hook path."""
    if not is_enabled():
        return
    try:
        _maybe_notify_once()
        rec = {
            "ts": int(time.time()),
            "schema": _SCHEMA,
            "project": _project_id(),
            "ab_group": ab_group(),
            "type": event_type,
            **_sanitize(event_type, payload or {}),
        }
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with _LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # Silent — never break the hook
        pass


if __name__ == "__main__":
    # Quick self-test: `python3 _ctx_telemetry.py`
    # Requires gate to be enabled to actually write.
    if not is_enabled():
        print("telemetry DISABLED (set CTX_TELEMETRY=1 or touch ~/.claude/ctx-telemetry.enabled)")
        sys.exit(0)
    log_event("mode_switch", {"hook": "self-test", "from_mode": "bm25", "to_mode": "hybrid"})
    log_event("warning_fired", {"hook": "self-test", "kind": "daemon_down"})
    log_event("auto_index", {"status": "indexed", "age_hours": 5})
    # Show last 3 lines
    if _LOG.exists():
        lines = _LOG.read_text().strip().split("\n")[-3:]
        for l in lines:
            print(l)
