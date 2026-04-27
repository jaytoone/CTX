#!/usr/bin/env python3
"""
chat-memory.py — UserPromptSubmit hook
claude-vault SQLite FTS5+Vector를 쿼리해 관련 과거 대화를 additionalContext로 주입.
CTX G1(git-memory)의 보완: 커밋되지 않은 세션 대화까지 커버.

Vector search: unix socket → vec-daemon.py (multilingual-e5-small, 384-dim)
Hybrid ranking: α=0.5 * cosine + (1-α) * bm25_norm
Fallback: BM25-only if daemon not running
"""
import json
import os
import re
import socket
import sqlite3
import sqlite_vec
import struct
import sys

VAULT_DB     = os.path.expanduser("~/.local/share/claude-vault/vault.db")
VEC_SOCK     = os.path.expanduser("~/.local/share/claude-vault/vec-daemon.sock")
MAX_RESULTS  = 3
MAX_CHARS_PER_MSG = 400
MIN_KEYWORD_LEN   = 3
MAX_CONTEXT_CHARS = 1200  # 전체 additionalContext 상한
HYBRID_ALPHA      = 0.5   # cosine weight; (1-alpha) = BM25 weight
VEC_TIMEOUT       = 0.3   # daemon connection timeout (seconds)

# SCOPE: "project" = current project only, "global" = all projects
# Default: project-scoped to avoid cross-project noise
SCOPE = os.environ.get("CHAT_MEMORY_SCOPE", "project")

# CHAT_MEMORY_EXTRA_PROJECTS: colon-separated extra project paths to include alongside current
# e.g. "/home/jayone/Project/Moat" or "/home/jayone/Project/Sales:/home/jayone/Project/Moat"
EXTRA_PROJECTS_RAW = os.environ.get("CHAT_MEMORY_EXTRA_PROJECTS", "")

STOPWORDS = {
    # English
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "that", "this", "these",
    "those", "with", "for", "from", "about", "into", "through", "what",
    "how", "why", "when", "where", "which", "who", "not", "and", "or",
    "but", "also", "just", "now", "then", "there", "here", "like",
    # Korean stopwords
    "이", "가", "은", "는", "을", "를", "에", "의", "와", "과",
    "로", "으로", "에서", "하는", "있는", "없는", "같은", "이런",
    "그런", "저런", "어떤", "모든", "각", "더", "또", "및",
    "오늘", "지금", "현재", "여기", "저기",
}


def extract_keywords(text: str, max_words: int = 6) -> str:
    """프롬프트에서 의미있는 키워드 추출.

    Regex breakdown:
      [a-zA-Z][a-zA-Z0-9]{1,} — alphanumeric tokens: BM25, G1, R@5 etc (2+ chars starting with letter)
      [a-zA-Z]{3,}            — pure English words (3+ chars)
      [가-힣]{2,}              — Korean syllable clusters (2+ chars, covers 쿼리·매칭·방법 etc)
    """
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]{1,}|[a-zA-Z]{3,}|[가-힣]{2,}", text)
    # Deduplicate while preserving order
    seen: set[str] = set()
    keywords = []
    for w in words:
        wl = w.lower()
        if wl not in STOPWORDS and wl not in seen:
            seen.add(wl)
            keywords.append(w)
    # FTS5 OR query: higher recall, FTS5 BM25 ranking handles relevance ordering
    return " OR ".join(keywords[:max_words])


def cwd_to_project(cwd: str) -> str:
    """cwd 경로를 vault project 컬럼 형식으로 변환.
    /home/jayone/Project/CTX → -home-jayone-Project-CTX
    """
    return cwd.replace("/", "-")


def get_query_embedding(query: str) -> list[float] | None:
    """Get query embedding from vec-daemon via Unix socket. Returns None if unavailable."""
    if not os.path.exists(VEC_SOCK):
        return None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(VEC_TIMEOUT)
        sock.connect(VEC_SOCK)
        req = json.dumps({"q": query}) + "\n"
        sock.sendall(req.encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        sock.close()
        resp = json.loads(buf.split(b"\n")[0].decode("utf-8"))
        if resp.get("ok"):
            return resp["emb"]
    except Exception:
        pass
    return None


def query_vault_vector(
    query_emb: list[float],
    project_filters: list[str] | None,
    limit: int,
    exclude_session_id: str | None = None,
) -> list[tuple]:
    """KNN vector search using sqlite-vec. Returns (msg_id, cosine_dist, role, content, ts, project)."""
    if not query_emb or not os.path.exists(VAULT_DB):
        return []
    try:
        import numpy as np
        conn = sqlite3.connect(f"file:{VAULT_DB}?mode=ro", uri=True, timeout=2.0)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        emb_bytes = bytes(struct.pack(f"{len(query_emb)}f", *query_emb))
        k = limit * 4  # over-fetch for project filter
        # Current-session exclusion: skip messages from the active session
        # to avoid retrieving this session's own turns as "past memory".
        sess_clause = "AND s.session_id != ?" if exclude_session_id else ""
        sess_params = [exclude_session_id] if exclude_session_id else []

        if project_filters:
            placeholders = ",".join("?" * len(project_filters))
            rows = conn.execute(f"""
                SELECT mv.rowid, mv.distance, m.role, m.content, m.timestamp, s.project
                FROM messages_vec mv
                JOIN messages m ON mv.rowid = m.id
                JOIN sessions s ON m.session_id = s.session_id
                WHERE mv.embedding MATCH ? AND mv.k = ?
                  AND s.project IN ({placeholders})
                  {sess_clause}
                  AND m.role IN ('user', 'assistant')
                  AND m.content NOT LIKE '[tool_use%'
                  AND m.content NOT LIKE '[tool_result%'
                  AND length(m.content) > 30
                ORDER BY mv.distance
                LIMIT ?
            """, [emb_bytes, k, *project_filters, *sess_params, limit]).fetchall()
        else:
            rows = conn.execute(f"""
                SELECT mv.rowid, mv.distance, m.role, m.content, m.timestamp, s.project
                FROM messages_vec mv
                JOIN messages m ON mv.rowid = m.id
                JOIN sessions s ON m.session_id = s.session_id
                WHERE mv.embedding MATCH ? AND mv.k = ?
                  {sess_clause}
                  AND m.role IN ('user', 'assistant')
                  AND m.content NOT LIKE '[tool_use%'
                  AND m.content NOT LIKE '[tool_result%'
                  AND length(m.content) > 30
                ORDER BY mv.distance
                LIMIT ?
            """, [emb_bytes, k, *sess_params, limit]).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def hybrid_merge(
    bm25_rows: list[tuple],
    vec_rows: list[tuple],
    max_results: int,
) -> list[tuple]:
    """
    Merge BM25 and vector results with hybrid scoring.
    bm25_rows: (project, role, content, timestamp) — FTS5 rank order (best first)
    vec_rows:  (rowid, distance, role, content, timestamp, project)
    Returns: (project, role, content, timestamp) sorted by hybrid score.
    """
    if not vec_rows:
        return bm25_rows[:max_results]

    # Normalize BM25: assign rank scores (1.0 for rank 0 → 0.0 for last)
    n_bm25 = len(bm25_rows)
    bm25_scores: dict[str, float] = {}
    for i, row in enumerate(bm25_rows):
        key = row[2][:120]  # content prefix as dedup key
        bm25_scores[key] = 1.0 - (i / max(n_bm25, 1))

    # Normalize vector: distance 0 → score 1.0; distance 2 → score 0.0 (cosine max=2)
    n_vec = len(vec_rows)
    vec_score_map: dict[str, tuple] = {}
    for row in vec_rows:
        dist = row[1]
        key = row[3][:120]
        vec_score = max(0.0, 1.0 - dist / 2.0)
        # Store (score, role, content, timestamp, project)
        vec_score_map[key] = (vec_score, row[2], row[3], row[4], row[5])

    # Merge: union of both result sets
    all_keys: set[str] = set(bm25_scores.keys()) | set(vec_score_map.keys())
    scored: list[tuple] = []
    for key in all_keys:
        b = bm25_scores.get(key, 0.0)
        v_data = vec_score_map.get(key)
        v = v_data[0] if v_data else 0.0
        hybrid = HYBRID_ALPHA * v + (1 - HYBRID_ALPHA) * b

        if v_data:
            _, role, content, ts, project = v_data
        else:
            # find in bm25_rows
            match = next((r for r in bm25_rows if r[2][:120] == key), None)
            if match is None:
                continue
            project, role, content, ts = match

        scored.append((hybrid, project, role, content, ts))

    scored.sort(key=lambda x: -x[0])
    # Return (project, role, content, timestamp)
    return [(s[1], s[2], s[3], s[4]) for s in scored[:max_results]]


def query_vault(keywords: str, project_filters: list[str] | None = None,
                exclude_session_id: str | None = None) -> list[tuple]:
    """FTS5로 관련 과거 대화 검색. tool_use 메시지 제외.
    project_filters: vault DB project 컬럼값 리스트 (e.g. ['-home-jayone-Project-CTX']).
                    None이면 전체 프로젝트 검색.
    exclude_session_id: current session's session_id — exclude to avoid retrieving
                        this session's own turns as "past memory".
    Returns: list of (project, role, content, timestamp)

    Adaptive threshold strategy:
    - Primary: rank < -17 (Youden J optimal, calibrated on n=194 real queries)
    - Same-day supplement: rank < -8 for today's messages (fixes 40% same-day hit rate)
      Same-day messages accumulate less vocabulary → weaker FTS5 rank → missed at -17.
    """
    if not keywords or not os.path.exists(VAULT_DB):
        return []

    # Fetch more than needed to allow dedup + recency re-ranking
    fetch_limit = MAX_RESULTS * 4

    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")

    # Current-session exclusion clause
    sess_clause = "AND s.session_id != ?" if exclude_session_id else ""
    sess_params_tuple = (exclude_session_id,) if exclude_session_id else ()

    try:
        conn = sqlite3.connect(f"file:{VAULT_DB}?mode=ro", uri=True, timeout=2.0)
        if project_filters:
            ph = ",".join("?" * len(project_filters))
            rows = conn.execute(
                f"""
                SELECT s.project, m.role, m.content, m.timestamp
                FROM messages_fts fts
                JOIN messages m ON fts.rowid = m.id
                JOIN sessions s ON m.session_id = s.session_id
                WHERE messages_fts MATCH ?
                  AND rank < -17
                  AND s.project IN ({ph})
                  {sess_clause}
                  AND m.role IN ('user', 'assistant')
                  AND m.content NOT LIKE '[tool_use%'
                  AND m.content NOT LIKE '[tool_result%'
                  AND length(m.content) > 30
                ORDER BY rank
                LIMIT ?
                """,
                (keywords, *project_filters, *sess_params_tuple, fetch_limit),
            ).fetchall()
            # Same-day supplement: looser threshold for today's messages
            same_day_rows = conn.execute(
                f"""
                SELECT s.project, m.role, m.content, m.timestamp
                FROM messages_fts fts
                JOIN messages m ON fts.rowid = m.id
                JOIN sessions s ON m.session_id = s.session_id
                WHERE messages_fts MATCH ?
                  AND rank < -8
                  AND m.timestamp >= ?
                  AND s.project IN ({ph})
                  {sess_clause}
                  AND m.role IN ('user', 'assistant')
                  AND m.content NOT LIKE '[tool_use%'
                  AND m.content NOT LIKE '[tool_result%'
                  AND length(m.content) > 30
                ORDER BY rank
                LIMIT ?
                """,
                (keywords, today_start, *project_filters, *sess_params_tuple, MAX_RESULTS * 2),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT s.project, m.role, m.content, m.timestamp
                FROM messages_fts fts
                JOIN messages m ON fts.rowid = m.id
                JOIN sessions s ON m.session_id = s.session_id
                WHERE messages_fts MATCH ?
                  AND rank < -17
                  {sess_clause}
                  AND m.role IN ('user', 'assistant')
                  AND m.content NOT LIKE '[tool_use%'
                  AND m.content NOT LIKE '[tool_result%'
                  AND length(m.content) > 30
                ORDER BY rank
                LIMIT ?
                """,
                (keywords, *sess_params_tuple, fetch_limit),
            ).fetchall()
            # Same-day supplement
            same_day_rows = conn.execute(
                f"""
                SELECT s.project, m.role, m.content, m.timestamp
                FROM messages_fts fts
                JOIN messages m ON fts.rowid = m.id
                JOIN sessions s ON m.session_id = s.session_id
                WHERE messages_fts MATCH ?
                  AND rank < -8
                  AND m.timestamp >= ?
                  {sess_clause}
                  AND m.role IN ('user', 'assistant')
                  AND m.content NOT LIKE '[tool_use%'
                  AND m.content NOT LIKE '[tool_result%'
                  AND length(m.content) > 30
                ORDER BY rank
                LIMIT ?
                """,
                (keywords, today_start, *sess_params_tuple, MAX_RESULTS * 2),
            ).fetchall()
        conn.close()
        rows = list(rows) + [r for r in same_day_rows if r not in rows]

        # Deduplicate: skip messages with identical first 120 chars
        seen: set[str] = set()
        deduped = []
        for row in rows:
            key = row[2][:120]
            if key not in seen:
                seen.add(key)
                deduped.append(row)

        # Recency re-rank: top half by FTS5 rank, then sort those by timestamp desc
        top_half = deduped[: min(len(deduped), MAX_RESULTS * 2)]
        top_half.sort(key=lambda r: r[3] or "", reverse=True)  # r[3] = timestamp
        return top_half[:MAX_RESULTS]

    except Exception:
        return []


def format_project(raw: str) -> str:
    """프로젝트 경로를 읽기 쉽게 변환: -home-jayone-Project-CTX → CTX"""
    parts = raw.strip("-").split("-")
    return parts[-1] if parts else raw


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = data.get("prompt", "")
    if not prompt or len(prompt) < 10:
        sys.exit(0)

    # A/B scaffold: control arm skips injection entirely (CTX_AB_DISABLE=1).
    # Dashboard uses the logged ab_skipped events to count control-arm sessions.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import ab_disabled, log_event
        if ab_disabled():
            log_event("ab_skipped", {"hook": "chat-memory", "reason": "CTX_AB_DISABLE"})
            sys.exit(0)
    except Exception:
        pass

    # Per-project filtering: cwd → project column key
    project_filters: list[str] | None = None
    if SCOPE == "project":
        cwd = data.get("cwd", "")
        if cwd:
            main_project = cwd_to_project(cwd)
            extras = [cwd_to_project(p.strip()) for p in EXTRA_PROJECTS_RAW.split(":") if p.strip()]
            project_filters = [main_project] + extras

    # Current session exclusion: don't retrieve this session's own turns as "past memory"
    current_session_id = data.get("session_id") or None

    keywords = extract_keywords(prompt)
    if not keywords:
        sys.exit(0)

    bm25_results = query_vault(keywords, project_filters=project_filters,
                               exclude_session_id=current_session_id)

    # Hybrid: try vector search if daemon is running
    import time as _time; _t0 = _time.perf_counter()
    query_emb = get_query_embedding(prompt[:500])
    if query_emb:
        vec_results = query_vault_vector(query_emb, project_filters, limit=MAX_RESULTS * 4,
                                         exclude_session_id=current_session_id)
        results = hybrid_merge(bm25_results, vec_results, MAX_RESULTS)
        search_mode = "hybrid"
    else:
        results = bm25_results
        search_mode = "bm25"

    # Opt-in telemetry: mode decision + daemon-down warning (privacy-safe, no content)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import log_event
        _dur = int((_time.perf_counter() - _t0) * 1000)
        log_event("mode_switch", {"hook": "chat-memory", "to_mode": search_mode, "duration_ms": _dur})
        if search_mode == "bm25":
            log_event("warning_fired", {"hook": "chat-memory", "kind": "daemon_down", "duration_ms": _dur})
    except Exception:
        pass

    # Cross-project fallback — OPT-IN only.
    # Previous default was: when project-scope returns 0, silently fall back
    # to global search across ALL projects. That leaked unrelated code-base
    # conversations into the current project's context (e.g. FromScratch
    # + Secure assistant turns appearing while working in CTX).
    # Now gated behind CHAT_MEMORY_GLOBAL_FALLBACK=1 to preserve project
    # isolation — the default behavior people actually want.
    global_fallback_used = False
    if (not results and project_filters
            and os.environ.get("CHAT_MEMORY_GLOBAL_FALLBACK") == "1"):
        bm25_results = query_vault(keywords, project_filters=None)
        if query_emb:
            vec_results = query_vault_vector(query_emb, None, limit=MAX_RESULTS * 4)
            results = hybrid_merge(bm25_results, vec_results, MAX_RESULTS)
        else:
            results = bm25_results
        global_fallback_used = bool(results)

    if not results:
        sys.exit(0)

    snippets = []
    total_chars = 0
    for project, role, content, _ts in results:
        proj_name = format_project(project)
        snippet = content[:MAX_CHARS_PER_MSG].replace("\n", " ").strip()
        line = f"[{role}@{proj_name}] {snippet}"
        if total_chars + len(line) > MAX_CONTEXT_CHARS:
            break
        snippets.append(line)
        total_chars += len(line)

    if not snippets:
        sys.exit(0)

    # Write CM injection items for utility-rate.py retrieval_event measurement
    try:
        import time as _time_cm
        _STOP_WORDS = frozenset([
            "that", "this", "with", "from", "have", "been", "were", "they",
            "their", "what", "when", "will", "more", "into", "then", "than",
            "some", "also", "about", "which", "there", "other",
        ])

        def _cm_tokens(text: str, n: int = 4) -> list:
            words = [w.strip(".,()[]{}:;!?\"'").lower() for w in text.split()]
            return [w for w in words if len(w) >= 5 and w not in _STOP_WORDS][:n]

        cm_items = [
            {"block": "chat_memory", "tokens": _cm_tokens(s), "subject": s[:80]}
            for s in snippets if s
        ]
        if cm_items:
            cm_injection = {
                "ts": _time_cm.time(),
                "items": cm_items,
                "retrieval_method": search_mode.upper(),
            }
            from pathlib import Path as _Path
            (_Path.home() / ".claude" / "last-cm-injection.json").write_text(
                json.dumps(cm_injection)
            )
    except Exception:
        pass

    first_snippet = snippets[0][:60].replace("\n", " ").strip()
    rest_count = len(snippets) - 1
    # Visible degradation signal: when daemon is unreachable, hybrid silently
    # falls back to BM25-only (happened 2026-04-11 → 2026-04-17, 6 days silent).
    # Suffix the mode tag so the user sees the regression in every prompt.
    mode_tag = search_mode
    if search_mode == "bm25":
        mode_tag = "bm25 ⚠ vec-daemon down (semantic rerank disabled)"
    if global_fallback_used:
        mode_tag += " ⚠ cross-project (no match in current project)"
    cm_header = f'> **CM** (chat memory/{mode_tag}): "{first_snippet}..." and {rest_count} more'

    body = "[CHAT-MEMORY] 관련 과거 대화:\n" + "\n---\n".join(snippets)
    context = cm_header + "\n\n" + body
    print(cm_header, file=sys.stderr)
    sys.stderr.flush()
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
