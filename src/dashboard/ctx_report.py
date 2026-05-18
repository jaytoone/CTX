#!/usr/bin/env python3
"""
ctx-report.py — terminal report for CTX telemetry (iter 17, upgraded iter 20).

Reads ~/.claude/ctx-telemetry.jsonl, prints a rich terminal report with
progress bars, panels, and inline green/yellow/red verdicts.

Uses `rich` for panels/bars when available; falls back to plain text with
--plain or when rich is unavailable.

Usage:
    ctx-report.py                    # last 7 days (default, rich UI)
    ctx-report.py --since=today      # today only
    ctx-report.py --since=24h        # last 24 hours
    ctx-report.py --since=all        # all events in log
    ctx-report.py --since=30d        # last 30 days
    ctx-report.py --plain            # no rich UI, plain text (for grep/pipe)
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress_bar import ProgressBar
    from rich.live import Live
    from rich import box
    _RICH_OK = True
except ImportError:
    _RICH_OK = False

LOG = Path(os.path.expanduser("~/.claude/ctx-telemetry.jsonl"))

# ── Thresholds (tune without reading code) ────────────────────────────
TH = {
    "cm_hybrid_pct_min":     0.95,   # CM hybrid below this → yellow/red
    "cm_hybrid_pct_red":     0.80,
    "g1_fire_min":           0.30,   # G1 fire rate: too low = fact corpus empty
    "g1_fire_max_concern":   1.00,   # 100% over many days might mean noise-matching
    "g2_docs_over_concern":  0.85,   # g2_docs firing too often = over-matching
    "g2_grep_over_concern":  0.50,   # g2_grep ≥50% = graph DB stale
    "bm25_p95_ms_yellow":    500,
    "bm25_p95_ms_red":       1000,
    "min_events_for_eval":   50,     # below this, most metrics are noise
}

# ── ANSI colors (guard for non-TTY) ───────────────────────────────────
def _use_color():
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

COLOR = _use_color()
GREEN = "\033[32m" if COLOR else ""
YELLOW = "\033[33m" if COLOR else ""
RED = "\033[31m" if COLOR else ""
DIM = "\033[2m" if COLOR else ""
BOLD = "\033[1m" if COLOR else ""
RESET = "\033[0m" if COLOR else ""

# Distinct symbols even in plain mode (bug fix: previously all collapsed to ●
# when color was off, causing overall_grade counter to double-count).
FLAG_G = f"{GREEN}✓{RESET}"  # green check
FLAG_Y = f"{YELLOW}~{RESET}"  # yellow tilde
FLAG_R = f"{RED}✗{RESET}"     # red cross


def parse_since(val: str) -> float | None:
    """Return cutoff UNIX ts (or None = all)."""
    now = datetime.now(timezone.utc).timestamp()
    if val == "all":
        return None
    if val == "today":
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start.timestamp()
    if val.endswith("h"):
        return now - int(val[:-1]) * 3600
    if val.endswith("d"):
        return now - int(val[:-1]) * 86400
    raise ValueError(f"bad --since: {val} (use 'today', '7d', '24h', 'all')")


def load_events(cutoff_ts: float | None):
    events = []
    if not LOG.exists():
        return events
    with LOG.open() as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if cutoff_ts is None or r.get("ts", 0) >= cutoff_ts:
                events.append(r)
    return events


def fmt_pct(num, denom):
    if not denom:
        return "  —"
    return f"{100 * num / denom:3.0f}%"


def fmt_ms(vals):
    if not vals:
        return "—"
    vals = sorted(vals)
    p50 = vals[len(vals) // 2]
    p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
    return f"p50 {p50}ms  p95 {p95}ms  max {vals[-1]}ms"


def daily_histogram(events):
    by_day = Counter()
    for e in events:
        try:
            d = datetime.fromtimestamp(e["ts"], tz=timezone.utc).strftime("%a %m-%d")
            by_day[d] += 1
        except Exception:
            continue
    days = sorted(by_day.keys())
    max_count = max(by_day.values()) if by_day else 0
    if not max_count:
        return "(no events)"
    bars = []
    for d in days:
        n = by_day[d]
        bar = "█" * max(1, int(10 * n / max_count))
        bars.append(f"  {d}  {n:>4}  {bar}")
    return "\n".join(bars)


# ── Verdict helpers ───────────────────────────────────────────────────
def verdict_cm_hybrid(pct: float):
    if pct >= TH["cm_hybrid_pct_min"]:
        return FLAG_G, "daemon healthy"
    if pct >= TH["cm_hybrid_pct_red"]:
        return FLAG_Y, f"daemon flaky (<{int(TH['cm_hybrid_pct_min']*100)}%)"
    return FLAG_R, f"daemon failing (<{int(TH['cm_hybrid_pct_red']*100)}%)"


def verdict_g1_fire(rate: float, n: int):
    if n < 5:
        return f"{DIM}○{RESET}", "low n"
    if rate >= TH["g1_fire_max_concern"]:
        return FLAG_Y, "always fires — check relevance quality"
    if rate < TH["g1_fire_min"]:
        return FLAG_Y, "low fire rate — corpus may be empty/stale"
    return FLAG_G, "selective firing"


def verdict_g2_block(block_name: str, rate: float):
    if block_name == "g2_docs" and rate >= TH["g2_docs_over_concern"]:
        return FLAG_Y, "over-matching — docs corpus too broad?"
    if block_name == "g2_grep" and rate >= TH["g2_grep_over_concern"]:
        return FLAG_Y, "graph DB stale/missing — falling back often"
    return FLAG_G, "ok"


def verdict_latency(p95: int):
    if p95 >= TH["bm25_p95_ms_red"]:
        return FLAG_R, f"over {TH['bm25_p95_ms_red']}ms — cost problem"
    if p95 >= TH["bm25_p95_ms_yellow"]:
        return FLAG_Y, "p95 borderline — watch"
    return FLAG_G, "fast"


# ── --explain spot-checks (iter 19) ──────────────────────────────────
# Concrete per-metric diagnostics. Each returns ONE number + verdict.
# No UI upgrade — still terminal-only text. Per /entity -cr 2026-04-19
# conclusion: message specificity, not form factor.

import subprocess as _sp
import sqlite3 as _sql
import re as _re

_VAULT_DB = Path(os.path.expanduser("~/.local/share/claude-vault/vault.db"))
_BM25_HOOK = Path(os.path.expanduser("~/.claude/hooks/bm25-memory.py"))


def _recent_user_prompts(n: int = 5, min_len: int = 20, max_len: int = 400):
    """Read N recent user prompts from vault.db. Returns [(ts, content), ...]."""
    if not _VAULT_DB.exists():
        return []
    try:
        c = _sql.connect(f"file:{_VAULT_DB}?mode=ro", uri=True, timeout=2.0)
        rows = c.execute(f"""
            SELECT timestamp, content FROM messages
            WHERE role='user'
              AND length(content) BETWEEN {min_len} AND {max_len}
              AND content NOT LIKE '[tool_%'
              AND content NOT LIKE 'Caveat:%'
              AND content NOT LIKE '<command-%'
            ORDER BY id DESC LIMIT {n}
        """).fetchall()
        c.close()
        return rows
    except Exception:
        return []


def _run_bm25_memory(prompt: str) -> str:
    """Invoke bm25-memory with a prompt, return its stdout."""
    if not _BM25_HOOK.exists():
        return ""
    try:
        r = _sp.run(
            ["python3", str(_BM25_HOOK), "--rich"],
            input=json.dumps({"prompt": prompt, "cwd": os.getcwd()}),
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout
    except Exception:
        return ""


def _extract_block(hook_output: str, block_marker: str) -> list:
    """Parse hook stdout JSON and extract items in a given block.
    block_marker = '[RECENT DECISIONS]' / '[G2-DOCS]' / '[G2-PREFETCH]' etc.
    Returns list of item strings (first 60 chars, stripped).

    Handles two item formats:
      - `> item` (G1 decisions, G2-DOCS)
      - `Function: foo @ path.py` (G2-PREFETCH, no leading '>')
    """
    try:
        payload = json.loads(hook_output)
        ctx = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    except Exception:
        ctx = hook_output
    # G2-PREFETCH's "Start with: ..." summary line is not an item — filter it
    PREFETCH_PREFIXES = ("Function:", "Class:", "Method:", "Module:", "File:")
    items = []
    in_block = False
    for line in ctx.split("\n"):
        stripped = line.strip()
        if stripped.startswith(block_marker):
            in_block = True
            continue
        if in_block:
            if not stripped:
                continue
            if stripped.startswith("["):  # next block
                break
            if stripped.startswith("Start with:"):  # summary line
                continue
            # Format 1: G1 / G2-DOCS items start with '>'
            if stripped.startswith(">"):
                items.append(stripped.lstrip("> ").strip()[:60])
            # Format 2: G2-PREFETCH items have a symbol-kind prefix
            elif any(stripped.startswith(p) for p in PREFETCH_PREFIXES):
                items.append(stripped[:60])
            # Format 3: G2-GREP items are plain file paths (no special prefix)
            elif "/" in stripped or "." in stripped:
                items.append(stripped[:60])
    return items


def _jaccard_avg(sets: list) -> float:
    """Average pairwise Jaccard overlap across a list of sets. 0 = diverse, 1 = identical."""
    if len(sets) < 2:
        return 0.0
    ovs = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            if not a and not b:
                continue
            union = a | b
            if not union:
                continue
            ovs.append(len(a & b) / len(union))
    return sum(ovs) / len(ovs) if ovs else 0.0


def _explain_g1():
    print(f"{BOLD}--explain g1{RESET}  (G1 decision-diversity spot-check)")
    prompts = _recent_user_prompts(5)
    if len(prompts) < 2:
        print(f"  {FLAG_R} Not enough recent user prompts in vault.db (got {len(prompts)}, need ≥2).")
        return
    print(f"  Sampled {len(prompts)} recent user prompts from vault.db")
    subject_sets = []
    for ts, content in prompts:
        out = _run_bm25_memory(content)
        subjects = set(_extract_block(out, "[RECENT DECISIONS]"))
        subject_sets.append(subjects)
        print(f"    · {ts[:16] if ts else '?'}  → top-7 size {len(subjects)}")
    jac = _jaccard_avg(subject_sets)
    print(f"\n  Average pairwise top-7 Jaccard overlap:  {jac*100:.0f}%")
    if jac >= 0.6:
        print(f"  {FLAG_R}  HIGH overlap → G1 returns similar subjects across different prompts (likely noise)")
    elif jac >= 0.3:
        print(f"  {FLAG_Y}  MIXED — some prompt sensitivity, some consistent baseline")
    else:
        print(f"  {FLAG_G}  LOW overlap → G1 adapts to prompt content (healthy)")


def _explain_g2_docs():
    print(f"{BOLD}--explain g2_docs{RESET}  (G2 docs over-match spot-check)")
    prompts = _recent_user_prompts(5)
    if len(prompts) < 2:
        print(f"  {FLAG_R} Not enough recent user prompts (got {len(prompts)}, need ≥2).")
        return
    print(f"  Sampled {len(prompts)} recent prompts — checking doc-name diversity across invocations")
    doc_sets = []
    for ts, content in prompts:
        out = _run_bm25_memory(content)
        items = _extract_block(out, "[G2-DOCS]")
        # Extract just the filename part (before §)
        filenames = set()
        for it in items:
            fn = it.split(" §")[0].strip("> `'\"").strip()
            if fn:
                filenames.add(fn)
        doc_sets.append(filenames)
        print(f"    · {ts[:16] if ts else '?'}  → unique docs {len(filenames)}")
    jac = _jaccard_avg(doc_sets)
    print(f"\n  Average pairwise doc-set Jaccard overlap:  {jac*100:.0f}%")
    if jac >= 0.6:
        print(f"  {FLAG_R}  HIGH overlap → same docs surface for different prompts (corpus too broad)")
    elif jac >= 0.3:
        print(f"  {FLAG_Y}  MIXED — some popular docs repeat (may be genuinely core docs)")
    else:
        print(f"  {FLAG_G}  LOW overlap → docs adapt to prompt (healthy)")


def _explain_g2_grep():
    print(f"{BOLD}--explain g2_grep{RESET}  (graph DB staleness check)")
    db_cache = Path(os.path.expanduser("~/.cache/codebase-memory-mcp"))
    if not db_cache.exists():
        print(f"  {FLAG_R} codebase-memory-mcp cache dir missing — graph DB never built")
        return
    # Find DB for current project
    cwd = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    slug = cwd.replace("/", "-").lstrip("-")
    db_path = db_cache / f"{slug}.db"
    if not db_path.exists():
        # look for any db matching cwd name
        for f in db_cache.iterdir():
            if f.suffix == ".db" and Path(cwd).name.lower() in f.name.lower():
                db_path = f
                break
    if not db_path.exists():
        print(f"  {FLAG_R} No graph DB for this project in {db_cache}")
        print(f"     g2_grep fallback fires every time — run: mcp__codebase-memory-mcp__index_repository")
        return
    import time
    age_s = time.time() - db_path.stat().st_mtime
    age_h = age_s / 3600
    age_d = age_h / 24
    print(f"  Graph DB:       {db_path.name}")
    print(f"  Last indexed:   {age_h:.1f}h ago  ({age_d:.1f}d)")
    if age_h < 24:
        print(f"  {FLAG_G}  FRESH — g2_grep fallback only fires when query genuinely misses graph")
    elif age_h < 72:
        print(f"  {FLAG_Y}  OK — 1-3d old, consider reindex if g2_grep rate climbs")
    elif age_h < 168:
        print(f"  {FLAG_Y}  STALE — 3-7d old, auto-index.py would flag this (but it's not wired)")
    else:
        print(f"  {FLAG_R}  VERY STALE — {age_d:.1f}d old. G2 recall degrades. Run a manual reindex.")


def _explain_latency(events: list):
    print(f"{BOLD}--explain latency{RESET}  (latency distribution + outliers)")
    bm = [e for e in events if e.get("type") == "hook_invoked" and e.get("hook") == "bm25-memory"]
    if not bm:
        print(f"  No bm25-memory invocations in window.")
        return
    durs = sorted([(e.get("duration_ms", 0), e.get("ts", 0)) for e in bm])
    vals = [d for d, _ in durs]
    if not vals:
        return
    p50 = vals[len(vals)//2]
    p95 = vals[min(len(vals)-1, int(len(vals)*0.95))]
    p99 = vals[min(len(vals)-1, int(len(vals)*0.99))]
    print(f"  n={len(vals)}  p50={p50}ms  p95={p95}ms  p99={p99}ms  max={vals[-1]}ms")
    # Outliers above p95
    outliers = [(d, t) for d, t in durs if d > p95]
    if outliers:
        print(f"\n  Outliers (>{p95}ms):  {len(outliers)} events")
        from datetime import datetime
        for d, t in outliers[-5:]:
            ts_str = datetime.fromtimestamp(t).strftime("%m-%d %H:%M:%S") if t else "?"
            print(f"    · {ts_str}  {d}ms")
        if max(vals) > 1000:
            print(f"  {FLAG_R}  Max > 1000ms — cold-start or corpus rebuild blocking hook path")
        elif max(vals) > 500:
            print(f"  {FLAG_Y}  Tail > 500ms — occasional spikes, likely cold rank_bm25 import")
    else:
        print(f"  {FLAG_G}  Tight distribution, no outliers above p95")


def overall_grade(flags: list):
    g = flags.count(FLAG_G)
    y = flags.count(FLAG_Y)
    r = flags.count(FLAG_R)
    total = g + y + r
    if r > 0:
        return RED, f"RED ({r} red, {y} yellow, {g} green)"
    if y >= 2:
        return YELLOW, f"MIXED ({y} yellow, {g} green)"
    if y == 1:
        return YELLOW, f"MOSTLY GREEN ({g} green, 1 yellow)"
    return GREEN, f"ALL GREEN ({g} green)"


# ── Rich renderer (iter 20) ───────────────────────────────────────────
def _grade_style(g: int, y: int, r: int) -> tuple:
    """Return (style_name, headline_text) for health panel header."""
    if r > 0:
        return "red", f"RED ({r} red, {y} yellow, {g} green)"
    if y >= 2:
        return "yellow", f"MIXED ({y} yellow, {g} green)"
    if y == 1:
        return "yellow", f"MOSTLY GREEN ({g} green, 1 yellow)"
    return "green", f"ALL GREEN ({g} green)"


def _bar_row(label: str, pct_value: float, threshold: float, raw: str,
             invert: bool = False, width: int = 24) -> tuple:
    """Build a (label_text, bar_widget, raw_text, verdict_text) row.
    pct_value and threshold are in [0,1]. invert=True means lower is better."""
    # Verdict based on threshold direction
    if invert:
        ok = pct_value < threshold
    else:
        ok = pct_value >= threshold
    color = "green" if ok else "yellow"
    symbol = "[green]✓[/green]" if ok else "[yellow]~[/yellow]"
    # Fill: bar length proportional to value (always 0..1 scale)
    bar = ProgressBar(total=100, completed=int(pct_value * 100), width=width,
                      complete_style=color, finished_style=color)
    return (label, bar, raw, symbol)


def _build_rich_group(args, events, data, live: bool = False):
    """Build the rich renderable group. Returns a Group so it can be printed
    once or wrapped in a Live() for watch mode."""
    items = []

    # ── Inline header (1 line): title + event count + activity mini-summary
    days_summary = " · ".join(
        f"[cyan]{d.split()[1]}[/cyan] {n}" for d, n in
        sorted(data["daily_counts"].items(), key=lambda kv: kv[0], reverse=True)[:3]
    )
    watch_tag = f"  [bold magenta]● LIVE[/bold magenta]" if live else ""
    header = (
        f"[bold cyan]CTX Telemetry[/bold cyan] "
        f"[dim]since={args.since} ·[/dim] [bold]{len(events)}[/bold] events "
        f"[dim]·[/dim] {days_summary}{watch_tag}"
    )
    items.append(Text.from_markup(header))

    if len(events) < TH["min_events_for_eval"]:
        items.append(Text.from_markup(
            f"[yellow]⚠ Sample too small (<{TH['min_events_for_eval']}). "
            f"Verdicts are provisional.[/yellow]"
        ))

    # ── System Health panel — compact progress bars (only meaningful metrics)
    health_table = Table.grid(padding=(0, 1), expand=False)
    health_table.add_column(style="bold", width=14)
    health_table.add_column(width=20)       # progress bar
    health_table.add_column(width=11, justify="right", style="cyan")
    health_table.add_column(width=2)        # symbol
    health_table.add_column(style="dim")    # msg

    def _row(label, ratio, value_str, ok, msg):
        color = "green" if ok else "yellow"
        health_table.add_row(
            label,
            ProgressBar(total=100, completed=int(min(1.0, ratio) * 100), width=18,
                        complete_style=color, finished_style=color),
            value_str,
            "[green]✓[/green]" if ok else "[yellow]~[/yellow]",
            msg,
        )

    if data["cm_events"]:
        ok = data["cm_hybrid_pct"] >= TH["cm_hybrid_pct_min"]
        _row("CM hybrid", data["cm_hybrid_pct"],
             f"{int(data['cm_hybrid_pct']*100)}%", ok,
             "daemon healthy" if ok else "daemon flaky")

    if data["bm_invoked"]:
        g1_ok = data["g1_rate"] < TH["g1_fire_max_concern"]
        _row("G1 fire rate", data["g1_rate"], f"{int(data['g1_rate']*100)}%",
             g1_ok, "selective" if g1_ok else "always fires")

        # Only show g2_docs + g2_grep (the ones with thresholds); skip prefetch/hooks
        for block_name, threshold_key, msg_ok, msg_bad in (
            ("g2_docs", "g2_docs_over_concern", "selective", "over-matching"),
            ("g2_grep", "g2_grep_over_concern", "graph fresh", "graph stale"),
        ):
            c = data["block_counts"].get(block_name, 0)
            if c == 0:
                continue
            rate = c / data["n_inv"]
            ok = rate < TH[threshold_key]
            _row(block_name, rate, f"{int(rate*100)}% ({c})", ok,
                 msg_ok if ok else msg_bad)

        p95 = data["p95"]
        lat_ok = p95 < TH["bm25_p95_ms_yellow"]
        _row("Latency p95", p95 / TH["bm25_p95_ms_yellow"],
             f"{p95}ms", lat_ok, "fast" if lat_ok else "borderline")

    g, y, r = data["flags_g"], data["flags_y"], data["flags_r"]
    style, headline = _grade_style(g, y, r)
    items.append(Panel(
        health_table,
        title=f"[bold]System Health[/bold]  [{style}]{headline}[/{style}]",
        box=box.ROUNDED, border_style=style, padding=(0, 1),
    ))

    # ── Token Usage panel — usage-based metric (M27)
    tu = data.get("token_usage")
    if tu:
        tok_table = Table.grid(padding=(0, 1), expand=False)
        tok_table.add_column(style="bold", width=18)
        tok_table.add_column(width=22, justify="right", style="cyan")
        tok_table.add_column(style="dim")

        tok_table.add_row("Turns tracked", f"{tu['total_turns']}", "")
        tok_table.add_row("Avg injected/turn", f"{tu['avg_injected_tokens']:,} tokens",
                          f"(total {tu['total_injected_tokens']:,})")
        tok_table.add_row("Avg prompt/turn", f"{tu['avg_prompt_tokens']:,} tokens",
                          f"(total {tu['total_prompt_tokens']:,})")

        # Per-block breakdown
        if tu.get("by_block"):
            block_parts = []
            for blk, tokens in sorted(tu["by_block"].items(), key=lambda x: -x[1]):
                block_parts.append(f"[cyan]{blk}[/cyan] {tokens:,}")
            tok_table.add_row("By block", "", " · ".join(block_parts))

        items.append(Panel(
            tok_table,
            title="[bold]Token Usage (CTX-injected)[/bold]",
            box=box.ROUNDED, border_style="blue", padding=(0, 1),
        ))
    else:
        items.append(Text.from_markup(
            "[dim]Token usage: no data yet (enable CTX_TELEMETRY=1)[/dim]"
        ))

    # ── Quality notices — one-line summary
    if data["quality_notices"]:
        parts = [f"[yellow]~[/yellow] {m}" for m, _ in data["quality_notices"]]
        items.append(Text.from_markup(
            f"[bold yellow]Quality notices:[/bold yellow] {' · '.join(parts)} "
            f"[dim]· --explain/--deep to verify[/dim]"
        ))

    # ── Other signals — one-line summary (only if any)
    other = []
    if data["cm_warnings"]:
        other.append(f"[yellow]CM daemon-down ×{data['cm_warnings']}[/yellow]")
    if data["decision_hits"]:
        other.append(f"decision-keyword ×{data['decision_hits']}")
    if data["grep_signals"]:
        total = sum(data["grep_signals"].values())
        other.append(f"grep-fallback ×{total}")
    if other:
        items.append(Text.from_markup(f"[dim]Other:[/dim] {' · '.join(other)}"))

    items.append(Text.from_markup(
        f"[dim]Thresholds: CM ≥{int(TH['cm_hybrid_pct_min']*100)}% │ "
        f"g2_docs <{int(TH['g2_docs_over_concern']*100)}% │ "
        f"g2_grep <{int(TH['g2_grep_over_concern']*100)}% │ "
        f"p95 <{TH['bm25_p95_ms_yellow']}ms[/dim]"
    ))

    if live:
        from datetime import datetime as _dt
        items.append(Text.from_markup(
            f"[dim]Updated {_dt.now().strftime('%H:%M:%S')}  ·  Ctrl+C to exit[/dim]"
        ))

    return Group(*items)


def _render_rich(args, events, data):
    """One-shot render."""
    console = Console(force_terminal=True, color_system="truecolor")
    console.print(_build_rich_group(args, events, data))


def _render_rich_live(args, refresh_seconds: float = 2.0):
    """Watch mode: tail-follow telemetry JSONL and re-render every N seconds.

    Avoids re-parsing the whole file each tick — on first tick reads once,
    then only appends new lines from the saved file position. Handles file
    truncation/rotation by falling back to full re-read when size shrinks."""
    import time
    console = Console(force_terminal=True, color_system="truecolor")
    try:
        cutoff = parse_since(args.since)
    except ValueError as e:
        print(e, file=sys.stderr); sys.exit(2)

    # Cache: persistent events + file position + last size (for rotation detection)
    # `data` is the aggregated metrics dict — only recomputed when events change.
    state = {"events": [], "pos": 0, "size": 0, "data": None}

    def _read_new():
        """Append newly-added events to state['events']. Drop events older than cutoff."""
        if not LOG.exists():
            return
        try:
            st = LOG.stat()
        except OSError:
            return
        # Rotation / truncation → re-read from scratch
        if st.st_size < state["size"]:
            state["events"].clear()
            state["pos"] = 0
        state["size"] = st.st_size
        if state["pos"] >= st.st_size:
            return
        try:
            with LOG.open() as f:
                f.seek(state["pos"])
                for line in f:
                    if not line.endswith("\n"):  # partial line — stop before it
                        break
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if cutoff is None or r.get("ts", 0) >= cutoff:
                        state["events"].append(r)
                state["pos"] = f.tell()
        except OSError:
            return
        # Drop events that have aged out of the window (cheap: only check front)
        if cutoff is not None and state["events"]:
            while state["events"] and state["events"][0].get("ts", 0) < cutoff:
                state["events"].pop(0)

    def _snapshot():
        """Render current state. Only re-parses file + recomputes metrics
        when the file has grown since the last tick; otherwise re-uses the
        cached data dict so the render is essentially free. The timestamp
        inside _build_rich_group updates on every call."""
        prev_size = state["size"]
        _read_new()
        events = state["events"]
        if not events:
            return Text.from_markup(
                f"[yellow]No events in {LOG} matching --since={args.since}.[/yellow]\n"
                f"[dim]Enable: touch ~/.claude/ctx-telemetry.enabled[/dim]"
            )
        # Recompute metrics only when file changed (or first call)
        if state["data"] is None or state["size"] != prev_size:
            state["data"] = _compute_metrics(events)
        return _build_rich_group(args, events, state["data"], live=True)

    try:
        with Live(_snapshot(), console=console, refresh_per_second=4,
                  screen=False, transient=False) as live:
            while True:
                time.sleep(refresh_seconds)
                live.update(_snapshot())
    except KeyboardInterrupt:
        console.print("[dim]— exited watch mode —[/dim]")


def _compute_token_usage(token_events):
    """Aggregate token_usage events into summary metrics.

    Returns dict with:
      - total_turns: number of token_usage events
      - total_injected_tokens: sum of injected_tokens across all events
      - avg_injected_tokens: mean injected tokens per turn
      - total_prompt_tokens: sum of prompt_tokens across all events
      - avg_prompt_tokens: mean prompt tokens per turn
      - by_block: per-block token totals {block_name: total_tokens}
    """
    if not token_events:
        return None

    total_injected = sum(e.get("injected_tokens", 0) for e in token_events)
    total_prompt = sum(e.get("prompt_tokens", 0) for e in token_events)
    by_block: dict = {}
    for e in token_events:
        bt = e.get("block_tokens", {})
        for block, tokens in bt.items():
            by_block[block] = by_block.get(block, 0) + tokens

    return {
        "total_turns": len(token_events),
        "total_injected_tokens": total_injected,
        "avg_injected_tokens": round(total_injected / len(token_events), 1),
        "total_prompt_tokens": total_prompt,
        "avg_prompt_tokens": round(total_prompt / len(token_events), 1),
        "by_block": by_block,
    }


def _compute_metrics(events):
    """Aggregate events into a metrics dict for rich/plain renderers."""
    by_type = defaultdict(list)
    for e in events:
        by_type[e["type"]].append(e)

    # CM
    cm_events = [e for e in by_type["mode_switch"] if e.get("hook") == "chat-memory"]
    cm_hybrid = sum(1 for e in cm_events if e.get("to_mode") == "hybrid")
    cm_bm25 = sum(1 for e in cm_events if e.get("to_mode") == "bm25")
    cm_warnings = sum(1 for e in by_type["warning_fired"] if e.get("hook") == "chat-memory")
    cm_hybrid_pct = cm_hybrid / len(cm_events) if cm_events else 0.0

    # bm25
    bm_invoked = [e for e in by_type["hook_invoked"] if e.get("hook") == "bm25-memory"]
    blocks = [e for e in by_type["block_fired"] if e.get("hook") == "bm25-memory"]
    n_inv = len(bm_invoked)
    g1_fires = sum(1 for e in blocks if e.get("block") == "g1_decisions")
    g1_rate = g1_fires / n_inv if n_inv else 0.0
    block_counts = Counter(e.get("block") for e in blocks)
    dur = [e.get("duration_ms", 0) for e in bm_invoked]
    dur_sorted = sorted(dur)
    p95 = dur_sorted[min(len(dur_sorted)-1, int(len(dur_sorted)*0.95))] if dur_sorted else 0

    # Flags for overall grade (health-critical only)
    flags_g = flags_y = flags_r = 0
    quality_notices = []
    if cm_events:
        if cm_hybrid_pct >= TH["cm_hybrid_pct_min"]:
            flags_g += 1
        elif cm_hybrid_pct >= TH["cm_hybrid_pct_red"]:
            flags_y += 1
        else:
            flags_r += 1
    if bm_invoked:
        # G1 rate → quality notice (not a health flag)
        if g1_rate >= TH["g1_fire_max_concern"]:
            quality_notices.append(("g1", "always fires — use --explain g1 to spot-check"))
        elif g1_rate < TH["g1_fire_min"] and n_inv >= 5:
            quality_notices.append(("g1", "low fire rate — corpus may be empty"))
        # g2_docs → quality notice
        if block_counts.get("g2_docs", 0) / n_inv >= TH["g2_docs_over_concern"]:
            quality_notices.append(("g2_docs", "over-matching — use --explain g2_docs to verify"))
        # g2_grep → health flag
        if block_counts.get("g2_grep", 0) / n_inv >= TH["g2_grep_over_concern"]:
            flags_y += 1
        else:
            flags_g += 1
        # Latency → health flag
        if p95 >= TH["bm25_p95_ms_red"]:
            flags_r += 1
        elif p95 >= TH["bm25_p95_ms_yellow"]:
            flags_y += 1
        else:
            flags_g += 1

    # Activity histogram
    daily_counts = Counter()
    for e in events:
        try:
            d = datetime.fromtimestamp(e["ts"], tz=timezone.utc).strftime("%a %m-%d")
            daily_counts[d] += 1
        except Exception:
            continue

    return {
        "cm_events": cm_events, "cm_hybrid": cm_hybrid, "cm_bm25": cm_bm25,
        "cm_warnings": cm_warnings, "cm_hybrid_pct": cm_hybrid_pct,
        "bm_invoked": bm_invoked, "blocks": blocks, "n_inv": n_inv,
        "g1_fires": g1_fires, "g1_rate": g1_rate,
        "block_counts": block_counts, "p95": p95, "dur": dur,
        "flags_g": flags_g, "flags_y": flags_y, "flags_r": flags_r,
        "quality_notices": quality_notices,
        "daily_counts": daily_counts,
        "decision_hits": len(by_type.get("decision_captured", [])),
        "grep_signals": Counter(e.get("signal") for e in by_type.get("grep_signal", [])),
        "token_usage": _compute_token_usage(by_type.get("token_usage", [])),
        "by_type": by_type,
    }


# ── Main ──────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--since", default="7d", help="today / 24h / 7d / 30d / all (default 7d)")
    ap.add_argument("--plain", action="store_true", help="disable ANSI colors")
    ap.add_argument("--explain", choices=["g1", "g2_docs", "g2_grep", "latency"],
                    help="run a concrete spot-check for one yellow/red metric")
    ap.add_argument("--deep", action="store_true",
                    help="auto-run spot-checks for every yellow/red metric after the main report")
    ap.add_argument("--watch", nargs="?", const=2.0, type=float, default=None,
                    metavar="SECONDS",
                    help="live dashboard mode — refresh every N seconds (default 2). Ctrl+C to exit")
    args = ap.parse_args()

    # ── Watch mode: live dashboard
    if args.watch is not None:
        if not _RICH_OK:
            print("--watch requires the 'rich' library (pip install rich)", file=sys.stderr)
            sys.exit(2)
        _render_rich_live(args, refresh_seconds=args.watch)
        return

    if args.plain:
        global COLOR, GREEN, YELLOW, RED, DIM, BOLD, RESET, FLAG_G, FLAG_Y, FLAG_R
        COLOR = False
        GREEN = YELLOW = RED = DIM = BOLD = RESET = ""
        FLAG_G = "✓"; FLAG_Y = "~"; FLAG_R = "✗"

    try:
        cutoff = parse_since(args.since)
    except ValueError as e:
        print(e, file=sys.stderr); sys.exit(2)

    events = load_events(cutoff)

    # ── --explain dispatch (runs and exits before main report)
    if args.explain:
        handler = {
            "g1": _explain_g1,
            "g2_docs": _explain_g2_docs,
            "g2_grep": _explain_g2_grep,
            "latency": lambda: _explain_latency(events),
        }[args.explain]
        handler()
        return
    if not events:
        gate_on = (os.environ.get("CTX_TELEMETRY") == "1"
                   or Path(os.path.expanduser("~/.claude/ctx-telemetry.enabled")).exists())
        print(f"No events in {LOG} matching --since={args.since}")
        print(f"  File exists: {LOG.exists()}  |  gate: {'ENABLED' if gate_on else 'DISABLED'}")
        if not gate_on:
            print("  Enable: touch ~/.claude/ctx-telemetry.enabled")
        sys.exit(0)

    # ── Rich UI path (default) — panels + progress bars
    if _RICH_OK and not args.plain:
        data = _compute_metrics(events)
        _render_rich(args, events, data)
        # --deep: run spot-checks (still plain text from the _explain_* functions)
        if args.deep and (data["flags_y"] + data["flags_r"] + len(data["quality_notices"])) > 0:
            print("\n" + "=" * 72)
            print(f"{BOLD}Deep dive — auto-running spot-checks{RESET}")
            print("=" * 72)
            bm_invoked = data["bm_invoked"]
            n_inv = data["n_inv"]
            block_counts = data["block_counts"]
            if bm_invoked and (data["g1_rate"] >= TH["g1_fire_max_concern"]
                               or data["g1_rate"] < TH["g1_fire_min"]):
                print(); _explain_g1()
            if bm_invoked and block_counts.get("g2_docs", 0) / n_inv >= TH["g2_docs_over_concern"]:
                print(); _explain_g2_docs()
            if bm_invoked and block_counts.get("g2_grep", 0) / n_inv >= TH["g2_grep_over_concern"]:
                print(); _explain_g2_grep()
            if bm_invoked and data["p95"] >= TH["bm25_p95_ms_yellow"]:
                print(); _explain_latency(events)
        return

    # ── Plain text fallback (--plain or rich unavailable)
    by_type = defaultdict(list)
    for e in events:
        by_type[e["type"]].append(e)

    flags_collected = []   # health-critical flags feeding Overall grade
    quality_notices = []   # rate-based heuristics (informational, don't degrade grade)

    # ── Header
    print(f"{BOLD}CTX Telemetry{RESET}  since={args.since}  |  {len(events)} events  |  {LOG}")
    print("─" * 72)

    # Sample-size warning
    if len(events) < TH["min_events_for_eval"]:
        print(f"{YELLOW}⚠ Sample too small for reliable eval (<{TH['min_events_for_eval']} events). "
              f"Keep using Claude Code; most verdicts below are provisional.{RESET}\n")

    # ── 1. Daily histogram
    print(f"{BOLD}Activity{RESET}  (events per day)")
    print(daily_histogram(events))

    # ── 2. CM (chat-memory)
    cm_events = [e for e in by_type["mode_switch"] if e.get("hook") == "chat-memory"]
    cm_hybrid = sum(1 for e in cm_events if e.get("to_mode") == "hybrid")
    cm_bm25 = sum(1 for e in cm_events if e.get("to_mode") == "bm25")
    cm_warnings = sum(1 for e in by_type["warning_fired"] if e.get("hook") == "chat-memory")
    if cm_events:
        hybrid_pct = cm_hybrid / len(cm_events)
        flag, msg = verdict_cm_hybrid(hybrid_pct)
        flags_collected.append(flag)
        print(f"\n{BOLD}CM (chat-memory){RESET}  {flag} {msg}")
        print(f"  hybrid:  {cm_hybrid} ({fmt_pct(cm_hybrid, len(cm_events))})   "
              f"bm25-fallback: {cm_bm25} ({fmt_pct(cm_bm25, len(cm_events))})")
        if cm_warnings:
            print(f"  {FLAG_Y} ⚠ daemon-down warnings this window: {cm_warnings}")
        cm_dur = [e.get("duration_ms", 0) for e in cm_events if e.get("duration_ms") is not None]
        if cm_dur:
            print(f"  query latency:  {fmt_ms(cm_dur)}")

    # ── 3. bm25-memory (G1 + G2)
    bm_invoked = [e for e in by_type["hook_invoked"] if e.get("hook") == "bm25-memory"]
    blocks = [e for e in by_type["block_fired"] if e.get("hook") == "bm25-memory"]
    if bm_invoked:
        n_inv = len(bm_invoked)
        print(f"\n{BOLD}bm25-memory{RESET}  ({n_inv} invocations)")

        # G1 — rate is informational (not a health signal); goes to quality_notices
        g1_fires = sum(1 for e in blocks if e.get("block") == "g1_decisions")
        g1_counts = [e.get("count", 0) for e in blocks if e.get("block") == "g1_decisions"]
        median_dec = int(statistics.median(g1_counts)) if g1_counts else 0
        g1_rate = g1_fires / n_inv
        flag, msg = verdict_g1_fire(g1_rate, n_inv)
        if flag == FLAG_Y:
            quality_notices.append(("g1", msg))
        print(f"  G1 (decisions):     {flag}  {fmt_pct(g1_fires, n_inv)}  "
              f"(median top-{median_dec})  {DIM}{msg}{RESET}")

        # G2 blocks — g2_docs rate is informational; g2_grep is a real health signal
        block_counts = Counter(e.get("block") for e in blocks)
        for block_name in ("g2_docs", "g2_prefetch", "g2_grep", "g2_hooks"):
            c = block_counts.get(block_name, 0)
            if c == 0:
                continue
            rate = c / n_inv
            flag, msg = verdict_g2_block(block_name, rate)
            if flag != FLAG_G:
                if block_name == "g2_docs":
                    quality_notices.append(("g2_docs", msg))
                else:
                    flags_collected.append(flag)
            print(f"  {block_name:18s}  {flag}  {fmt_pct(c, n_inv)}  "
                  f"({c} fires)  {DIM}{msg}{RESET}")

        # Latency
        dur = [e.get("duration_ms", 0) for e in bm_invoked]
        dur_sorted = sorted(dur)
        p95 = dur_sorted[min(len(dur_sorted) - 1, int(len(dur_sorted) * 0.95))] if dur_sorted else 0
        flag, msg = verdict_latency(p95)
        flags_collected.append(flag)
        print(f"  total latency:      {flag}  {fmt_ms(dur)}  {DIM}{msg}{RESET}")

    # ── 4. auto-index removed iter 18.2: hook is retired (not wired in
    # settings.json per CLAUDE.md sync). The event type remains in
    # _ctx_telemetry.py whitelist for future reuse but is no longer
    # surfaced in the report to reduce noise.

    # ── 5. Decision keywords
    dec = by_type.get("decision_captured", [])
    if dec:
        print(f"\n{BOLD}Decision-keyword{RESET}  {len(dec)} hits")

    # ── 6. Grep fallback
    grep_events = by_type.get("grep_signal", [])
    if grep_events:
        signals = Counter(e.get("signal") for e in grep_events)
        print(f"\n{BOLD}Grep-fallback{RESET}  {len(grep_events)} hints  {dict(signals)}")

    # ── 7. System Health (top) + Quality Alerts (bottom)
    print("\n" + "─" * 72)
    color, summary = overall_grade(flags_collected)
    print(f"{BOLD}System Health{RESET}  {color}{summary}{RESET}  "
          f"{DIM}— CM, g2_grep, latency{RESET}")

    # Health-critical items that need attention
    y_count = flags_collected.count(FLAG_Y)
    r_count = flags_collected.count(FLAG_R)
    if y_count + r_count > 0:
        print(f"\n{BOLD}Health issues{RESET}")
        if cm_events and cm_hybrid / len(cm_events) < TH["cm_hybrid_pct_min"]:
            print(f"  • CM hybrid dropped below {int(TH['cm_hybrid_pct_min']*100)}% → vec-daemon reliability")
        if bm_invoked:
            if block_counts.get("g2_grep", 0) / n_inv >= TH["g2_grep_over_concern"]:
                print(f"  • g2_grep fallback ≥{int(TH['g2_grep_over_concern']*100)}% — graph DB stale or incomplete")
            if p95 >= TH["bm25_p95_ms_yellow"]:
                print(f"  • bm25-memory p95 over {TH['bm25_p95_ms_yellow']}ms — cold-start or corpus rebuild")

    # Quality notices (rate-based heuristics — informational only)
    if quality_notices:
        print(f"\n{BOLD}Quality notices{RESET}  {DIM}(rate-based, not health-critical){RESET}")
        for metric, msg in quality_notices:
            print(f"  {FLAG_Y} {metric:10s}  {msg}")
        print(f"\n{DIM}Verify with → ctx-report.py --explain <metric>  "
              f"(metrics: g1, g2_docs, g2_grep, latency)  "
              f"— or --deep to auto-run all{RESET}")

    # ── --deep: auto-run spot-checks for health issues AND quality notices
    total_flagged = y_count + r_count + len(quality_notices)
    if args.deep and total_flagged > 0:
        print("\n" + "=" * 72)
        print(f"{BOLD}Deep dive — auto-running spot-checks{RESET}")
        print("=" * 72)
        # G1 quality check (if notice present)
        if bm_invoked and (g1_fires / n_inv >= TH["g1_fire_max_concern"]
                           or g1_fires / n_inv < TH["g1_fire_min"]):
            print(); _explain_g1()
        # g2_docs quality check (if notice present)
        if bm_invoked and block_counts.get("g2_docs", 0) / n_inv >= TH["g2_docs_over_concern"]:
            print(); _explain_g2_docs()
        # g2_grep health check (if flagged)
        if bm_invoked and block_counts.get("g2_grep", 0) / n_inv >= TH["g2_grep_over_concern"]:
            print(); _explain_g2_grep()
        # Latency health check (if flagged)
        if bm_invoked and p95 >= TH["bm25_p95_ms_yellow"]:
            print(); _explain_latency(events)
    elif total_flagged == 0:
        print(f"\n{GREEN}All signals within healthy ranges for this window.{RESET}")

    # Data hygiene
    print(f"\n{DIM}Thresholds: CM hybrid ≥{int(TH['cm_hybrid_pct_min']*100)}%  |  "
          f"g2_docs <{int(TH['g2_docs_over_concern']*100)}%  |  "
          f"g2_grep <{int(TH['g2_grep_over_concern']*100)}%  |  "
          f"bm25 p95 <{TH['bm25_p95_ms_yellow']}ms  |  "
          f"min n={TH['min_events_for_eval']}{RESET}")


if __name__ == "__main__":
    main()
