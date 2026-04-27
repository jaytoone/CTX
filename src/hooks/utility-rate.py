#!/usr/bin/env python3
"""
utility-rate.py — Stop hook that measures CTX injection utility (P1).

After each assistant turn, reads:
  1. The items bm25-memory injected into the turn (~/.claude/last-injection.json)
  2. The just-emitted assistant response from Claude Code's transcript_path
     (passed in the Stop hook's stdin JSON). Authoritative source — no race
     with claude-vault-incremental. Falls back to vault.db if transcript
     not available.

Substring-matches each item's distinctive tokens against the assistant's
response. Emits a `utility_measured` telemetry event with:
  - total_items: how many distinct items were injected
  - referenced_items: how many had at least one token substring-match in the response
  - by_block: per-block breakdown (g1 / g2_docs / g2_prefetch)

This is the R3 signal (outcome) described in the WTP analysis — it tells
us whether injected context was actually USED by the assistant, not just
surfaced. Dashboard presents this as "Utility rate" per block.

Privacy: no content logged; only counts + block names.
"""
import json
import os
import socket
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
LAST_INJECT = HOME / ".claude" / "last-injection.json"
VAULT_DB = HOME / ".local" / "share" / "claude-vault" / "vault.db"
WOW_STATE = HOME / ".claude" / ".ctx-wow-fired"
WOW_EVENT_FILE = HOME / ".claude" / ".ctx-wow-event.json"   # latest qualifying event (for dashboard banner)

# Wow-trigger gates
WOW_UTILITY_MIN = 0.70      # utility_rate ≥ 70%
WOW_AGE_MIN_DAYS = 14       # at least one referenced item ≥ 14 days old


# ── T1: Semantic similarity via vec-daemon ───────────────────────────
VEC_SOCK = HOME / ".local" / "share" / "claude-vault" / "vec-daemon.sock"
SEMANTIC_THRESHOLD = 0.85
# e5-small calibration (empirical, 2026-04-20):
#   related pairs:    cos ∈ [0.84, 0.90]  (item subject vs on-topic response chunk)
#   unrelated pairs:  cos ∈ [0.74, 0.78]  (shared "query:" prefix gives high baseline)
# 0.85 sits at the floor of "related", above the unrelated ceiling.


def _embed(text: str, timeout: float = 0.8) -> list | None:
    """Query vec-daemon for an embedding. Returns None on any failure."""
    if not VEC_SOCK.exists() or not text:
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(str(VEC_SOCK))
        s.sendall((json.dumps({"q": text[:1000]}) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        resp = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
        if resp.get("ok"):
            return resp.get("emb")
    except Exception:
        pass
    return None


def _cosine(a: list, b: list) -> float:
    """Cosine similarity for already-normalized vectors (vec-daemon normalizes)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _chunk_response(text: str, chunk_chars: int = 400, overlap: int = 80) -> list:
    """Split response into overlapping chunks so a long response doesn't dilute
    any single item's cosine. Chunks span paragraphs when possible."""
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for p in paragraphs:
        if len(p) <= chunk_chars:
            chunks.append(p)
        else:
            # Slide a window through long paragraphs
            start = 0
            while start < len(p):
                chunks.append(p[start:start + chunk_chars])
                start += chunk_chars - overlap
    return chunks[:20]   # hard cap — ceiling on vec-daemon calls per measurement


def _item_text(item: dict) -> str:
    """Reconstruct a natural-language description from an item's tokens.
    Prefer the raw subject if preserved; fall back to joining tokens."""
    if item.get("subject"):
        return item["subject"]
    tokens = item.get("tokens", [])
    return " ".join(tokens) if tokens else ""


def _log_event(event_type: str, payload: dict):
    try:
        sys.path.insert(0, str(HOME / ".claude" / "hooks"))
        from _ctx_telemetry import log_event
        log_event(event_type, payload)
    except Exception:
        pass


def _from_transcript(transcript_path: str) -> str:
    """Return concatenation of ALL assistant text blocks emitted since the
    last user message. Kept for backward compat with callers that only need text."""
    text, _ = _from_transcript_with_tools(transcript_path)
    return text


# Tool-use parameter keys whose string values carry meaningful content the
# assistant "referenced" via action. We flatten these into a single searchable
# text blob per turn and substring-match CTX-item tokens against it — this
# catches the case where the assistant reads a file CTX surfaced, or runs a
# command mentioning a CTX-surfaced symbol, without ever mentioning it in prose.
_TOOL_USE_STRING_KEYS = {
    "file_path", "notebook_path", "command", "pattern", "path",
    "description", "prompt", "query", "url", "old_string", "new_string",
    "subagent_type",
}


def _extract_tool_params(content: list) -> str:
    """Pull string values from tool_use blocks in a single assistant message.
    Returns a concatenation bounded to ~4000 chars to keep semantic-embed
    budget reasonable downstream. Non-string values (bools, ints) are skipped."""
    parts: list[str] = []
    for c in content or []:
        if not (isinstance(c, dict) and c.get("type") == "tool_use"):
            continue
        inp = c.get("input", {}) or {}
        # Tool name is itself useful context (Grep vs Edit vs Task)
        name = c.get("name", "")
        if name:
            parts.append(name)
        for k, v in inp.items():
            if k not in _TOOL_USE_STRING_KEYS:
                continue
            if isinstance(v, str):
                # Truncate long strings (Bash commands with huge pasted output)
                parts.append(v[:800])
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        parts.append(item[:400])
    joined = "\n".join(parts)
    return joined[:4000]   # cap total tool-params size per turn


def _from_transcript_with_tools(transcript_path: str) -> tuple:
    """Return (text, tool_params) — parallel streams of assistant output.

    - text: all text blocks since last user turn (what the user reads)
    - tool_params: flattened tool_use inputs since last user turn (what the
      assistant DID — file reads, edits, bash commands, grep patterns)

    Resets both on each 'user' entry so we only see the current turn.
    This is the authoritative, race-free source — transcript is written by
    Claude Code BEFORE any Stop hook fires."""
    if not transcript_path or not os.path.exists(transcript_path):
        return "", ""
    text_chunks: list[str] = []
    tool_chunks: list[str] = []
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line.strip())
                except Exception:
                    continue
                t = d.get("type")
                if t == "user":
                    text_chunks = []
                    tool_chunks = []
                    continue
                if t != "assistant":
                    continue
                msg = d.get("message", {})
                content = msg.get("content", [])
                if isinstance(content, str):
                    if content.strip():
                        text_chunks.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if c.get("type") == "text":
                            txt = c.get("text", "")
                            if txt and txt.strip():
                                text_chunks.append(txt)
                    tp = _extract_tool_params(content)
                    if tp:
                        tool_chunks.append(tp)
    except Exception:
        pass
    return "\n".join(text_chunks), "\n".join(tool_chunks)


def _from_vault() -> str:
    """Fallback: most recent assistant turn from vault.db.
    Note — vault.db updates on Stop via claude-vault-incremental (async),
    so this often lags the transcript by one turn. Kept as fallback only."""
    if not VAULT_DB.exists():
        return ""
    try:
        c = sqlite3.connect(f"file:{VAULT_DB}?mode=ro", uri=True, timeout=2.0)
        row = c.execute(
            "SELECT content FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        c.close()
        return (row[0] or "") if row else ""
    except Exception:
        return ""


def _read_stop_stdin() -> dict:
    """Stop hook receives {session_id, transcript_path, stop_hook_active} on stdin.
    Returns {} if stdin is empty (backward compat / manual invocation)."""
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


# ── retrieval_event schema (data flywheel — privacy-safe, local-first) ──────
_RETRIEVAL_EVENTS_LOG = HOME / ".claude" / "ctx-retrieval-events.jsonl"
_RETRIEVAL_META_PATH = HOME / ".claude" / "last-retrieval-meta.json"
_RETRIEVAL_EVENT_SCHEMA = "v1.5"
_USER_ID_CACHE = HOME / ".claude" / "ctx-user-id.hash"


def _get_user_id_hash() -> str:
    """Stable, non-reversible machine-level user_id for flywheel aggregation.

    Computed once, cached to ctx-user-id.hash.
    Source: SHA256(machine_id + install_month_epoch).
    - machine_id from /etc/machine-id (Linux) or /var/lib/dbus/machine-id or hostname fallback
    - install_month: mtime of ~/.claude truncated to 1st of month (prevents daily re-tracking)
    Privacy: not linkable to email/name; hash changes on reinstall.
    """
    try:
        if _USER_ID_CACHE.exists():
            cached = _USER_ID_CACHE.read_text().strip()
            if len(cached) == 16:
                return cached
    except Exception:
        pass
    try:
        import hashlib
        machine_id = ""
        for mid_path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                machine_id = open(mid_path).read().strip()
                break
            except Exception:
                pass
        if not machine_id:
            import socket
            machine_id = socket.gethostname()
        # install_month: mtime of ~/.claude truncated to month boundary
        claude_dir = HOME / ".claude"
        install_ts = int(claude_dir.stat().st_mtime) if claude_dir.exists() else 0
        # Truncate to month: set day=1, hour=0
        from datetime import datetime, timezone
        d = datetime.fromtimestamp(install_ts, tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0)
        install_month_epoch = str(int(d.timestamp()))
        uid = hashlib.sha256(f"{machine_id}:{install_month_epoch}".encode()).hexdigest()[:16]
        _USER_ID_CACHE.write_text(uid)
        return uid
    except Exception:
        return "unknown"

_HOOK_SOURCE_MAP = {
    "g1_decisions": "G1",
    "g2_docs": "G2_DOCS",
    "g2_prefetch": "G2_CODE",
    "chat_memory": "CM",
}


def _get_vault_stats() -> tuple:
    """Return (vault_entry_count, index_staleness_hours) for session_aggregate schema v1.4."""
    vault_count = None
    index_staleness = None
    try:
        if VAULT_DB.exists():
            import sqlite3 as _sqlite3
            conn = _sqlite3.connect(str(VAULT_DB))
            vault_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            conn.close()
    except Exception:
        pass
    try:
        # codebase-memory-mcp db (G2 freshness signal)
        for candidate in [
            HOME / ".local" / "share" / "codebase-memory" / "code-graph.db",
            HOME / ".local" / "share" / "codebase-memory-mcp" / "code-graph.db",
        ]:
            if candidate.exists():
                import time as _t
                age_s = _t.time() - candidate.stat().st_mtime
                index_staleness = int(age_s / 3600)
                break
    except Exception:
        pass
    return vault_count, index_staleness


def _write_retrieval_events(session_id, by_block, hits_by_mode, semantic_available, inj):
    """Write one retrieval_event record per active block to ctx-retrieval-events.jsonl.

    Privacy contract: no text, no query content, no file names — only numeric +
    categorical fields. Follows flywheel research schema (20260427-ctx-user-data-flywheel).
    """
    import hashlib
    try:
        meta = {}
        if _RETRIEVAL_META_PATH.exists():
            try:
                meta = json.loads(_RETRIEVAL_META_PATH.read_text())
            except Exception:
                pass

        ts_now = time.time()
        ts_unix_hour = int(ts_now / 3600)
        # Anonymize session_id — keep local correlation but non-reversible
        sid_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16] if session_id else "unknown"
        user_id = _get_user_id_hash()

        # session_turn_index: read current turn count before this turn is accumulated
        session_turn_index = 0
        try:
            if _SESSION_STATE_PATH.exists():
                st = json.loads(_SESSION_STATE_PATH.read_text())
                current_sid_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16] if session_id else ""
                if st.get("session_id_hash") == current_sid_hash:
                    session_turn_index = st.get("turns", 0)
        except Exception:
            pass

        for block, counts in by_block.items():
            hook_source = _HOOK_SOURCE_MAP.get(block, block.upper())
            block_meta = meta.get("blocks", {}).get(block, {})
            total = counts.get("total", 0)
            cited = counts.get("referenced", 0)

            record = {
                "schema_version": _RETRIEVAL_EVENT_SCHEMA,
                "ts_unix_hour": ts_unix_hour,
                "user_id": user_id,
                "session_id_hash": sid_hash,
                "hook_source": hook_source,
                "query_type": block_meta.get("query_type", "UNKNOWN"),
                "query_char_count": meta.get("query_char_count", inj.get("prompt_len", 0)),
                "candidates_returned": block_meta.get("candidates"),
                "retrieval_method": block_meta.get("retrieval_method", "UNKNOWN"),
                "duration_ms": block_meta.get("duration_ms"),
                "total_injected": total,
                "total_cited": cited,
                "utility_rate": round(cited / total, 4) if total > 0 else 0.0,
                "session_turn_index": session_turn_index,
                "vec_daemon_up": meta.get("vec_daemon_up", semantic_available),
                "bge_daemon_up": meta.get("bge_daemon_up", False),
                "top_score_bm25": block_meta.get("top_score_bm25"),
                "top_score_dense": block_meta.get("top_score_dense"),
            }
            with open(_RETRIEVAL_EVENTS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
    except Exception:
        pass


_SESSION_STATE_PATH = HOME / ".claude" / "ctx-session-state.json"
_SESSION_AGGREGATES_LOG = HOME / ".claude" / "ctx-session-aggregates.jsonl"


def _accumulate_session_aggregate(session_id, by_block, utility_rate):
    """Accumulate per-turn metrics into a running session state.

    On session_id change: flush previous session to ctx-session-aggregates.jsonl
    and start a fresh state for the new session.

    Privacy: session_id hashed, dates truncated to day, no content.
    """
    import hashlib
    from datetime import date as _date

    try:
        state = {}
        if _SESSION_STATE_PATH.exists():
            try:
                state = json.loads(_SESSION_STATE_PATH.read_text())
            except Exception:
                pass

        current_sid = session_id or "unknown"
        current_sid_hash = hashlib.sha256(current_sid.encode()).hexdigest()[:16]

        prev_sid_hash = state.get("session_id_hash", "")
        if prev_sid_hash and prev_sid_hash != current_sid_hash:
            # New session — flush aggregate for old session
            turns = state.get("turns", 0)
            agg = {
                "schema_version": _RETRIEVAL_EVENT_SCHEMA,
                "user_id": _get_user_id_hash(),
                "session_id_hash": prev_sid_hash,
                "ts_date": state.get("ts_date", str(_date.today())),
                "total_turns": turns,
                "total_injections": state.get("total_injections", 0),
                "mean_utility_rate": round(state.get("utility_rate_sum", 0) / turns, 4) if turns > 0 else 0.0,
                "hook_source_hist": state.get("hook_source_hist", {}),
                "retrieval_method_hist": state.get("retrieval_method_hist", {}),
                "session_outcome": "SHORT" if turns <= 2 else "NORMAL",
            }
            vault_count, index_staleness = _get_vault_stats()
            if vault_count is not None:
                agg["vault_entry_count"] = vault_count
            if index_staleness is not None:
                agg["index_staleness_hours"] = index_staleness
            bm25_sum = state.get("top_score_bm25_sum", 0.0)
            bm25_count = state.get("top_score_bm25_count", 0)
            if bm25_count > 0:
                agg["mean_top_score_bm25"] = round(bm25_sum / bm25_count, 4)
            qt_hist = state.get("query_type_hist", {})
            if qt_hist:
                agg["query_type_hist"] = qt_hist
            with open(_SESSION_AGGREGATES_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(agg) + "\n")
            state = {}

        # Accumulate current turn
        state["session_id_hash"] = current_sid_hash
        state.setdefault("ts_date", str(_date.today()))
        state["turns"] = state.get("turns", 0) + 1
        state["utility_rate_sum"] = state.get("utility_rate_sum", 0.0) + utility_rate

        # Total injections
        turn_injections = sum(v.get("total", 0) for v in by_block.values())
        state["total_injections"] = state.get("total_injections", 0) + turn_injections

        # Hook source histogram
        src_hist = state.get("hook_source_hist", {})
        for block in by_block:
            src = _HOOK_SOURCE_MAP.get(block, block.upper())
            src_hist[src] = src_hist.get(src, 0) + 1
        state["hook_source_hist"] = src_hist

        # Retrieval method histogram + query_type histogram + mean_top_score_bm25
        try:
            meta = json.loads(_RETRIEVAL_META_PATH.read_text()) if _RETRIEVAL_META_PATH.exists() else {}
            meth_hist = state.get("retrieval_method_hist", {})
            qt_hist = state.get("query_type_hist", {})
            for bdata in meta.get("blocks", {}).values():
                method = bdata.get("retrieval_method", "UNKNOWN")
                meth_hist[method] = meth_hist.get(method, 0) + 1
                qt = bdata.get("query_type")
                if qt and qt != "UNKNOWN":
                    qt_hist[qt] = qt_hist.get(qt, 0) + 1
                top_bm25 = bdata.get("top_score_bm25")
                if top_bm25 is not None:
                    state["top_score_bm25_sum"] = state.get("top_score_bm25_sum", 0.0) + top_bm25
                    state["top_score_bm25_count"] = state.get("top_score_bm25_count", 0) + 1
            state["retrieval_method_hist"] = meth_hist
            state["query_type_hist"] = qt_hist
        except Exception:
            pass

        _SESSION_STATE_PATH.write_text(json.dumps(state))
    except Exception:
        pass


_CM_INJECT_PATH = HOME / ".claude" / "last-cm-injection.json"


def main():
    if not LAST_INJECT.exists():
        return
    try:
        inj = json.loads(LAST_INJECT.read_text())
    except Exception:
        return
    items = inj.get("items", [])

    # Merge CM items from chat-memory.py (separate injection file)
    try:
        if _CM_INJECT_PATH.exists():
            cm_inj = json.loads(_CM_INJECT_PATH.read_text())
            # Age guard: same 10-min window as main injection
            if time.time() - cm_inj.get("ts", 0) <= 600:
                items = items + cm_inj.get("items", [])
                # Carry over ts from main injection for age check below
                _CM_INJECT_PATH.unlink(missing_ok=True)
    except Exception:
        pass

    if not items:
        return

    # Age guard: injection older than 10 min → probably stale, skip
    if time.time() - inj.get("ts", 0) > 600:
        return

    # Prefer Claude Code's transcript (race-free, authoritative); fall back
    # to vault.db only if transcript_path wasn't provided. This fixes the
    # "always scoring previous turn's response" bug where utility-rate and
    # claude-vault-incremental both ran async and utility-rate often read
    # vault.db BEFORE incremental finished writing the current turn.
    stop_input = _read_stop_stdin()
    transcript_path = stop_input.get("transcript_path", "")
    response, tool_params = _from_transcript_with_tools(transcript_path)
    if not response:
        # Fall back to vault (no tool-param recovery in this path — vault.db
        # stores text-only content; tool-param matching is transcript-only).
        response = _from_vault()
        tool_params = ""
    if not response and not tool_params:
        return
    # Case-insensitive substring match on distinctive tokens
    response_l = response.lower()
    tool_params_l = tool_params.lower()

    # ── T1: pre-compute response-chunk embeddings (one daemon call per chunk)
    # If vec-daemon is unreachable, we fall back to pure substring match per item.
    response_chunks = _chunk_response(response)
    chunk_embeddings = []
    semantic_available = False
    for chunk in response_chunks:
        emb = _embed(chunk)
        if emb:
            chunk_embeddings.append(emb)
            semantic_available = True

    by_block = {}
    total = 0
    referenced = 0
    # hits_by_mode tracks HOW each referenced item was matched:
    #   substring : token literally in response text
    #   semantic  : item vs response-chunk cosine ≥ threshold
    #   tool_use  : token literally in a tool_use parameter (file_path, cmd, ...)
    #   both_text : substring AND semantic both fired (text-only)
    # An item contributes to exactly one bucket (strongest-wins: both_text > substring > semantic > tool_use)
    hits_by_mode = {"substring": 0, "semantic": 0, "tool_use": 0, "both_text": 0}
    # referenced_by = counts from separate views for dashboard split:
    #   text_only : only text-match (substring or semantic) fired
    #   tool_only : only tool_use param match fired
    #   both      : text-match AND tool-match fired
    referenced_by = {"text_only": 0, "tool_only": 0, "both": 0}
    # by_age visualizes cross-session memory: are old decisions actually being
    # recalled, or is utility dominated by fresh items? Bands: 0-7d / 7-30d / 30d+.
    # Items without a date field (docs/prefetch) go into "no_date".
    by_age = {"0-7d": {"total": 0, "referenced": 0},
              "7-30d": {"total": 0, "referenced": 0},
              "30d+": {"total": 0, "referenced": 0},
              "no_date": {"total": 0, "referenced": 0}}
    max_referenced_age = 0    # oldest decision date among referenced items (for wow trigger)

    for it in items:
        block = it.get("block", "?")
        tokens = it.get("tokens", [])
        by_block.setdefault(block, {"total": 0, "referenced": 0})
        by_block[block]["total"] += 1
        total += 1

        # Substring check against response TEXT (what the user reads)
        sub_hit = any(len(t) >= 4 and t.lower() in response_l for t in tokens)

        # Semantic check (catches paraphrase, synonym, cross-language)
        sem_hit = False
        if semantic_available:
            item_text = _item_text(it)
            if item_text:
                item_emb = _embed(item_text)
                if item_emb:
                    max_sim = max((_cosine(item_emb, ce) for ce in chunk_embeddings),
                                  default=0.0)
                    sem_hit = max_sim >= SEMANTIC_THRESHOLD

        # Tool-use check — did the assistant's ACTIONS reference this item?
        # (Read target, Edit file, Bash command, Grep pattern, Task description)
        # This closes the blind spot where CTX informed tool choice but never
        # appeared in textual prose. Substring-only on tool params (embedding
        # file paths doesn't produce a meaningful cosine signal).
        tool_hit = (bool(tool_params_l)
                    and any(len(t) >= 4 and t.lower() in tool_params_l for t in tokens))

        text_hit = sub_hit or sem_hit
        hit = text_hit or tool_hit

        # Compute age band for EVERY item (referenced or not) so the denominator
        # is accurate — we need to know "of all 0-7d items injected, how many
        # got referenced", not just "of referenced items, what age".
        age_band = "no_date"
        item_age_days: int | None = None
        date_str = it.get("date")
        if date_str:
            try:
                item_age_days = (date.today() - datetime.fromisoformat(date_str).date()).days
                if item_age_days <= 7:
                    age_band = "0-7d"
                elif item_age_days <= 30:
                    age_band = "7-30d"
                else:
                    age_band = "30d+"
            except Exception:
                pass
        by_age[age_band]["total"] += 1

        if hit:
            referenced += 1
            by_block[block]["referenced"] += 1
            by_age[age_band]["referenced"] += 1
            # Mode attribution (strongest-wins text modes, then tool-only)
            if sub_hit and sem_hit:
                hits_by_mode["both_text"] += 1
            elif sub_hit:
                hits_by_mode["substring"] += 1
            elif sem_hit:
                hits_by_mode["semantic"] += 1
            else:
                hits_by_mode["tool_use"] += 1
            # Text-vs-tool split (separate dimension — an item can be in both)
            if text_hit and tool_hit:
                referenced_by["both"] += 1
            elif text_hit:
                referenced_by["text_only"] += 1
            else:
                referenced_by["tool_only"] += 1
            # Track oldest referenced decision date (for wow trigger)
            if item_age_days is not None and item_age_days > max_referenced_age:
                max_referenced_age = item_age_days

    _log_event("utility_measured", {
        "total_items": total,
        "referenced_items": referenced,
        "by_block": by_block,
        "by_age": by_age,
        "response_len": len(response),
        "hits_by_mode": hits_by_mode,
        "referenced_by": referenced_by,
        "tool_params_len": len(tool_params),
        "semantic_available": semantic_available,
    })

    # ── retrieval_event: structured telemetry schema (flywheel data asset) ──
    _write_retrieval_events(
        session_id=stop_input.get("session_id", ""),
        by_block=by_block,
        hits_by_mode=hits_by_mode,
        semantic_available=semantic_available,
        inj=inj,
    )

    # ── Wow-trigger: specific-old-recall + high-utility, fired once ever ──
    if total > 0:
        rate = referenced / total
        if (not WOW_STATE.exists()
                and rate >= WOW_UTILITY_MIN
                and max_referenced_age >= WOW_AGE_MIN_DAYS):
            # Terminal toast (stderr is visible in most shells)
            age_d = max_referenced_age
            msg_lines = [
                "",
                "  ╔══════════════════════════════════════════════════╗",
                f"  ║  ● CTX recalled a decision from {age_d:3d} days ago   ║",
                f"  ║    Claude actually used it ({int(rate*100)}% of injections).  ║",
                "  ║  → see the graph:  ctx                           ║",
                "  ╚══════════════════════════════════════════════════╝",
                "",
            ]
            print("\n".join(msg_lines), file=sys.stderr)

            wow = {
                "fired_at": time.time(),
                "age_days": age_d,
                "utility_rate": rate,
            }
            try:
                WOW_STATE.write_text(json.dumps(wow))
                WOW_EVENT_FILE.write_text(json.dumps(wow))
            except Exception:
                pass
            _log_event("wow_fired", {
                "total_items": total,
                "referenced_items": referenced,
                "response_len": len(response),
            })
        # Always keep WOW_EVENT_FILE fresh for dashboard banner (latest qualifying event)
        elif rate >= WOW_UTILITY_MIN and max_referenced_age >= WOW_AGE_MIN_DAYS:
            try:
                WOW_EVENT_FILE.write_text(json.dumps({
                    "fired_at": time.time(),
                    "age_days": max_referenced_age,
                    "utility_rate": rate,
                }))
            except Exception:
                pass

    # ── session_aggregate: per-session rollup (Stage 1 flywheel, second half) ──
    _accumulate_session_aggregate(
        session_id=stop_input.get("session_id", ""),
        by_block=by_block,
        utility_rate=referenced / total if total > 0 else 0.0,
    )

    # Consume the injection file so we don't double-count it on a second Stop
    try:
        LAST_INJECT.unlink()
    except Exception:
        pass


if __name__ == "__main__":
    main()
