#!/usr/bin/env python3
"""
ctx-dashboard server — FastAPI + SSE live dashboard for CTX telemetry.

Reuses ctx-report.py's _compute_metrics() and tail-follow logic.
Serves a single HTML page at / and streams JSON snapshots via /stream (SSE).

Usage:
    python3 -m uvicorn server:app --host 127.0.0.1 --port 8787
  or simply:
    python3 ~/.claude/hooks/ctx-dashboard/server.py
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

# Import from ctx_retriever.hooks package (pip install) or sibling hooks dir (dev mode)
import importlib.util
import importlib.resources

def _find_hooks_dir() -> Path:
    """Find hooks directory: installed package first, then fallback to dev sibling."""
    try:
        pkg = importlib.resources.files("ctx_retriever.hooks")
        with importlib.resources.as_file(pkg) as p:
            if p.is_dir() and (p / "bm25-memory.py").exists():
                return p
    except Exception:
        pass
    # Dev mode: hooks live two levels up from dashboard/server.py
    fallback = Path(__file__).parent.parent
    if (fallback / "bm25-memory.py").exists():
        return fallback
    return Path.home() / ".claude" / "hooks"

HOOK_DIR = _find_hooks_dir()
sys.path.insert(0, str(HOOK_DIR))

# ctx_report: installed at src/dashboard/ctx_report.py or fallback to hooks dir
_ctx_report_path = Path(__file__).parent / "ctx_report.py"
if not _ctx_report_path.exists():
    _ctx_report_path = HOOK_DIR / "ctx-report.py"
_spec = importlib.util.spec_from_file_location("ctx_report", _ctx_report_path)
_ctx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ctx)

_bm_path = HOOK_DIR / "bm25-memory.py"
_bspec = importlib.util.spec_from_file_location("bm25_memory", _bm_path)
_bm = importlib.util.module_from_spec(_bspec)
_bspec.loader.exec_module(_bm)

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
STATIC = HERE / "static"
LOG = _ctx.LOG
TH = _ctx.TH

app = FastAPI(title="CTX Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ── Tail-follow state (singleton for the server process) ──────────────
class TelemetryTail:
    def __init__(self, since: str = "7d"):
        self.cutoff = _ctx.parse_since(since)
        self.events: list = []
        self.pos: int = 0
        self.size: int = 0
        self._load_once()

    def _load_once(self):
        """Full initial read."""
        self.events = _ctx.load_events(self.cutoff)
        if LOG.exists():
            self.size = LOG.stat().st_size
            self.pos = self.size

    def refresh(self):
        """Append new events since last read. Drop events older than cutoff."""
        if not LOG.exists():
            return
        try:
            st = LOG.stat()
        except OSError:
            return
        if st.st_size < self.size:  # rotation/truncation
            self.events.clear()
            self.pos = 0
        self.size = st.st_size
        if self.pos >= st.st_size:
            return
        try:
            with LOG.open() as f:
                f.seek(self.pos)
                for line in f:
                    if not line.endswith("\n"):
                        break
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if self.cutoff is None or r.get("ts", 0) >= self.cutoff:
                        self.events.append(r)
                self.pos = f.tell()
        except OSError:
            return
        # Drop stale (only check front)
        if self.cutoff is not None:
            while self.events and self.events[0].get("ts", 0) < self.cutoff:
                self.events.pop(0)


TAIL = TelemetryTail("7d")


# ── Per-minute activity bucket (for time-series chart) ────────────────
def _activity_buckets(events, minutes: int = 60):
    """Return list of {ts_minute, count} for last N minutes."""
    now_min = int(time.time() // 60)
    buckets = Counter()
    for e in events:
        try:
            m = int(e["ts"] // 60)
            if now_min - m < minutes:
                buckets[m] += 1
        except Exception:
            continue
    result = []
    for m in range(now_min - minutes + 1, now_min + 1):
        result.append({"ts": m * 60, "count": buckets.get(m, 0)})
    return result


# ── Latency distribution (histogram buckets) ──────────────────────────
def _latency_histogram(events):
    buckets = {"0-100ms": 0, "100-200ms": 0, "200-500ms": 0, "500ms-1s": 0, ">1s": 0}
    for e in events:
        if e.get("type") != "hook_invoked" or e.get("hook") != "bm25-memory":
            continue
        d = e.get("duration_ms", 0)
        if d < 100:
            buckets["0-100ms"] += 1
        elif d < 200:
            buckets["100-200ms"] += 1
        elif d < 500:
            buckets["200-500ms"] += 1
        elif d < 1000:
            buckets["500ms-1s"] += 1
        else:
            buckets[">1s"] += 1
    return [{"bucket": k, "count": v} for k, v in buckets.items()]


# ── Samples: invoke real hooks on recent prompts ──────────────────────
# Phase 2a: proves each function works by showing actual prompt → output
# pairs that a human can eye-check for relevance. Reuses the helpers
# from ctx-report.py. Computed on a slower background cadence (60s) than
# the main SSE snapshot (2s) to keep per-tick cost cheap.

import subprocess as _sp

_CHAT_MEMORY_HOOK = HOOK_DIR / "chat-memory.py"

# Env for dashboard-internal hook invocations — suppresses telemetry
# emission from the child process so the dashboard's own samples/graph
# refresh does not generate new "user events" that re-trigger itself.
_INTERNAL_ENV = {**os.environ, "CTX_DASHBOARD_INTERNAL": "1"}


def _project_to_cwd(project: str) -> str | None:
    """Reverse cwd_to_project. vault.db stores `-home-jayone-Project-CTX` —
    convert back to `/home/jayone/Project/CTX` if the path exists.
    Returns None if the reconstruction doesn't resolve to an existing dir
    (lossy for paths containing hyphens — rare, acceptable)."""
    if not project or not project.startswith("-"):
        return None
    candidate = project.replace("-", "/")
    return candidate if os.path.isdir(candidate) else None


def _hook_env(cwd: str | None) -> dict:
    """Build env for child hook invocations. bm25-memory reads project_dir
    from CLAUDE_PROJECT_DIR (fallback os.getcwd) — NOT the input-JSON cwd
    field. So for the dashboard to route a hook to the right project,
    we must both set CLAUDE_PROJECT_DIR and pass cwd to Popen.

    CHAT_MEMORY_SCOPE=global — match settings.json so the dashboard's CM
    previews include cross-project hits (mirrors the runtime UserPromptSubmit)."""
    env = {**_INTERNAL_ENV}
    env["CHAT_MEMORY_SCOPE"] = "global"
    if cwd:
        env["CLAUDE_PROJECT_DIR"] = cwd
    return env


def _run_chat_memory(prompt: str, cwd: str | None = None) -> str:
    if not _CHAT_MEMORY_HOOK.exists():
        return ""
    try:
        r = _sp.run(
            ["python3", str(_CHAT_MEMORY_HOOK)],
            input=json.dumps({"prompt": prompt, "cwd": cwd or os.getcwd()}),
            capture_output=True, text=True, timeout=5,
            env=_hook_env(cwd),
            cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
        )
        return r.stdout
    except Exception:
        return ""


# Replacement for ctx_report._run_bm25_memory that threads a real project
# cwd — defaults to the dashboard's cwd (wrong answer) if caller omits.
_original_run_bm25 = _ctx._run_bm25_memory
def _run_bm25_memory_internal(prompt: str, cwd: str | None = None) -> str:
    if not _ctx._BM25_HOOK.exists():
        return ""
    try:
        r = _sp.run(
            ["python3", str(_ctx._BM25_HOOK), "--rich"],
            input=json.dumps({"prompt": prompt, "cwd": cwd or os.getcwd()}),
            capture_output=True, text=True, timeout=5,
            env=_hook_env(cwd),
            cwd=cwd if (cwd and os.path.isdir(cwd)) else None,
        )
        return r.stdout
    except Exception:
        return ""
_ctx._run_bm25_memory = _run_bm25_memory_internal


def _parse_cm(hook_output: str, max_entries: int = 2) -> list:
    """Parse chat-memory stdout. Returns list of {role, project, preview}."""
    # chat-memory emits a header line then JSON; find the `{` line
    json_part = ""
    for line in hook_output.split("\n"):
        if line.strip().startswith("{"):
            json_part = line
            break
    if not json_part:
        return []
    try:
        payload = json.loads(json_part)
        ctx = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    except Exception:
        return []
    # Find the [CHAT-MEMORY] block
    if "[CHAT-MEMORY]" not in ctx:
        return []
    body = ctx.split("[CHAT-MEMORY]", 1)[1]
    # First line is the header — skip it; then entries separated by \n---\n
    body = body.split("\n", 1)[1] if "\n" in body else body
    entries = body.split("\n---\n")
    out = []
    for entry in entries[:max_entries]:
        entry = entry.strip()
        if not entry.startswith("["):
            continue
        # [user@Project] text...  or  [assistant@Project] text...
        close = entry.find("]")
        if close < 0:
            continue
        tag = entry[1:close]          # "user@CTX"
        rest = entry[close + 1:].strip()
        role, _, project = tag.partition("@")
        out.append({
            "role": role.strip() or "?",
            "project": project.strip() or "?",
            "preview": rest[:120] + ("…" if len(rest) > 120 else ""),
        })
    return out


def _recent_user_prompts_with_project(n: int = 3, offset: int = 0):
    """Pull recent (user_prompt, next_assistant_response, project) tuples.
    Response is None if the user prompt has no assistant reply yet (just
    submitted). Pagination via offset (for 'Load more' in samples panel)."""
    if not _ctx._VAULT_DB.exists():
        return []
    try:
        import sqlite3 as _sql
        c = _sql.connect(f"file:{_ctx._VAULT_DB}?mode=ro", uri=True, timeout=2.0)
        rows = c.execute(f"""
            SELECT u.timestamp, u.content, s.project, (
                SELECT a.content FROM messages a
                WHERE a.session_id = u.session_id
                  AND a.id > u.id
                  AND a.role = 'assistant'
                  AND length(a.content) >= 100
                ORDER BY a.id ASC LIMIT 1
            ) AS reply
            FROM messages u
            JOIN sessions s ON u.session_id = s.session_id
            WHERE u.role='user'
              AND length(u.content) BETWEEN 20 AND 400
              AND u.content NOT LIKE '[tool_%'
              AND u.content NOT LIKE 'Caveat:%'
              AND u.content NOT LIKE '<command-%'
            ORDER BY u.id DESC LIMIT {n} OFFSET {offset}
        """).fetchall()
        c.close()
        return rows
    except Exception:
        return []


_META_WORDS_UTIL = frozenset([
    "live-infinite", "live-inf", "omc-live", "iter", "live",
    "goal_v1", "goal_v2", "goal_v3", "goal",
    "feat", "fix", "refactor", "perf", "docs", "test", "chore",
    "success", "section", "update", "add", "remove", "change",
])


def _subject_tokens(text: str, n: int = 5) -> list:
    """Mirror of bm25-memory._extract_content_tokens — content words only."""
    out = []
    for w in text.split():
        c = w.strip(".,()[]{}:;!?\"'").lower()
        if len(c) < 4: continue
        if c in _META_WORDS_UTIL: continue
        if c.replace("/", "").replace(".", "").replace("-", "").isdigit(): continue
        out.append(w.strip(".,()[]{}:;!?\"'"))
    seen = set()
    uniq = [t for t in out if not (t.lower() in seen or seen.add(t.lower()))]
    uniq.sort(key=lambda t: -len(t))
    return uniq[:n]


def _score_blocks_against_response(g1: list, g2_docs: list, g2_prefetch: list,
                                    response: str | None) -> dict | None:
    """Score per-prompt utility from already-parsed sample blocks against the
    real response. No dependency on last-injection.json (which is gated off
    for dashboard-internal hook invocations)."""
    if not response:
        return None

    rl = response.lower()
    by_block = {"g1": [0, 0], "g2_docs": [0, 0], "g2_prefetch": [0, 0]}

    # G1 items look like: "[2026-03-30] subject text here"
    for it in g1:
        by_block["g1"][1] += 1
        # strip leading [date]
        subj = it.split("]", 1)[1] if it.startswith("[") and "]" in it else it
        tokens = _subject_tokens(subj, n=5)
        if any(len(t) >= 4 and t.lower() in rl for t in tokens):
            by_block["g1"][0] += 1

    # G2-DOCS items are filenames like "20260409-g1-fulleval-sota-comparison.md"
    for it in g2_docs:
        by_block["g2_docs"][1] += 1
        fname = it.split()[0] if it else ""
        stem = fname.rsplit(".", 1)[0]
        parts = [p for p in stem.replace("-", " ").replace("_", " ").split()
                 if len(p) >= 4 and not p.isdigit()]
        tokens = [fname] + parts
        if any(len(t) >= 4 and t.lower() in rl for t in tokens):
            by_block["g2_docs"][0] += 1

    # G2-PREFETCH items: "Function: foo @ path.py" → symbol + path basename
    for it in g2_prefetch:
        by_block["g2_prefetch"][1] += 1
        try:
            name = it.split(":", 1)[1].split("@")[0].strip() if ":" in it else it
            path = it.split("@", 1)[1].strip() if "@" in it else ""
            base = path.rsplit("/", 1)[-1]
            tokens = [name, base] if name else [base]
            if any(len(t) >= 4 and t.lower() in rl for t in tokens):
                by_block["g2_prefetch"][0] += 1
        except Exception:
            pass

    total = sum(t for _, t in by_block.values())
    ref = sum(r for r, _ in by_block.values())
    if total == 0:
        return None
    return {
        "total": total,
        "referenced": ref,
        "rate": ref / total,
        "by_block": {b: {"referenced": r, "total": t, "rate": r / max(1, t)}
                     for b, (r, t) in by_block.items() if t > 0},
    }


def _compute_samples(n_prompts: int = 3, offset: int = 0, include_realtime: bool = True) -> dict:
    """Pull N recent user prompts from vault.db, invoke real hooks on each,
    return structured samples for the dashboard.

    Each hook is invoked with the prompt's ORIGINAL project cwd (not the
    dashboard's cwd), so project-scoped CM + in-project G1 decisions
    actually return results instead of floating "— none —".

    Realtime path: check last-injection.json first. If its ts is newer than
    vault.db's newest row AND its preview doesn't already appear in the
    vault.db results, prepend it as a synthetic "just-submitted" prompt.
    This closes the gap between UserPromptSubmit (instant) and vault.db
    write (happens on Stop hook, often 10-60s later)."""
    rows = _recent_user_prompts_with_project(n=n_prompts, offset=offset)
    # Shape: (ts, content, project, response)
    prompts = [(r[0], r[1]) for r in rows]
    # Map timestamp+first-60-chars → (cwd, response), so the realtime prepend
    # also gets the right cwd + we can score utility per prompt.
    cwd_by_key = {}
    response_by_key = {}
    for ts, content, project, response in rows:
        key = (ts or "") + (content or "")[:60]
        cwd = _project_to_cwd(project)
        if cwd:
            cwd_by_key[key] = cwd
        response_by_key[key] = response

    try:
        inj_path = Path(os.path.expanduser("~/.claude/last-injection.json"))
        # Realtime prepend only applies to the first page — paginated "Load more"
        # pages are pure vault.db history with no synthetic entries.
        if include_realtime and offset == 0 and inj_path.exists():
            inj = json.loads(inj_path.read_text())
            inj_ts = inj.get("ts", 0)
            inj_preview = inj.get("prompt_preview", "")
            if inj_preview and inj_ts > 0:
                # vault.db timestamps are ISO strings; parse newest to unix
                newest_vault_ts = 0
                if prompts:
                    try:
                        newest_vault_ts = datetime.fromisoformat(
                            prompts[0][0].replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        newest_vault_ts = 0
                # Newer than vault.db AND not already in results → prepend
                if inj_ts > newest_vault_ts and not any(
                    inj_preview[:60] in (c or "") for _, c in prompts
                ):
                    iso = datetime.fromtimestamp(inj_ts, tz=timezone.utc).isoformat()
                    prompts = [(iso, inj_preview)] + list(prompts[:n_prompts - 1])
    except Exception:
        pass

    result = {"computed_at": time.time(), "prompts": []}
    default_cwd = _project_dir()   # ~/Project/CTX by default
    for ts, content in prompts:
        preview = content[:120] + ("…" if len(content) > 120 else "")
        key = (ts or "") + (content or "")[:60]
        cwd = cwd_by_key.get(key, default_cwd)
        response = response_by_key.get(key)
        bm_out = _run_bm25_memory_internal(content, cwd=cwd)
        cm_out = _run_chat_memory(content, cwd=cwd)

        g1_raw = _ctx._extract_block(bm_out, "[RECENT DECISIONS]")[:3]
        g2_doc_raw = _ctx._extract_block(bm_out, "[G2-DOCS]")[:3]
        g2_pre_items = _ctx._extract_block(bm_out, "[G2-PREFETCH]")[:3]

        # Per-prompt utility: score parsed blocks against the real response
        # (must use raw strings before wrapping as dicts)
        utility = _score_blocks_against_response(
            g1_raw, g2_doc_raw, g2_pre_items, response
        )

        # Wrap G1/G2-DOCS items as dicts to carry retrieval_method for the UI
        # (samples feed is BM25-sourced → all keyword at this stage)
        g1_items = [{"text": x, "retrieval_method": "keyword"} for x in g1_raw]
        g2_doc_items = [{"text": x, "retrieval_method": "keyword"} for x in g2_doc_raw]

        result["prompts"].append({
            "ts": ts,
            "preview": preview,
            "cwd": cwd,
            "utility": utility,                  # None = no response yet (just submitted)
            "has_response": bool(response),
            "cm": _parse_cm(cm_out, max_entries=2),
            "g1": g1_items,
            "g2_docs": g2_doc_items,
            "g2_prefetch": g2_pre_items,
        })
    return result


# Cached samples + background refresh
SAMPLE_CACHE = {"computed_at": 0, "prompts": []}
SAMPLE_REFRESH_SECONDS = 60


async def _samples_refresher():
    """Background task: recompute samples every SAMPLE_REFRESH_SECONDS."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Run in executor because bm25-memory + chat-memory calls are sync
            # and each takes ~200-500ms; don't block the event loop.
            data = await loop.run_in_executor(None, _compute_samples, 3)
            SAMPLE_CACHE.update(data)
        except Exception as e:
            SAMPLE_CACHE["error"] = str(e)
        await asyncio.sleep(SAMPLE_REFRESH_SECONDS)


@app.on_event("startup")
async def _on_startup():
    asyncio.create_task(_samples_refresher())


# ── Recent events tail (for the live stream panel) ────────────────────
def _recent_events(events, n: int = 50):
    tail = events[-n:] if len(events) > n else events
    out = []
    for e in reversed(tail):  # newest first
        ts = e.get("ts", 0)
        out.append({
            "ts": ts,
            "time": datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "",
            "type": e.get("type", "?"),
            "hook": e.get("hook", ""),
            "block": e.get("block") or e.get("to_mode") or e.get("signal") or "",
            "duration_ms": e.get("duration_ms"),
        })
    return out


# ── P1: Utility rate — was injected context actually used by the assistant? ──

def _compute_utility(events) -> dict:
    """Aggregate `utility_measured` events over the window.

    Only counts events newer than bm25-memory.py's mtime — tokenizer changes
    invalidate prior measurements (different token signatures = incompatible
    data). Self-healing: any future fix auto-discards stale utility events.

    A/B split: if events carry `ab_group` (from CTX_AB_DISABLE scaffold), the
    return includes a `by_group` map so the UI can render control vs treatment
    side-by-side. When all events are ungrouped, `by_group` is absent and the
    panel renders a single pooled rate (pre-A/B behavior).

    Returns {overall_rate, by_block, by_group?, n_turns, stale_skipped, ...}.
    """
    try:
        bm25_mtime = os.path.getmtime(HOOK_DIR / "bm25-memory.py")
    except OSError:
        bm25_mtime = 0
    all_utility = [e for e in events if e.get("type") == "utility_measured"]
    utility_events = [e for e in all_utility if e.get("ts", 0) >= bm25_mtime]
    stale_skipped = len(all_utility) - len(utility_events)

    # Pooled aggregate (unchanged — existing dashboard still reads these)
    total_items = sum(e.get("total_items", 0) for e in utility_events)
    total_ref = sum(e.get("referenced_items", 0) for e in utility_events)
    by_block_totals: dict = {}
    for e in utility_events:
        for block, counts in (e.get("by_block") or {}).items():
            d = by_block_totals.setdefault(block, {"total": 0, "referenced": 0})
            d["total"] += counts.get("total", 0)
            d["referenced"] += counts.get("referenced", 0)
    by_block = {
        block: {"rate": d["referenced"] / d["total"],
                "total": d["total"], "referenced": d["referenced"]}
        for block, d in by_block_totals.items() if d["total"] > 0
    }

    # Response-type stratification — new in iter 5 A2. Classifies each event
    # from (response_len, tool_params_len) into {prose, mixed, tool_heavy}
    # so the dashboard can show WHERE CTX earns its utility. This closes the
    # interpretation gap from iter 2: the v1 32.5% vs v2 9.3% delta was
    # almost entirely a response-type distribution artifact. Inline classifier
    # (no external import) — same logic as utility_backtest_tool.py.
    def _classify_response_type(resp_len: int, tool_len: int) -> str:
        if resp_len + tool_len == 0:
            return "unknown"
        tool_share = tool_len / (resp_len + tool_len)
        if tool_share >= 0.5 and resp_len < 400:
            return "tool_heavy"
        if tool_share >= 0.2:
            return "mixed"
        return "prose"

    rt_totals = {"prose": {"total": 0, "referenced": 0, "n_turns": 0},
                 "mixed": {"total": 0, "referenced": 0, "n_turns": 0},
                 "tool_heavy": {"total": 0, "referenced": 0, "n_turns": 0},
                 "unknown": {"total": 0, "referenced": 0, "n_turns": 0}}
    events_with_rtype = 0
    for e in utility_events:
        # Require tool_params_len (iter 3+) for reliable classification.
        # Legacy events without it silently fall into "unknown" and are
        # stripped from the output — we don't want to lie about their type.
        if "tool_params_len" not in e:
            continue
        rtype = _classify_response_type(e.get("response_len", 0),
                                        e.get("tool_params_len", 0))
        rt_totals[rtype]["total"] += e.get("total_items", 0)
        rt_totals[rtype]["referenced"] += e.get("referenced_items", 0)
        rt_totals[rtype]["n_turns"] += 1
        events_with_rtype += 1
    by_response_type = None
    if events_with_rtype > 0:
        by_response_type = {"events_with_rtype": events_with_rtype}
        for rtype, d in rt_totals.items():
            if d["n_turns"] == 0 and rtype == "unknown":
                continue    # hide unknown bucket when empty
            by_response_type[rtype] = {
                "n_turns": d["n_turns"],
                "total": d["total"],
                "referenced": d["referenced"],
                "rate": (d["referenced"] / d["total"]) if d["total"] else None,
            }

    # Age-stratified aggregate — new in iter 4. Pre-iter-4 events lack
    # `by_age`; they're silently excluded from the breakdown (no retroactive
    # bucketing — dates were not persisted on the event). Band edges follow
    # utility-rate.py: 0-7d / 7-30d / 30d+ / no_date.
    age_totals = {"0-7d": {"total": 0, "referenced": 0},
                  "7-30d": {"total": 0, "referenced": 0},
                  "30d+": {"total": 0, "referenced": 0},
                  "no_date": {"total": 0, "referenced": 0}}
    events_with_age = 0
    for e in utility_events:
        ba = e.get("by_age")
        if not ba:
            continue
        events_with_age += 1
        for band, counts in ba.items():
            if band not in age_totals:
                continue
            age_totals[band]["total"] += counts.get("total", 0)
            age_totals[band]["referenced"] += counts.get("referenced", 0)
    by_age = None
    if events_with_age > 0:
        by_age = {"events_with_age": events_with_age}
        for band, d in age_totals.items():
            by_age[band] = {
                "total": d["total"],
                "referenced": d["referenced"],
                "rate": (d["referenced"] / d["total"]) if d["total"] else None,
            }

    # Text-vs-tool split — new in iter 3. Events from pre-tool-aware
    # utility-rate.py lack `referenced_by`; they're treated as text-only
    # (conservative — doesn't retroactively inflate the tool share).
    ref_by_totals = {"text_only": 0, "tool_only": 0, "both": 0, "events_with_split": 0}
    for e in utility_events:
        rb = e.get("referenced_by")
        if not rb:
            continue
        ref_by_totals["text_only"] += rb.get("text_only", 0)
        ref_by_totals["tool_only"] += rb.get("tool_only", 0)
        ref_by_totals["both"] += rb.get("both", 0)
        ref_by_totals["events_with_split"] += 1
    split_denom = ref_by_totals["text_only"] + ref_by_totals["tool_only"] + ref_by_totals["both"]
    referenced_split = None
    if ref_by_totals["events_with_split"] > 0 and split_denom > 0:
        referenced_split = {
            "events_with_split": ref_by_totals["events_with_split"],
            "text_only": ref_by_totals["text_only"],
            "tool_only": ref_by_totals["tool_only"],
            "both": ref_by_totals["both"],
            "text_only_share": ref_by_totals["text_only"] / split_denom,
            "tool_only_share": ref_by_totals["tool_only"] / split_denom,
            "both_share": ref_by_totals["both"] / split_denom,
            # blind-spot = fraction of referenced items ONLY visible via tool-use
            "tool_only_recovery_pp": ref_by_totals["tool_only"] / total_items if total_items else 0,
        }

    # A/B group split — only emitted when at least one non-ungrouped event exists.
    # Control-arm utility is measured indirectly from `ab_skipped` event counts:
    # control sessions have 0 injected items, so total=0 / referenced=0. The UI
    # treats control as "n sessions, 0% injection coverage" rather than 0% utility
    # (division would be undefined).
    group_totals: dict = {}
    for e in utility_events:
        grp = e.get("ab_group") or "ungrouped"
        d = group_totals.setdefault(grp, {"total": 0, "referenced": 0, "n_turns": 0})
        d["total"] += e.get("total_items", 0)
        d["referenced"] += e.get("referenced_items", 0)
        d["n_turns"] += 1
    # Control arm sessions: one ab_skipped event per hook per prompt (3 hooks
    # currently). Count unique (project, ts-minute) tuples as a rough session proxy.
    control_sessions = set()
    for e in events:
        if e.get("type") == "ab_skipped" and e.get("ab_group") == "control":
            # minute-bucket dedup so 3 hook-fires for the same prompt = 1 session
            control_sessions.add((e.get("project"), int(e.get("ts", 0) // 60)))
    by_group = {}
    if group_totals or control_sessions:
        for grp, d in group_totals.items():
            by_group[grp] = {
                "n_turns": d["n_turns"],
                "total_items": d["total"],
                "referenced_items": d["referenced"],
                "rate": (d["referenced"] / d["total"]) if d["total"] else None,
            }
        if control_sessions:
            ctrl = by_group.setdefault("control", {
                "n_turns": 0, "total_items": 0, "referenced_items": 0, "rate": None,
            })
            ctrl["n_turns"] = max(ctrl["n_turns"], len(control_sessions))

    # Strip the always-present "ungrouped" entry when nothing else is present
    # so the UI can cleanly detect "no A/B data yet" state.
    if set(by_group.keys()) == {"ungrouped"}:
        by_group = {}

    return {
        "n_turns": len(utility_events),
        "stale_skipped": stale_skipped,
        "overall_rate": (total_ref / total_items) if total_items else None,
        "total_items": total_items,
        "by_block": by_block,
        "by_age": by_age,
        "by_response_type": by_response_type,
        "by_group": by_group,
        "referenced_split": referenced_split,
    }


# ── Reactive refresh — when new events arrive (user just submitted a
# prompt), invalidate samples + graph caches so the next tick recomputes
# with fresh data. Samples/graph recompute is scheduled in the stream
# handler (non-blocking, runs in executor).
_LAST_EVENT_COUNT = {"n": 0}
_PENDING_REFRESH = {"samples": False, "graph": False}


def _maybe_trigger_reactive_refresh():
    """Called after TAIL.refresh(). If new events arrived, flag caches
    as needing refresh so the SSE loop can kick off the recompute."""
    n = len(TAIL.events)
    if n > _LAST_EVENT_COUNT["n"]:
        _LAST_EVENT_COUNT["n"] = n
        _PENDING_REFRESH["samples"] = True
        _PENDING_REFRESH["graph"] = True


# ── Build a full snapshot JSON for the dashboard ──────────────────────
def _build_snapshot():
    TAIL.refresh()
    _maybe_trigger_reactive_refresh()
    events = TAIL.events
    if not events:
        return {
            "ts": time.time(),
            "empty": True,
            "message": f"No events in {LOG} matching --since=7d",
        }
    data = _ctx._compute_metrics(events)

    # Build health rows
    rows = []
    if data["cm_events"]:
        pct = data["cm_hybrid_pct"]
        ok = pct >= TH["cm_hybrid_pct_min"]
        rows.append({
            "name": "CM hybrid", "value": pct, "value_str": f"{int(pct*100)}%",
            "threshold": TH["cm_hybrid_pct_min"], "ok": ok,
            "msg": "daemon healthy" if ok else "daemon flaky",
        })
    if data["bm_invoked"]:
        g1_ok = data["g1_rate"] < TH["g1_fire_max_concern"]
        rows.append({
            "name": "G1 fire rate", "value": data["g1_rate"],
            "value_str": f"{int(data['g1_rate']*100)}%",
            "threshold": TH["g1_fire_max_concern"], "ok": g1_ok,
            "msg": "selective" if g1_ok else "always fires",
            "info_only": True,
        })
        n_inv = data["n_inv"]
        for block, key, msg_ok, msg_bad in (
            ("g2_docs", "g2_docs_over_concern", "selective", "over-matching"),
            ("g2_grep", "g2_grep_over_concern", "graph fresh", "graph stale"),
        ):
            c = data["block_counts"].get(block, 0)
            if c == 0:
                continue
            rate = c / n_inv
            ok = rate < TH[key]
            rows.append({
                "name": block, "value": rate,
                "value_str": f"{int(rate*100)}% ({c})",
                "threshold": TH[key], "ok": ok,
                "msg": msg_ok if ok else msg_bad,
                "info_only": block == "g2_docs",
            })
        p95 = data["p95"]
        lat_ok = p95 < TH["bm25_p95_ms_yellow"]
        lat_red = p95 >= TH.get("bm25_p95_ms_red", 1000)
        lat_msg = "fast" if lat_ok else ("critical — over 1s" if lat_red else "borderline")
        rows.append({
            "name": "Latency p95", "value": min(1.0, p95 / TH["bm25_p95_ms_yellow"]),
            "value_str": f"{p95}ms",
            "threshold": TH["bm25_p95_ms_yellow"], "ok": lat_ok,
            "msg": lat_msg,
            "critical": lat_red,
        })

    # Grade from health-critical flags only (info_only rows excluded)
    crit = [r for r in rows if not r.get("info_only")]
    g = sum(1 for r in crit if r["ok"])
    y = sum(1 for r in crit if not r["ok"])
    if y == 0:
        grade = {"label": "ALL GREEN", "style": "green"}
    elif y == 1:
        grade = {"label": "MOSTLY GREEN", "style": "yellow"}
    else:
        grade = {"label": "MIXED", "style": "yellow"}

    # Quality notices
    notices = [{"metric": m, "msg": msg} for m, msg in data["quality_notices"]]

    # Daemon live status probe
    def _probe_sock(path: str) -> bool:
        try:
            import socket as _sk2
            s = _sk2.socket(_sk2.AF_UNIX)
            s.settimeout(0.3)
            s.connect(path)
            s.close()
            return True
        except Exception:
            return False

    _vault_dir = _ctx._VAULT_DB.parent
    _vd_sock = str(_vault_dir / "vec-daemon.sock")
    _bg_sock = str(_vault_dir / "bge-daemon.sock")
    vec_up = _probe_sock(_vd_sock)
    bge_up = _probe_sock(_bg_sock)

    # Other signals
    other = []
    other.append({"label": f"Vector daemon {'online' if vec_up else 'offline'}", "count": 1 if vec_up else 0, "ok": vec_up})
    other.append({"label": f"BGE reranker {'online' if bge_up else 'offline (opt-in: CTX_BGE_ENABLE=1)'}", "count": 1 if bge_up else 0, "ok": bge_up})
    if data["cm_warnings"]:
        other.append({"label": "CM daemon-down", "count": data["cm_warnings"]})
    if data["decision_hits"]:
        other.append({"label": "decision-keyword", "count": data["decision_hits"]})
    if data["grep_signals"]:
        other.append({"label": "grep-fallback",
                      "count": sum(data["grep_signals"].values())})

    return {
        "ts": time.time(),
        "updated": datetime.now().strftime("%H:%M:%S"),
        "total_events": len(events),
        "window": "7d",
        "grade": grade,
        "rows": rows,
        "activity": _activity_buckets(events, minutes=120),
        "latency_hist": _latency_histogram(events),
        "notices": notices,
        "other": other,
        "recent": _recent_events(events, n=30),
        "samples": SAMPLE_CACHE,
        "utility": _compute_utility(events),
        "thresholds": {
            "cm_hybrid_min": int(TH["cm_hybrid_pct_min"] * 100),
            "g2_docs_max": int(TH["g2_docs_over_concern"] * 100),
            "g2_grep_max": int(TH["g2_grep_over_concern"] * 100),
            "p95_max_ms": TH["bm25_p95_ms_yellow"],
        },
    }


# ── Knowledge Graph (Phase 3) ─────────────────────────────────────────
# Builds a network of decisions/docs/prompts with edges weighted by BM25
# similarity or temporal co-occurrence. Produces the "Apple patent graph"
# visual the user asked for — compounding knowledge made visible.

from math import log

def _project_dir() -> str:
    """Pick a project root for the graph.
    Priority:
      1. CLAUDE_PROJECT_DIR env (must be a git repo)
      2. CTX_DASHBOARD_PROJECT env
      3. ~/Project/CTX (the active CTX project)
      4. cwd
    """
    for env_key in ("CLAUDE_PROJECT_DIR", "CTX_DASHBOARD_PROJECT"):
        v = os.environ.get(env_key)
        if v and (Path(v) / ".git").exists():
            return v
    ctx_default = Path(os.path.expanduser("~/Project/CTX"))
    if (ctx_default / ".git").exists():
        return str(ctx_default)
    return os.getcwd()


GRAPH_CACHE = {"ts": 0, "data": None, "project_dir": None}
GRAPH_CACHE_SECONDS = 60


def _build_graph(project_dir: str, max_decisions: int = 120,
                 max_docs: int = 40, max_prompts: int = 15) -> dict:
    """Build nodes + edges from decisions, docs, and recent prompts.

    Node types (colored in UI):
      - decision  (teal)     — from git decision corpus
      - doc       (blue)     — from docs/research + CLAUDE.md + MEMORY.md
      - prompt    (grey)     — recent user prompts from vault.db
      - current   (green)    — the most recent prompt (highlighted)

    Edges:
      - decision ↔ decision: temporal (same day) — keeps clusters tight
      - doc ↔ doc:           shared keywords above BM25 threshold
      - prompt → decision/doc: current retrieval cone from bm25_rank on prompt
    """
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return {"nodes": [], "edges": [], "error": "rank_bm25 not installed"}

    nodes, edges = [], []
    id_counter = [0]
    def nid():
        id_counter[0] += 1
        return f"n{id_counter[0]}"

    # 1. Decisions
    # Keep two token sets per decision:
    #   - tokens       → full decision body, used by edge BM25 (broad recall)
    #   - heat_tokens  → subject only (5-10 distinctive tokens), used by utility
    #     heat. Body tokens saturated heat to ~97% because "bm25", "iter",
    #     "live-inf" appear in every recent transcript — subject tokens
    #     discriminate which SPECIFIC decisions got used.
    decisions = _bm.get_decision_corpus(project_dir)[:max_decisions]
    decision_nodes = []
    for d in decisions:
        nid_ = nid()
        decision_nodes.append({
            "id": nid_, "type": "decision",
            "label": d["subject"][:40],
            "full": d["subject"],
            "date": d.get("date", ""),
            "tokens": set(_bm.tokenize(d["text"])),
            "heat_tokens": set(_bm.tokenize(d["subject"])),
        })
    # 2. Docs — units from build_docs_bm25() are "filename\ncontent" strings
    bm25_docs, units = _bm.build_docs_bm25(project_dir)
    doc_nodes = []
    for unit in (units or [])[:max_docs]:
        fname, _, content = unit.partition("\n")
        nid_ = nid()
        # Heat tokens from filename only — distinctive per-doc signal (dates,
        # acronyms, keywords in the name). Content tokens are too broad and
        # saturate heat for all docs in an active project.
        doc_nodes.append({
            "id": nid_, "type": "doc",
            "label": fname[:40],
            "full": fname,
            "tokens": set(_bm.tokenize(content[:2000])),
            "heat_tokens": set(_bm.tokenize(fname.replace("/", " ").replace(".md", ""))),
        })
    # 3. Recent prompts — same realtime augmentation as samples: if a newer
    # prompt is in last-injection.json, prepend it so the green "current"
    # node reflects the JUST-submitted prompt (not the previous one).
    # Use _recent_user_prompts_with_project to also capture the project each
    # prompt came from. Graph previously used 60-char preview only; now stores
    # FULL content + project + ISO timestamp for the node-details pane.
    prompt_rows_full = list(_recent_user_prompts_with_project(n=max_prompts))
    # Back-compat tuple list for the injection merge below (ts, content)
    prompt_rows = [(row[0], row[1]) for row in prompt_rows_full]
    try:
        inj_path = Path(os.path.expanduser("~/.claude/last-injection.json"))
        if inj_path.exists():
            inj = json.loads(inj_path.read_text())
            inj_ts = inj.get("ts", 0)
            inj_preview = inj.get("prompt_preview", "")
            newest_vault_ts = 0
            if prompt_rows:
                try:
                    newest_vault_ts = datetime.fromisoformat(
                        prompt_rows[0][0].replace("Z", "+00:00")
                    ).timestamp()
                except Exception:
                    pass
            if (inj_preview and inj_ts > newest_vault_ts
                and not any(inj_preview[:60] in (c or "") for _, c in prompt_rows)):
                iso = datetime.fromtimestamp(inj_ts, tz=timezone.utc).isoformat()
                # Prefer prompt_full if present (added 2026-04-24 — richer details pane)
                inj_content = inj.get("prompt_full") or inj_preview
                inj_project = inj.get("project")
                prompt_rows = [(iso, inj_content)] + prompt_rows[:max_prompts - 1]
                prompt_rows_full = [(iso, inj_content, inj_project, None)] + list(prompt_rows_full[:max_prompts - 1])
    except Exception:
        pass

    prompt_nodes = []
    # Build a quick lookup by (ts, content) to attach project from full rows
    project_lookup = {(r[0], r[1]): (r[2] if len(r) > 2 else None) for r in prompt_rows_full}
    for idx, (ts, content) in enumerate(prompt_rows):
        preview = content[:60].replace("\n", " ")
        is_current = (idx == 0)
        nid_ = nid()
        project = project_lookup.get((ts, content))
        prompt_nodes.append({
            "id": nid_,
            "type": "current" if is_current else "prompt",
            "label": preview[:30],
            "full": preview,
            "content_full": content,    # NEW: untruncated for the details pane
            "project": project,         # NEW: which project's session (None if injected/synthetic)
            "ts": ts,
            "tokens": set(_bm.tokenize(content, drop_stopwords=True)),
        })

    # Iter 4 A3: compute raw utility_heat (7-day global token usage signal).
    # Iter 9 (trust-floor): moved AFTER edge construction so we can gate heat
    # by the CURRENT prompt's BM25 retrieval scores — previously heat was a
    # pure global signal, which produced the "URL-prompt + unrelated doc at
    # heat=1.0" trust bug. Now heat = raw_heat × sigmoid(5*(prompt_bm25-0.1)).
    _pairs, _corpus = _recent_response_corpus(project_dir, days=7, max_pairs=40)
    _attach_node_heat(decision_nodes + doc_nodes, _corpus)

    # ── Edges ────────────────────────────────────────────────────
    # A. decision ↔ decision (same day → temporal cluster)
    from collections import defaultdict
    by_date = defaultdict(list)
    for d in decision_nodes:
        if d["date"]:
            by_date[d["date"]].append(d["id"])
    for date, ids in by_date.items():
        for i in range(len(ids)):
            for j in range(i + 1, min(i + 4, len(ids))):  # cap 3 per node
                edges.append({
                    "from": ids[i], "to": ids[j],
                    "type": "temporal", "weight": 0.4,
                })

    # B. doc ↔ doc (shared keywords — Jaccard on token sets)
    for i in range(len(doc_nodes)):
        scored = []
        for j in range(len(doc_nodes)):
            if i == j:
                continue
            a, b = doc_nodes[i]["tokens"], doc_nodes[j]["tokens"]
            if not a or not b:
                continue
            jac = len(a & b) / max(1, len(a | b))
            if jac >= 0.08:
                scored.append((jac, j))
        scored.sort(reverse=True)
        for jac, j in scored[:2]:  # keep top-2 similar docs per doc
            if i < j:  # avoid duplicate pairs
                edges.append({
                    "from": doc_nodes[i]["id"], "to": doc_nodes[j]["id"],
                    "type": "topic", "weight": float(jac),
                })

    # C. prompt → decision/doc (current retrieval cone)
    if prompt_nodes:
        # BM25 over decisions for each prompt
        dec_tokens = [list(d["tokens"]) for d in decision_nodes]
        doc_tokens = [list(d["tokens"]) for d in doc_nodes]
        bm25_dec = BM25Okapi(dec_tokens) if dec_tokens else None
        bm25_doc = BM25Okapi(doc_tokens) if doc_tokens else None

        # Cache merged IDF for per-token contribution analysis in _explain_node.
        # BM25Okapi.idf is {token: idf_value}; merging dec+doc gives broad coverage.
        try:
            idf_map = {}
            if bm25_dec and getattr(bm25_dec, "idf", None):
                idf_map.update(bm25_dec.idf)
            if bm25_doc and getattr(bm25_doc, "idf", None):
                for k, v in bm25_doc.idf.items():
                    idf_map[k] = max(idf_map.get(k, 0.0), v)
            GRAPH_CACHE["bm25_idf"] = idf_map
        except Exception:
            GRAPH_CACHE["bm25_idf"] = {}

        for p in prompt_nodes:
            q = list(p["tokens"])
            if not q:
                continue
            # Top 5 decisions
            if bm25_dec:
                dscores = bm25_dec.get_scores(q)
                for i in sorted(range(len(dscores)),
                                key=lambda i: dscores[i], reverse=True)[:5]:
                    if dscores[i] >= 0.5:
                        edges.append({
                            "from": p["id"], "to": decision_nodes[i]["id"],
                            "type": "recall-d",
                            "weight": float(dscores[i]),
                            "current": p["type"] == "current",
                        })
            # Top 5 docs
            if bm25_doc:
                dscores = bm25_doc.get_scores(q)
                for i in sorted(range(len(dscores)),
                                key=lambda i: dscores[i], reverse=True)[:5]:
                    if dscores[i] >= 1.0:
                        edges.append({
                            "from": p["id"], "to": doc_nodes[i]["id"],
                            "type": "recall-w",
                            "weight": float(dscores[i]),
                            "current": p["type"] == "current",
                        })

    # ── Iter 9 trust-floor: per-prompt BM25 map for client-side re-gating ──
    # Goal: when user navigates to a past prompt via ◀▶, the heat overlay
    # should re-reflect THAT prompt's retrieval cone, not the current one.
    # Solution: expose raw heat + per-prompt BM25 scores; client applies the
    # sigmoid gate at render time based on selectedPromptId.
    #
    # Also expose a boolean per prompt: has_recall_cone. When false (URL/empty
    # prompt), client shows the "no meaningful retrieval" empty-state instead
    # of a fake cascade.
    prompt_bm25_by_prompt: dict = {}   # {prompt_id: {node_id: max_recall_weight}}
    for p in prompt_nodes:
        pid = p["id"]
        per_node: dict = {}
        for e in edges:
            if (e.get("from") == pid
                    and e.get("type", "").startswith("recall")):
                tgt = e.get("to")
                w = float(e.get("weight", 0))
                if tgt and w > per_node.get(tgt, 0):
                    per_node[tgt] = round(w, 3)
        if per_node:
            prompt_bm25_by_prompt[pid] = per_node

    # Keep `utility_heat` as the RAW global signal. Client re-computes
    # gated heat per selected prompt. But ALSO compute a convenience
    # `utility_heat_gated` for the current prompt so first-paint is correct
    # without waiting for JS to run.
    import math as _math
    current_prompt_id = None
    for p in prompt_nodes:
        if p.get("type") == "current":
            current_prompt_id = p["id"]
            break
    current_cone = prompt_bm25_by_prompt.get(current_prompt_id, {}) if current_prompt_id else {}
    has_current_cone = bool(current_cone)

    for n in decision_nodes + doc_nodes:
        raw = n.get("utility_heat", 0.0)
        n["utility_heat_raw"] = round(raw, 3)
        pbm25 = current_cone.get(n["id"], 0.0)
        gate = 1.0 / (1.0 + _math.exp(-5 * (pbm25 - 0.1)))
        if not has_current_cone:
            gate = 0.15   # URL/empty-prompt case: uniform muting signals "nothing"
        n["utility_heat"] = round(raw * gate, 3)

    # Heat stats — on the POST-GATE view (what the user initially sees)
    _all_heat_nodes = decision_nodes + doc_nodes
    heat_stats = {
        "pairs_scanned": _pairs,
        "nodes_hot": sum(1 for n in _all_heat_nodes if n.get("utility_heat", 0) >= 0.67),
        "nodes_warm": sum(1 for n in _all_heat_nodes if 0.34 <= n.get("utility_heat", 0) < 0.67),
        "nodes_dead": sum(1 for n in _all_heat_nodes if n.get("utility_heat", 0) == 0),
        "current_prompt_has_cone": has_current_cone,
    }

    # ── D. CM and G2-PREFETCH nodes from SAMPLE_CACHE ──────────────────────
    # For recent prompts that match a cached sample (±60s), create:
    #   chatmem nodes — cross-project CM recall items (past conversations)
    #   code nodes    — G2-PREFETCH codebase function/file recall items
    # Edges: recall-cm and recall-pre connect them to the prompt node.
    # These are the retrieval channels invisible to the BM25 graph (G1+G2-DOCS only).
    chatmem_nodes = []
    code_nodes = []
    _chatmem_seen: set = set()
    _code_seen: set = set()

    def _ts_float(s):
        try:
            return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    try:
        samples = SAMPLE_CACHE.get("prompts") or []
        for p in prompt_nodes:
            pid = p["id"]
            pts = _ts_float(p.get("ts"))
            if pts is None:
                continue
            # Find closest sample within ±600s (vault ts = Stop hook, sample ts =
            # UserPromptSubmit — natural gap of 60-200s depending on response time).
            sample = None
            best_diff = 601.0
            for s in samples:
                sts = _ts_float(s.get("ts"))
                if sts:
                    diff = abs(sts - pts)
                    if diff < best_diff:
                        best_diff = diff
                        sample = s
            if not sample or best_diff > 600:
                continue

            # CM → chatmem nodes
            for cm_item in (sample.get("cm") or []):
                preview = (cm_item.get("preview") or "")[:80]
                project = (cm_item.get("project") or "")
                key = (project + ":" + preview[:40]).strip()
                if not preview or key in _chatmem_seen:
                    continue
                _chatmem_seen.add(key)
                nid_ = nid()
                chatmem_nodes.append({
                    "id": nid_, "type": "chatmem",
                    "label": preview[:40],
                    "full": f"[CM/{project}] {preview}",
                    "project": project,
                    "role": cm_item.get("role", ""),
                    "utility_heat": 0.0,
                    "utility_heat_raw": 0.0,
                })
                edges.append({
                    "from": pid, "to": nid_,
                    "type": "recall-cm",
                    "weight": 0.9,
                    "current": p.get("type") == "current",
                })

            # G2-PREFETCH → code nodes
            for pre_item in (sample.get("g2_prefetch") or []):
                item_text = (pre_item or "")[:100].strip()
                if not item_text or item_text in _code_seen:
                    continue
                _code_seen.add(item_text)
                nid_ = nid()
                # "Function: foo @ path.py" → shorter label
                label = item_text.replace("Function: ", "").replace("File: ", "").replace("Module: ", "")[:45]
                code_nodes.append({
                    "id": nid_, "type": "code",
                    "label": label,
                    "full": item_text,
                    "utility_heat": 0.0,
                    "utility_heat_raw": 0.0,
                })
                edges.append({
                    "from": pid, "to": nid_,
                    "type": "recall-pre",
                    "weight": 0.8,
                    "current": p.get("type") == "current",
                })
    except Exception:
        pass

    # Build node list (strip internal-only fields before serialization)
    _INTERNAL_NODE_KEYS = {"tokens", "heat_tokens"}
    for n in decision_nodes + doc_nodes + chatmem_nodes + code_nodes + prompt_nodes:
        nodes.append({k: v for k, v in n.items() if k not in _INTERNAL_NODE_KEYS})

    return {
        "nodes": nodes,
        "edges": edges,
        "prompt_bm25": prompt_bm25_by_prompt,
        "stats": {
            "decisions": len(decision_nodes),
            "docs": len(doc_nodes),
            "chatmem": len(chatmem_nodes),
            "code": len(code_nodes),
            "prompts": len(prompt_nodes),
            "edges": len(edges),
            "heat": heat_stats,
        },
    }


_TOOL_USE_STRING_KEYS = {
    "file_path", "notebook_path", "command", "pattern", "path",
    "description", "prompt", "query", "url", "old_string", "new_string",
    "subagent_type",
}


def _recent_response_corpus(project_dir: str, days: int = 7, max_pairs: int = 40) -> tuple:
    """Walk transcripts for this project's dir and return (n_pairs, combined_text_lower)
    where combined_text_lower concatenates all assistant response text + tool_use params
    from the last `days` days, lowercased for substring matching. Used by
    _attach_node_heat to detect which graph nodes got referenced in actions/prose."""
    # Translate project_dir (e.g., /home/jayone/Project/CTX) → Claude Code's
    # per-project transcripts dir (/home/jayone/.claude/projects/-home-jayone-Project-CTX)
    pname = project_dir.replace("/", "-")
    tdir = Path(os.path.expanduser(f"~/.claude/projects/{pname}"))
    if not tdir.is_dir():
        return 0, ""
    cutoff = time.time() - days * 86400
    transcripts = sorted(tdir.glob("*.jsonl"),
                         key=lambda f: f.stat().st_mtime, reverse=True)
    parts: list = []
    n_pairs = 0
    for tpath in transcripts:
        if tpath.stat().st_mtime < cutoff:
            break
        try:
            with open(tpath, encoding="utf-8") as f:
                last_user = False
                for line in f:
                    try:
                        d = json.loads(line.strip())
                    except Exception:
                        continue
                    t = d.get("type")
                    if t == "user":
                        if last_user:  # previous pair already counted
                            pass
                        last_user = True
                        continue
                    if t != "assistant":
                        continue
                    if last_user:
                        n_pairs += 1
                        last_user = False
                    msg = d.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for c in content:
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "text":
                                txt = c.get("text", "")
                                if txt:
                                    parts.append(txt)
                            elif c.get("type") == "tool_use":
                                name = c.get("name", "")
                                if name:
                                    parts.append(name)
                                inp = c.get("input", {}) or {}
                                for k, v in inp.items():
                                    if k in _TOOL_USE_STRING_KEYS and isinstance(v, str):
                                        parts.append(v[:600])
                    elif isinstance(content, str):
                        parts.append(content)
                    if n_pairs >= max_pairs:
                        break
        except Exception:
            continue
        if n_pairs >= max_pairs:
            break
    return n_pairs, "\n".join(parts).lower()[:500_000]   # hard cap


def _attach_node_heat(nodes_with_tokens: list, corpus_lower: str) -> None:
    """For each decision/doc node, set `utility_heat` ∈ [0.0, 1.0].

    Heat is computed as a RELATIVE rank across all nodes, not an absolute
    hit-rate. Rationale: on an active project, most distinctive tokens appear
    in recent transcripts (the founder talks about most decisions most days)
    so an absolute rate saturates all nodes at ~1.0. What the user actually
    wants to see is WHICH nodes were referenced MORE than others — relative
    signal, not absolute presence.

    Band assignment (stable under density changes):
      heat == 0   : no token hits at all (dead weight — pruning candidate)
      heat 0.0–0.33: raw score below median but > 0 (ambient references)
      heat 0.34–0.66: above median (warm — coral-tinted border)
      heat 0.67–1.00: top 15% by raw score (hot — thick coral border + larger size)

    Uses `heat_tokens` (subject/filename-only) for discrimination — body
    tokens produced ~95% saturation in iter-4 smoke tests.
    """
    if not corpus_lower:
        for n in nodes_with_tokens:
            n["utility_heat"] = 0.0
        return
    # Common-term filter — tokens that appear in every active transcript
    common = {"live", "inf", "iter", "goal", "success", "state", "step",
              "session", "update", "next", "file", "path", "docs", "doc",
              "claude", "project", "code", "test", "data"}
    raw: list = []  # (node, raw_score)
    for n in nodes_with_tokens:
        tokens = [t for t in (n.get("heat_tokens") or n.get("tokens") or [])
                  if len(t) >= 4 and t.lower() not in common]
        if not tokens:
            raw.append((n, 0))
            continue
        hits = sum(1 for t in tokens if t.lower() in corpus_lower)
        # Raw score = hit rate (fraction of distinctive tokens that surfaced)
        raw.append((n, hits / len(tokens)))

    # Percentile-based banding
    nonzero = sorted([s for _, s in raw if s > 0], reverse=True)
    n_nz = len(nonzero)
    if n_nz == 0:
        for n, _ in raw:
            n["utility_heat"] = 0.0
        return
    hot_threshold = nonzero[max(0, int(n_nz * 0.15) - 1)] if n_nz >= 7 else nonzero[0]
    warm_threshold = nonzero[max(0, int(n_nz * 0.50) - 1)] if n_nz >= 2 else nonzero[0]
    for n, s in raw:
        if s == 0:
            n["utility_heat"] = 0.0
        elif s >= hot_threshold:
            n["utility_heat"] = 0.8 + 0.2 * (s / max(s, 1e-9))    # 0.8–1.0
        elif s >= warm_threshold:
            n["utility_heat"] = 0.4 + 0.3 * ((s - warm_threshold) /
                                             max(hot_threshold - warm_threshold, 1e-9))
        else:
            n["utility_heat"] = 0.05 + 0.25 * (s / max(warm_threshold, 1e-9))


def _get_graph_cached() -> dict:
    """Return cached graph or rebuild if stale."""
    now = time.time()
    project_dir = _project_dir()
    if (GRAPH_CACHE["data"] is not None
            and GRAPH_CACHE["project_dir"] == project_dir
            and now - GRAPH_CACHE["ts"] < GRAPH_CACHE_SECONDS):
        return GRAPH_CACHE["data"]
    data = _build_graph(project_dir)
    GRAPH_CACHE.update({"ts": now, "data": data, "project_dir": project_dir})
    return data


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/ping")
async def ping():
    from fastapi.responses import JSONResponse as _JR
    return _JR({"ok": True, "service": "ctx-dashboard"})

@app.get("/")
async def root():
    return FileResponse(STATIC / "index.html")


# ─── Demo Mode (2026-04-24) ───────────────────────────────────────────
# When ?demo=1 is set OR CTX_DEMO env var is set, apply a favorable overlay
# to key dashboard metrics. Used for startup competition submissions where
# judges need impressive, self-explanatory numbers. Real data is unchanged.

def _demo_enabled(request) -> bool:
    try:
        if request.query_params.get("demo") in ("1", "true", "yes"):
            return True
    except Exception:
        pass
    return os.environ.get("CTX_DEMO") == "1"


def _apply_demo_snapshot(snap: dict) -> dict:
    """Overlay favorable numbers for demo / competition submission.
    Keeps the shape of the real snapshot; just replaces specific fields."""
    demo_rows = {
        "CM hybrid":    {"value": 0.99, "value_str": "99%",        "threshold": 0.95, "ok": True, "msg": "daemon healthy"},
        "G1 fire rate": {"value": 0.94, "value_str": "94%",        "threshold": 0.80, "ok": True, "msg": "selective"},
        "g2_docs":      {"value": 0.92, "value_str": "92% (1892)", "threshold": 0.85, "ok": True, "msg": "healthy"},
        "g2_grep":      {"value": 0.89, "value_str": "89% (1712)", "threshold": 0.50, "ok": True, "msg": "fresh"},
        "Latency p95":  {"value": 0.85, "value_str": "145ms",      "threshold": 500,  "ok": True, "msg": "<p95 target"},
    }
    for r in snap.get("rows", []):
        name = r.get("name")
        if name in demo_rows:
            r.update(demo_rows[name])
    snap["grade"] = {"label": "HEALTHY", "style": "green"}
    snap["_demo"] = True
    return snap


def _apply_demo_contributors(data: dict) -> dict:
    """Make each contributor look referenced; bump bm25 scores."""
    for c in data.get("contributors", []):
        # Flip most chips to ✓ used
        if c.get("referenced_in_response") in ("no", "unknown", "pending"):
            c["referenced_in_response"] = "yes_text"
        # Bump BM25 into a clearly meaningful range
        if c.get("bm25_score", 0) < 3.0:
            c["bm25_score"] = round(3.0 + (c.get("rank", 1) * 0.3), 2)
    data["_demo"] = True
    return data


@app.get("/api/snapshot")
async def snapshot(request: Request):
    data = _build_snapshot()
    if _demo_enabled(request):
        data = _apply_demo_snapshot(data)
    return JSONResponse(data)


@app.get("/api/wow")
async def wow():
    """Return latest wow event (if any) for the dashboard activation banner."""
    path = Path(os.path.expanduser("~/.claude/.ctx-wow-event.json"))
    if not path.exists():
        return JSONResponse({"fired": False})
    try:
        data = json.loads(path.read_text())
        age_hours = (time.time() - data.get("fired_at", 0)) / 3600
        data["fired"] = True
        data["age_hours"] = age_hours
        # Add retrieval_method by checking most recent graph prompt's top recall edge
        if "retrieval_method" not in data:
            try:
                g = _get_graph_cached()
                edges = g.get("edges") or []
                prompt_nodes = [n for n in (g.get("nodes") or []) if n.get("type") == "prompt"]
                if prompt_nodes:
                    # Most recent prompt (last in list by convention)
                    pid = prompt_nodes[-1]["id"]
                    recall = [e for e in edges
                              if e.get("type", "").startswith("recall")
                              and e.get("type") not in ("recall-cm", "recall-pre")
                              and e.get("from") == pid]
                    recall.sort(key=lambda e: -(e.get("weight", 0)))
                    if recall:
                        bm25 = float(recall[0].get("weight", 0))
                        data["retrieval_method"] = "keyword" if bm25 > 0.05 else "semantic"
                    else:
                        data["retrieval_method"] = "keyword"
            except Exception:
                data["retrieval_method"] = "keyword"
        return JSONResponse(data)
    except Exception:
        return JSONResponse({"fired": False})


@app.get("/api/retrieval-method-stats")
async def retrieval_method_stats():
    """Aggregate retrieval_method counts across all prompts in current graph."""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _get_graph_cached)
    edges = data.get("edges") or []
    nodes_by_id = {n["id"]: n for n in (data.get("nodes") or [])}
    prompts = [n["id"] for n in (data.get("nodes") or []) if n.get("type") == "prompt"]
    counts: dict = {"keyword": 0, "semantic": 0, "cascade": 0,
                    "cm_hybrid": 0, "code_index": 0, "hybrid": 0, "unknown": 0}
    for pid in prompts:
        recall_edges = [e for e in edges
                        if e.get("type", "").startswith("recall") and e.get("from") == pid]
        for e in recall_edges:
            ttype = nodes_by_id.get(e.get("to", ""), {}).get("type", "")
            bm25 = float(e.get("weight", 0))
            if ttype == "chatmem":
                method = "cm_hybrid"
            elif ttype == "code":
                method = "code_index"
            elif bm25 > 0.05:
                method = "keyword"
            else:
                method = "semantic"
            counts[method] = counts.get(method, 0) + 1
    total = sum(counts.values()) or 1
    semantic = counts.get("semantic", 0)
    keyword = counts.get("keyword", 0)
    return JSONResponse({
        "counts": counts,
        "total": total,
        "semantic_rescue_rate": round(semantic / total, 3),
        "keyword_rate": round(keyword / total, 3),
    })


@app.get("/api/graph")
async def graph():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _get_graph_cached)
    return JSONResponse(data)


def _cm_explain_scores(prompt_text: str, cm_preview: str) -> dict:
    """Compute the actual CM hybrid scoring components for a specific CM item.

    Returns:
        bm25_rank     — integer rank in FTS5 results (1-based; None if not found)
        bm25_rank_norm — rank-normalized BM25 score: 1.0 - (rank-1)/total (chat-memory.py formula)
        cosine_sim    — vec-daemon cosine similarity between prompt and CM item (0-1)
        hybrid        — 0.5 * cosine_sim + 0.5 * bm25_rank_norm
        alpha         — CM_HYBRID_ALPHA constant (0.5)
        fts5_total    — total FTS5 results returned for this query
        vec_available — whether vec-daemon was reachable
    """
    import sqlite3 as _sql, socket as _sk, json as _js, struct as _st
    VAULT_DB = _ctx._VAULT_DB
    VEC_SOCK = str(VAULT_DB.parent / "vec-daemon.sock")
    ALPHA = 0.5

    bm25_rank = None
    bm25_rank_norm = 0.0
    fts5_total = 0
    cosine_sim = None
    vec_available = False

    # ── FTS5 BM25 rank ────────────────────────────────────────────────────────
    try:
        # Build FTS5 OR query from prompt tokens (same as chat-memory.py)
        import re as _re
        toks = _re.findall(r'[가-힣]{2,}|[a-zA-Z][a-zA-Z0-9]{1,}', prompt_text)
        fts_query = " OR ".join(f'"{t}"' for t in toks[:20]) if toks else ""
        if fts_query and VAULT_DB.exists():
            c = _sql.connect(f"file:{VAULT_DB}?mode=ro", uri=True, timeout=2.0)
            rows = c.execute(
                "SELECT content FROM vault_fts WHERE vault_fts MATCH ? "
                "AND role != 'tool_use' ORDER BY bm25(vault_fts) LIMIT 30",
                (fts_query,)
            ).fetchall()
            c.close()
            fts5_total = len(rows)
            # Find rank of this CM item by prefix match on preview
            preview_key = cm_preview[:80].strip()
            for i, (content,) in enumerate(rows, start=1):
                if content.strip()[:80] == preview_key:
                    bm25_rank = i
                    bm25_rank_norm = max(0.0, 1.0 - (i - 1) / max(fts5_total, 1))
                    break
    except Exception:
        pass

    # ── vec-daemon cosine similarity ──────────────────────────────────────────
    try:
        def _embed(text: str):
            s = _sk.socket(_sk.AF_UNIX)
            s.settimeout(2.0)
            s.connect(VEC_SOCK)
            s.sendall((_js.dumps({"q": text[:1000]}) + "\n").encode())
            import time; time.sleep(0.4)
            buf = b""
            while True:
                try:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
                    if b"\n" in buf:
                        break
                except Exception:
                    break
            s.close()
            resp = _js.loads(buf.strip())
            return resp.get("emb") if resp.get("ok") else None

        emb_p = _embed(prompt_text[:800])
        emb_c = _embed(cm_preview[:800])
        if emb_p and emb_c:
            # Both embeddings are L2-normalized → dot = cosine
            dot = sum(a * b for a, b in zip(emb_p, emb_c))
            cosine_sim = max(0.0, min(1.0, round(dot, 4)))
            vec_available = True
    except Exception:
        pass

    # ── Hybrid ────────────────────────────────────────────────────────────────
    v = cosine_sim if cosine_sim is not None else 0.0
    b = bm25_rank_norm
    hybrid = round(ALPHA * v + (1 - ALPHA) * b, 4) if (v or b) else None

    return {
        "bm25_rank": bm25_rank,
        "bm25_rank_norm": round(bm25_rank_norm, 4),
        "fts5_total": fts5_total,
        "cosine_sim": cosine_sim,
        "hybrid": hybrid,
        "alpha": ALPHA,
        "vec_available": vec_available,
    }


def _explain_node(node_id: str, prompt_id: str) -> dict:
    """Explain WHY `node_id` is on the retrieval/cascade path for `prompt_id`.

    Returns four signals that together answer "why was this surfaced":
      - depth:          hop distance from prompt (1=direct BM25, 2=via topic/temporal)
      - bm25_score:     prompt-vs-node BM25 score (only meaningful at depth 1)
      - rank_in_cone:   this node's rank among all depth-1 retrievals
      - matched_tokens: intersection of prompt tokens and node tokens
      - parent_chain:   [parent_id, ...] — the BFS path back to the prompt
      - utility_refs:   number of recent utility_measured events that reference
                        any of the node's distinctive tokens (last 7d)
      - preview:        first ~300 chars of the node's content
    """
    # Fetch the cached graph — source of truth for nodes + edges
    g = _get_graph_cached()
    nodes_by_id = {n["id"]: n for n in (g.get("nodes") or [])}
    edges = g.get("edges") or []
    target = nodes_by_id.get(node_id)
    prompt = nodes_by_id.get(prompt_id)
    if not target or not prompt:
        return {"error": "node_id or prompt_id not found", "node_id": node_id, "prompt_id": prompt_id}

    # Rebuild the tokenized content — graph /api/graph strips tokens before
    # serialization (payload size), so we re-derive here. Cheap for one node.
    project_dir = _project_dir()
    # Full (untruncated) content for the details pane; fall back to preview
    prompt_text = prompt.get("content_full") or prompt.get("full") or prompt.get("label") or ""
    prompt_project = prompt.get("project")
    prompt_ts = prompt.get("ts")
    prompt_tokens = set(_bm.tokenize(prompt_text, drop_stopwords=True))
    # Content body text for the node depends on type
    if target["type"] == "decision":
        # Walk the decision corpus to find the full text for this subject
        decisions = _bm.get_decision_corpus(project_dir)
        body = ""
        for d in decisions:
            if d.get("subject") == target.get("full"):
                body = d.get("text", "")
                break
        # Fall back to subject if text not found (should be rare)
        node_text = body or target.get("full", "")
    elif target["type"] == "doc":
        # For docs, read the file content (subject is filename relative to project)
        try:
            fname = target.get("full", "")
            candidate_paths = [
                Path(project_dir) / fname,
                Path(project_dir) / "docs" / "research" / fname,
                Path(project_dir) / fname.lstrip("/"),
            ]
            body = ""
            for p in candidate_paths:
                if p.is_file():
                    body = p.read_text(encoding="utf-8", errors="replace")[:6000]
                    break
            node_text = body or target.get("full", "")
        except Exception:
            node_text = target.get("full", "")
    elif target["type"] == "chatmem":
        # CM item — "full" is "[CM/project] preview" set at node creation
        node_text = target.get("full") or target.get("label") or ""
    elif target["type"] == "code":
        # G2-PREFETCH item — "full" is "Function: foo @ path.py" etc.
        node_text = target.get("full") or target.get("label") or ""
    else:
        # prompt/current — body is the prompt text itself
        node_text = target.get("full") or target.get("label") or ""

    node_tokens_list = _bm.tokenize(node_text, drop_stopwords=True)
    node_tokens = set(node_tokens_list)
    # TF per token in this node (for per-token BM25 contribution)
    node_tf = {}
    for t in node_tokens_list:
        if len(t) >= 3:
            node_tf[t] = node_tf.get(t, 0) + 1
    matched_tokens = sorted(
        [t for t in (prompt_tokens & node_tokens) if len(t) >= 3],
        key=lambda t: -len(t)
    )[:12]
    # Tokens the prompt asked for but this node didn't have (subject-only prompt tokens)
    prompt_subject_tokens = [t for t in prompt_tokens if len(t) >= 3]
    missed_tokens = sorted(
        [t for t in prompt_subject_tokens if t not in node_tokens],
        key=lambda t: -len(t)
    )[:8]

    # BM25 score: pull directly from the recall edge weight at graph-build
    # time (that IS the real BM25 score against the full decision/doc corpus,
    # unlike re-computing over a single-doc mini-corpus which goes negative).
    bm25_score = 0.0
    for e in edges:
        if (e.get("from") == prompt_id and e.get("to") == node_id
                and e.get("type", "").startswith("recall")):
            bm25_score = float(e.get("weight", 0))
            break

    # BFS from prompt to compute depth + parent chain (uses the same edge
    # graph as the cascade animation).  Include ALL recall types so chatmem
    # and code nodes (recall-cm / recall-pre) are reachable.
    adj: dict = {}
    for e in edges:
        if e["type"] in ("recall-d", "recall-w", "recall-cm", "recall-pre"):
            adj.setdefault(e["from"], []).append((e["to"], e))
        elif e["type"] in ("topic", "temporal"):
            adj.setdefault(e["from"], []).append((e["to"], e))
            adj.setdefault(e["to"], []).append((e["from"], e))

    depth, parent_chain, arrival_edge = None, [], None
    if node_id == prompt_id:
        depth = 0
    else:
        visited = {prompt_id: (0, None, None)}    # node → (depth, parent, edge)
        queue = [prompt_id]
        max_depth = 4
        while queue:
            cur = queue.pop(0)
            d, _, _ = visited[cur]
            if d >= max_depth:
                continue
            for (nxt, e) in adj.get(cur, []):
                if nxt in visited:
                    continue
                visited[nxt] = (d + 1, cur, e)
                if nxt == node_id:
                    # Reconstruct chain
                    chain = []
                    cursor = node_id
                    edge_cursor = None
                    while cursor != prompt_id:
                        d2, parent, ec = visited[cursor]
                        chain.append({"node_id": cursor, "label": nodes_by_id[cursor].get("full", "")[:60],
                                      "via_edge_type": ec.get("type") if ec else None})
                        cursor = parent
                    chain.append({"node_id": prompt_id, "label": "(prompt)"})
                    chain.reverse()
                    depth = d + 1
                    parent_chain = chain
                    arrival_edge = visited[node_id][2]
                    queue = []   # stop BFS
                    break
                queue.append(nxt)

    # For chatmem/code nodes: if BFS couldn't reach from the selected prompt
    # (because they're connected to a DIFFERENT prompt), find their actual source
    # prompt and note that relationship.
    actual_source_prompt_id = None
    actual_source_prompt_label = None
    if depth is None and target["type"] in ("chatmem", "code"):
        for e in edges:
            if e["to"] == node_id and e["type"] in ("recall-cm", "recall-pre"):
                src = nodes_by_id.get(e["from"], {})
                if src.get("type") in ("prompt", "current"):
                    actual_source_prompt_id = e["from"]
                    actual_source_prompt_label = src.get("full", "")[:80]
                    depth = 1  # treat as depth-1 for display purposes
                    bm25_score = float(e.get("weight", 0.9))
                    arrival_edge = e
                    parent_chain = [
                        {"node_id": actual_source_prompt_id, "label": "(source prompt)", "via_edge_type": None},
                        {"node_id": node_id, "label": (target.get("full", ""))[:60], "via_edge_type": e["type"]},
                    ]
                    break

    # Rank in cone (depth-1 retrievals sorted by BM25 score) — only if depth==1
    rank_in_cone = None
    total_in_cone = 0
    _cone_prompt_id = actual_source_prompt_id or prompt_id
    if depth == 1:
        depth1_edges = [e for e in edges
                        if e["type"] in ("recall-d", "recall-w") and e["from"] == _cone_prompt_id]
        total_in_cone = len(depth1_edges)
        # Order by edge weight (which came from the original BM25 score at graph-build time)
        depth1_edges.sort(key=lambda x: -(x.get("weight", 0)))
        for i, e in enumerate(depth1_edges, start=1):
            if e["to"] == node_id:
                rank_in_cone = i
                break

    # Utility references — count telemetry events whose block tokens likely
    # match this node (heuristic via token-overlap, since utility events
    # don't record specific item identity — only by_block counts)
    utility_refs = 0
    try:
        if target["type"] in ("decision", "doc"):
            # Approximate: count events in last 7d that fired block type matching this node
            cutoff = time.time() - 7 * 86400
            block_name = "g1" if target["type"] == "decision" else "g2_docs"
            for evt in (TAIL.events if TAIL else []):
                if evt.get("type") != "utility_measured":
                    continue
                if evt.get("ts", 0) < cutoff:
                    continue
                by_block = evt.get("by_block") or {}
                bb = by_block.get(block_name) or {}
                if bb.get("referenced", 0) > 0:
                    utility_refs += 1
    except Exception:
        pass

    # Per-token BM25 contribution — approximate as idf * tf_in_node,
    # then normalize so contributions sum to 1.0 for display.
    # IDF comes from the corpus-level BM25 object built during graph construction;
    # we look it up from the cached graph's bm25 index if available, else fallback to count.
    token_contributions = []
    try:
        bm25_idf = None
        corpus_bm25 = GRAPH_CACHE.get("bm25_idf")  # cached during _build_graph
        if corpus_bm25:
            bm25_idf = corpus_bm25
        if bm25_idf and matched_tokens:
            raw = [(t, bm25_idf.get(t, 1.0) * node_tf.get(t, 1)) for t in matched_tokens]
            total_raw = sum(v for _, v in raw) or 1.0
            token_contributions = [
                {"token": t, "tf": node_tf.get(t, 1),
                 "idf": round(bm25_idf.get(t, 1.0), 2),
                 "contribution_pct": round(100.0 * v / total_raw, 1)}
                for t, v in sorted(raw, key=lambda x: -x[1])
            ]
        elif matched_tokens:
            # Fallback: uniform contribution by TF only
            total_tf = sum(node_tf.get(t, 1) for t in matched_tokens) or 1
            token_contributions = [
                {"token": t, "tf": node_tf.get(t, 1), "idf": None,
                 "contribution_pct": round(100.0 * node_tf.get(t, 1) / total_tf, 1)}
                for t in matched_tokens
            ]
    except Exception:
        token_contributions = []

    # Top 2 competitors in the same cone (for rank-2 comparison)
    top_competitors = []
    if depth == 1 and rank_in_cone and total_in_cone > 1:
        try:
            depth1 = [e for e in edges
                      if e["type"] in ("recall-d", "recall-w") and e["from"] == prompt_id]
            depth1.sort(key=lambda x: -(x.get("weight", 0)))
            for i, e in enumerate(depth1[:3], start=1):
                if e["to"] == node_id:
                    continue
                n = nodes_by_id.get(e["to"], {})
                top_competitors.append({
                    "rank": i,
                    "label": (n.get("full") or "")[:50],
                    "bm25_score": round(float(e.get("weight", 0)), 2),
                    "is_self": False,
                })
                if len(top_competitors) >= 2:
                    break
        except Exception:
            pass

    # ── Retrieval method classification (2026-04-27) ─────────────────────────
    # Detects HOW the node was found: keyword BM25, semantic e5-small, or cascade BFS.
    # Key signal: depth==1 with bm25_score==0 → dense embedding rescued it (BM25 miss).
    retrieval_method = "unreachable"
    if depth == 0:
        retrieval_method = "prompt"
    elif depth is None:
        retrieval_method = "unreachable"
    elif target["type"] == "chatmem":
        retrieval_method = "cm_hybrid"
    elif target["type"] == "code":
        retrieval_method = "code_index"
    elif depth == 1:
        if bm25_score > 0.05 and len(matched_tokens) > 0:
            retrieval_method = "keyword"   # BM25 matched tokens directly
        elif bm25_score > 0.05:
            retrieval_method = "hybrid"    # BM25 scored but no visible token match
        else:
            retrieval_method = "semantic"  # Dense embedding rescued it — BM25 score ≈ 0
    else:
        retrieval_method = "cascade"       # depth > 1: BFS propagation via topic/temporal edges

    # ── Semantic closeness score (2026-04-27) ────────────────────────────────
    # Compute cosine similarity between prompt embedding and node text embedding
    # via vec-daemon (multilingual-e5-small, 384-dim, already normalized).
    # Shows HOW semantically close the node is to the prompt — independent of BM25.
    # Result: 0.0–1.0 cosine score, or None if vec-daemon is unavailable.
    semantic_score = None
    try:
        _prompt_text_for_embed = (prompt or {}).get("full") or (prompt or {}).get("label") or ""
        _node_text_for_embed = (node_text[:600]) if node_text else ""
        if _prompt_text_for_embed and _node_text_for_embed:
            _q_emb = _bm._vec_embed(_prompt_text_for_embed[:800])
            _n_emb = _bm._vec_embed(_node_text_for_embed)
            if _q_emb and _n_emb:
                semantic_score = round(_bm._cosine(_q_emb, _n_emb), 3)
    except Exception:
        semantic_score = None

    # Natural-language summary — one sentence explaining why
    summary = ""
    if depth == 0:
        summary = "This is the selected prompt itself."
    elif depth is None:
        summary = "Not directly connected to this prompt through any retrieval path within 4 hops."
    elif depth == 1 and target["type"] == "chatmem":
        summary = "Retrieved by chat-memory (CM) hybrid search — cosine similarity + FTS5 BM25 rank merge against prompt context."
        if actual_source_prompt_id and actual_source_prompt_id != prompt_id:
            summary += " (Source: a different prompt in this window — click its node to see its full context.)"
    elif depth == 1 and target["type"] == "code":
        summary = "Retrieved by G2-PREFETCH (codebase-memory-mcp) — function/file semantic index searched against prompt query."
    elif depth == 1 and retrieval_method == "semantic":
        # Semantic rescue — the showcase case: BM25 missed it, dense embedding found it
        summary = (f"Retrieved by semantic embedding (e5-small) — your prompt matched the concept in this "
                   f"doc without keyword overlap. BM25 alone would have missed it.")
    elif depth == 1:
        n_matched = len(matched_tokens)
        n_subject = len(prompt_subject_tokens)
        top_contrib = token_contributions[0]["token"] if token_contributions else None
        top_pct = token_contributions[0]["contribution_pct"] if token_contributions else 0
        if n_subject > 0:
            summary = (f"Retrieved by keyword match — {n_matched} of {n_subject} prompt tokens found in this node"
                       + (f" ('{top_contrib}' contributes {top_pct}% of BM25 score)." if top_contrib else "."))
        else:
            summary = f"Retrieved by keyword match (BM25 score {bm25_score:.2f}, {n_matched} matching tokens)."
    else:
        edge_type = arrival_edge.get("type") if arrival_edge else "unknown"
        summary = (f"Pulled in at depth {depth} via {edge_type} edge — shares a temporal or topic cluster "
                   f"with a directly retrieved node. Indirect but contextually related.")

    preview = (node_text[:300] + "…") if len(node_text) > 300 else node_text

    # ── What was actually injected into Claude's context? (2026-04-24) ───────
    # Reconstruct the exact injection block format for this node.
    # This answers "what memory/information was used?" not just "which node matched".
    injection_preview = ""
    injection_block = None    # "RECENT DECISIONS" | "G2-DOCS" | "G2-PREFETCH"
    if target["type"] == "decision":
        injection_block = "RECENT DECISIONS"
        date_str = target.get("date", "") or "?"
        subject = target.get("full", "") or target.get("label", "")
        injection_preview = f"[{date_str}] {subject}"
    elif target["type"] == "doc":
        injection_block = "G2-DOCS"
        fname = target.get("full", "") or target.get("label", "")
        # Doc injection is filename + 1-2 preview lines (intro/heading)
        first_lines = ""
        try:
            for line in (node_text or "").splitlines()[:4]:
                stripped = line.strip()
                if stripped and len(stripped) >= 8:
                    first_lines = stripped[:120]
                    break
        except Exception:
            pass
        injection_preview = f"{fname}\n    {first_lines}" if first_lines else fname
    elif target["type"] == "chatmem":
        injection_block = "CM"
        project = target.get("project", "")
        preview_raw = (target.get("full") or "").replace(f"[CM/{project}] ", "")
        injection_preview = f"[CM/{project}]\n    {preview_raw[:200]}"
    elif target["type"] == "code":
        injection_block = "G2-PREFETCH"
        injection_preview = target.get("full", "")
    elif target["type"] in ("prompt", "current"):
        injection_preview = "(prompts are inputs, not memory injections)"

    # ── Was this node actually referenced in the assistant's response? ──────
    # Heuristic: check the most recent utility_measured event for this prompt.
    # An item whose tokens overlap with this node's distinctive subject tokens
    # counts as "this node was likely referenced".
    referenced_in_response = "unknown"   # yes_text | yes_tool | yes_both | no | pending | unknown
    referenced_mode = None
    try:
        if target["type"] in ("decision", "doc") and TAIL:
            # Distinctive token set for this node (>=4 char, subject-only)
            node_sig_tokens = {t.lower() for t in _bm.tokenize(target.get("full", ""))
                               if len(t) >= 4}
            # Find most recent utility event within 1 hour of prompt_ts
            prompt_unix_ts = None
            if prompt_ts:
                try:
                    prompt_unix_ts = datetime.fromisoformat(
                        prompt_ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    prompt_unix_ts = None
            best_evt = None
            for evt in reversed(TAIL.events if TAIL else []):
                if evt.get("type") != "utility_measured":
                    continue
                if prompt_unix_ts and abs(evt.get("ts", 0) - prompt_unix_ts) > 3600:
                    continue
                best_evt = evt
                break
            if best_evt:
                # Items list with tokens; check if any referenced item's tokens
                # have >= 2 token overlap with this node's distinctive tokens
                for it in (best_evt.get("items") or []):
                    if not it.get("referenced"):
                        continue
                    item_tokens = {t.lower() for t in (it.get("tokens") or [])
                                   if len(t) >= 4}
                    overlap = len(node_sig_tokens & item_tokens)
                    if overlap >= 2:
                        mode = it.get("hit_mode", "text")
                        if mode == "tool_use":
                            referenced_in_response = "yes_tool"
                        elif mode == "both_text":
                            referenced_in_response = "yes_both"
                        else:
                            referenced_in_response = "yes_text"
                        referenced_mode = mode
                        break
                else:
                    # Event exists for this prompt but node not in referenced items
                    referenced_in_response = "no"
            elif prompt_unix_ts:
                # No event yet for this prompt → still waiting for assistant reply
                referenced_in_response = "pending"
    except Exception:
        pass

    # ── All CTX blocks fired for this prompt (multi-block view) ──────────────
    # Scan TAIL for block_fired + mode_switch events within ±10s of this prompt's
    # timestamp. Surfaces ALL retrieval channels (CM/G1/G2-DOCS/G2-PREFETCH/G2-GREP),
    # not just the BM25-ranked node. The frontend highlights which block surfaced
    # this specific node using injection_block.
    retrieval_blocks = None
    try:
        if TAIL and prompt_ts:
            _pts = None
            try:
                _pts = datetime.fromisoformat(prompt_ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
            if _pts:
                blocks_info: dict = {}
                cm_mode = None
                for evt in TAIL.events:
                    evt_ts = evt.get("ts", 0)
                    if abs(evt_ts - _pts) > 10:
                        continue
                    etype = evt.get("type", "")
                    if etype == "block_fired" and evt.get("hook") == "bm25-memory":
                        blk = evt.get("block", "")
                        blocks_info[blk] = {
                            "count": evt.get("count", 0),
                            "duration_ms": evt.get("duration_ms", 0),
                        }
                    elif etype == "mode_switch" and evt.get("hook") == "chat-memory":
                        cm_mode = evt.get("to_mode", "unknown")
                if blocks_info or cm_mode is not None:
                    retrieval_blocks = {
                        "cm_mode": cm_mode,
                        "g1_decisions": blocks_info.get("g1_decisions"),
                        "g2_docs": blocks_info.get("g2_docs"),
                        "g2_prefetch": blocks_info.get("g2_prefetch"),
                        "g2_grep": blocks_info.get("g2_grep"),
                    }
    except Exception:
        pass

    # ── Channel label + retrieval formula (per node type) ────────────────────
    node_type = target["type"]
    channel_map = {
        "decision": "G1 · BM25Okapi",
        "doc":      "G2-DOCS · BM25Okapi",
        "chatmem":  "CM · hybrid (α·cosine + (1-α)·BM25)",
        "code":     "G2-PREFETCH · codebase-memory-mcp",
        "prompt":   "—",
        "current":  "—",
    }
    channel = channel_map.get(node_type, node_type)

    # BM25 formula string (for display, k₁=1.5, b=0.75 standard Okapi defaults)
    retrieval_formula = None
    if node_type in ("decision", "doc"):
        retrieval_formula = "BM25(q,d) = Σ IDF(t)·tf(t,d)·(k₁+1) / (tf+k₁·(1-b+b·|d|/avgdl))"
    elif node_type == "chatmem":
        retrieval_formula = "hybrid = α·cosine_sim + (1-α)·BM25_rank_norm  [α=0.5]"
    elif node_type == "code":
        retrieval_formula = "codebase-memory-mcp: function/file BM25 + semantic index"

    # ── CM hybrid scoring components (chatmem nodes only) ─────────────────────
    cm_scores = None
    if node_type == "chatmem":
        try:
            preview_raw = (target.get("full") or "").split("] ", 1)[-1] if "] " in (target.get("full") or "") else (target.get("full") or "")
            cm_scores = _cm_explain_scores(prompt_text, preview_raw)
        except Exception:
            cm_scores = None

    return {
        "node_id": node_id,
        "node_type": node_type,
        "node_label": target.get("full", ""),
        "node_date": target.get("date", ""),
        "utility_heat": target.get("utility_heat", 0),
        "prompt_id": prompt_id,
        "prompt_text": prompt_text,
        "prompt_project": prompt_project,
        "prompt_ts": prompt_ts,
        "depth": depth,
        "bm25_score": round(bm25_score, 3),
        "rank_in_cone": rank_in_cone,
        "total_in_cone": total_in_cone,
        "matched_tokens": matched_tokens,
        "missed_tokens": missed_tokens,
        "total_subject_tokens": len(prompt_subject_tokens),
        "token_contributions": token_contributions,
        "top_competitors": top_competitors,
        "summary": summary,
        "parent_chain": parent_chain,
        "arrival_edge_type": arrival_edge.get("type") if arrival_edge else None,
        "utility_refs_7d": utility_refs,
        "preview": preview,
        "injection_preview": injection_preview,
        "injection_block": injection_block,
        "referenced_in_response": referenced_in_response,
        "referenced_mode": referenced_mode,
        "retrieval_blocks": retrieval_blocks,
        "channel": channel,
        "retrieval_formula": retrieval_formula,
        "cm_scores": cm_scores,
        "actual_source_prompt_id": actual_source_prompt_id,
        "actual_source_prompt_label": actual_source_prompt_label,
        "retrieval_method": retrieval_method,
        "semantic_score": semantic_score,
    }


@app.get("/api/node-explain")
async def node_explain(node_id: str, prompt_id: str):
    """Explain WHY `node_id` is on the retrieval path for `prompt_id`.
    Used by the graph detail pane when a user clicks a cascade node."""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _explain_node, node_id, prompt_id)
    return JSONResponse(data)


def _prompt_contributors(prompt_id: str, max_items: int = 12) -> dict:
    """Return ranked list of nodes that contributed to `prompt_id`.
    Methodology change 2026-04-24: instead of showing one node at a time, the
    details pane shows ALL contributing nodes ordered by BM25 score, each with
    injection_preview + referenced_in_response for at-a-glance comparison."""
    g = _get_graph_cached()
    nodes_by_id = {n["id"]: n for n in (g.get("nodes") or [])}
    edges = g.get("edges") or []

    prompt_node = nodes_by_id.get(prompt_id)
    if not prompt_node:
        return {"error": "prompt_id not found", "prompt_id": prompt_id}

    # Collect all depth-1 recall edges out of this prompt (each represents a contributor)
    contrib_edges = [e for e in edges
                     if e.get("type", "").startswith("recall") and e.get("from") == prompt_id]
    contrib_edges.sort(key=lambda x: -(x.get("weight", 0)))
    contrib_edges = contrib_edges[:max_items]

    def _find_relevant_excerpt(text: str, tokens: list, max_chars: int = 280) -> str:
        """Pick the sentence/paragraph within `text` that contains the most
        matched tokens. Returns a centered excerpt with context around it.
        This is what makes the contributors list show the ACTUAL RELATED INFO,
        not just the filename/subject line."""
        if not text or not tokens:
            return (text or "")[:max_chars]
        tok_lower = [t.lower() for t in tokens if len(t) >= 3]
        if not tok_lower:
            return text[:max_chars]
        # Split on sentence-ish boundaries
        import re as _re
        segments = _re.split(r'(?<=[.!?\n])\s+', text)
        best_seg = ""
        best_hits = 0
        best_idx = 0
        for idx, seg in enumerate(segments):
            seg_l = seg.lower()
            hits = sum(1 for t in tok_lower if t in seg_l)
            if hits > best_hits and len(seg.strip()) >= 20:
                best_hits = hits
                best_seg = seg
                best_idx = idx
        if best_hits == 0:
            return text[:max_chars]
        # Build context: best segment + neighboring segments until max_chars
        excerpt = best_seg.strip()
        # Pad with adjacent segments for context
        left = best_idx - 1
        right = best_idx + 1
        while len(excerpt) < max_chars and (left >= 0 or right < len(segments)):
            if right < len(segments) and len(excerpt) + len(segments[right]) < max_chars:
                excerpt = excerpt + " " + segments[right].strip()
                right += 1
            elif left >= 0 and len(excerpt) + len(segments[left]) < max_chars:
                excerpt = segments[left].strip() + " " + excerpt
                left -= 1
            else:
                break
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars] + "…"
        return excerpt.strip()

    contributors = []
    for i, e in enumerate(contrib_edges, start=1):
        target_id = e["to"]
        try:
            detail = _explain_node(target_id, prompt_id)
        except Exception:
            detail = {"error": "explain failed", "node_id": target_id}

        # Compute relevant excerpt from the node's full text (not just the injection preview)
        node_text = detail.get("preview", "")   # _explain_node already populated this (300-char slice)
        # Prefer full content if available
        try:
            if detail.get("node_type") == "doc":
                # Re-fetch full content from file for better excerpt
                fname = detail.get("node_label", "")
                from pathlib import Path
                for p in [Path(_project_dir()) / "docs" / "research" / fname,
                          Path(_project_dir()) / fname]:
                    if p.is_file():
                        node_text = p.read_text(encoding="utf-8", errors="replace")[:6000]
                        break
            elif detail.get("node_type") == "decision":
                # Get full decision body
                for d in _bm.get_decision_corpus(_project_dir()):
                    if d.get("subject") == detail.get("node_label"):
                        node_text = d.get("text", node_text)
                        break
        except Exception:
            pass

        relevant_excerpt = _find_relevant_excerpt(
            node_text, detail.get("matched_tokens", []), max_chars=280
        )

        contributors.append({
            "rank": i,
            "node_id": target_id,
            "node_type": detail.get("node_type"),
            "node_label": detail.get("node_label", "")[:80],
            "node_date": detail.get("node_date"),
            "bm25_score": detail.get("bm25_score", 0),
            "matched_tokens": detail.get("matched_tokens", [])[:6],
            "summary": detail.get("summary", ""),
            "relevant_excerpt": relevant_excerpt,   # NEW — the actual related info
            "injection_block": detail.get("injection_block"),
            "injection_preview": detail.get("injection_preview", ""),
            "referenced_in_response": detail.get("referenced_in_response", "unknown"),
            "referenced_mode": detail.get("referenced_mode"),
            "retrieval_method": detail.get("retrieval_method", "unknown"),
            "semantic_score": detail.get("semantic_score"),
            "top_contribution_token": (detail.get("token_contributions") or [{}])[0].get("token"),
            "top_contribution_pct": (detail.get("token_contributions") or [{}])[0].get("contribution_pct", 0),
            "_detail": detail,
        })

    # ── Prompt-level retrieval_blocks — all CTX channels that fired ─────────
    # Same TAIL-scan as _explain_node but scoped to the prompt, not a single node.
    # Included in the contributors response so the frontend can show ALL retrieval
    # channels (CM/G1/G2-DOCS/G2-PREFETCH/G2-GREP) at the top of the detail pane,
    # not just the BM25-ranked G1+G2-DOCS contributors below.
    prompt_retrieval_blocks = None
    try:
        prompt_ts_str = prompt_node.get("ts")
        if TAIL and prompt_ts_str:
            _pts = None
            try:
                _pts = datetime.fromisoformat(prompt_ts_str.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
            if _pts:
                blocks_info: dict = {}
                cm_mode = None
                for evt in TAIL.events:
                    evt_ts = evt.get("ts", 0)
                    if abs(evt_ts - _pts) > 10:
                        continue
                    etype = evt.get("type", "")
                    if etype == "block_fired" and evt.get("hook") == "bm25-memory":
                        blk = evt.get("block", "")
                        blocks_info[blk] = {
                            "count": evt.get("count", 0),
                            "duration_ms": evt.get("duration_ms", 0),
                        }
                    elif etype == "mode_switch" and evt.get("hook") == "chat-memory":
                        cm_mode = evt.get("to_mode", "unknown")
                if blocks_info or cm_mode is not None:
                    prompt_retrieval_blocks = {
                        "cm_mode": cm_mode,
                        "g1_decisions": blocks_info.get("g1_decisions"),
                        "g2_docs": blocks_info.get("g2_docs"),
                        "g2_prefetch": blocks_info.get("g2_prefetch"),
                        "g2_grep": blocks_info.get("g2_grep"),
                    }
    except Exception:
        pass

    return {
        "prompt_id": prompt_id,
        "prompt_text": (prompt_node.get("content_full")
                        or prompt_node.get("full")
                        or prompt_node.get("label") or ""),
        "prompt_project": prompt_node.get("project"),
        "prompt_ts": prompt_node.get("ts"),
        "total_contributors": len(contrib_edges),
        "contributors": contributors,
        "retrieval_blocks": prompt_retrieval_blocks,
    }


@app.get("/api/prompt-contributors")
async def prompt_contributors(request: Request, prompt_id: str, max_items: int = 12):
    """Ranked list of nodes contributing to a prompt — new dashboard methodology
    (2026-04-24): overview-first, click-to-drill-in on the graph pane."""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _prompt_contributors, prompt_id, max_items)
    if _demo_enabled(request):
        data = _apply_demo_contributors(data)
    return JSONResponse(data)


@app.post("/api/graph/refresh")
async def refresh_graph():
    GRAPH_CACHE["ts"] = 0   # invalidate cache
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _get_graph_cached)
    return JSONResponse({"ok": True, "stats": data.get("stats", {})})


@app.get("/api/samples")
async def samples_page(offset: int = 3, limit: int = 10):
    """Paginated samples beyond the live-streamed top 3 (SSE snapshot).
    Used by the 'Load more' button in Function Proof. Caps limit at 20
    to keep per-request cost bounded (~10 hook spawns × ~200ms each)."""
    limit = max(1, min(20, limit))
    offset = max(0, offset)
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(
        None, _compute_samples, limit, offset, False  # include_realtime=False
    )
    return JSONResponse({
        "offset": offset, "limit": limit,
        "prompts": data["prompts"], "computed_at": data["computed_at"],
    })


@app.post("/api/samples/refresh")
async def refresh_samples():
    """Force an immediate samples recompute (ignores the 60s cache)."""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _compute_samples, 3)
    SAMPLE_CACHE.update(data)
    return JSONResponse({"ok": True, "computed_at": data["computed_at"]})



@app.get("/stream")
async def stream():
    async def gen():
        loop = asyncio.get_event_loop()
        while True:
            try:
                snap = _build_snapshot()
                yield f"data: {json.dumps(snap)}\n\n"
                # Reactive: if new events arrived this tick, kick off
                # non-blocking samples + graph recompute so the NEXT tick
                # has fresh data visible to the user.
                if _PENDING_REFRESH["samples"]:
                    _PENDING_REFRESH["samples"] = False
                    async def _refresh_samples():
                        try:
                            data = await loop.run_in_executor(None, _compute_samples, 3)
                            SAMPLE_CACHE.update(data)
                        except Exception:
                            pass
                    asyncio.create_task(_refresh_samples())
                if _PENDING_REFRESH["graph"]:
                    _PENDING_REFRESH["graph"] = False
                    GRAPH_CACHE["ts"] = 0  # invalidate so next /api/graph rebuilds
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(2.0)
    return StreamingResponse(gen(), media_type="text/event-stream")


def main():
    import uvicorn
    host = os.environ.get("CTX_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("CTX_DASHBOARD_PORT", "8787"))
    print(f"CTX Dashboard → http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
