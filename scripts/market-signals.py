#!/usr/bin/env python3
"""
market-signals.py — CTX weekly market signal monitor

Pulls from 3 public APIs (no auth required):
  1. GitHub issues: anthropics/claude-code — pain signals CTX solves
  2. PyPI stats:    ctx-retriever download trend vs baseline
  3. HN Algolia:   developer discourse on Claude Code memory/context

Usage:
    python3 scripts/market-signals.py          # full report
    python3 scripts/market-signals.py --json   # machine-readable output
    python3 scripts/market-signals.py --save   # append to docs/research/signal-log.jsonl

Baseline (2026-05-06): 39/day · 633/week · 1096/month
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────
PYPI_PACKAGE   = "ctx-retriever"
PYPI_BASELINE  = {"day": 39, "week": 633, "month": 1096}  # 2026-05-06

GITHUB_REPO    = "anthropics/claude-code"
GITHUB_KEYWORDS = [
    "context loss", "cross-session", "forgot", "memory",
    "session memory", "remember", "context window",
]

HN_KEYWORDS = [
    "claude code memory", "coding agent context",
    "claude code context", "cross-session memory",
]

SIGNAL_LOG = "docs/research/signal-log.jsonl"

TIMEOUT = 8


def _get(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ctx-market-signals/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)
    except Exception as e:
        print(f"  [WARN] fetch failed: {url[:60]}... — {e}", file=sys.stderr)
        return None


# ── 1. PyPI downloads ────────────────────────────────────────────────

def pypi_stats() -> dict:
    # pypistats.org sometimes rejects default User-Agent — try with Accept header
    try:
        req = urllib.request.Request(
            f"https://pypistats.org/api/packages/{PYPI_PACKAGE}/recent",
            headers={"User-Agent": "ctx-market-signals/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.load(r)
    except Exception as e:
        print(f"  [WARN] pypi fetch failed: {e}", file=sys.stderr)
        return {}
    if not data:
        return {}
    d = data.get("data", {})
    result = {
        "day":   d.get("last_day", 0),
        "week":  d.get("last_week", 0),
        "month": d.get("last_month", 0),
    }
    result["delta_day"]   = result["day"]   - PYPI_BASELINE["day"]
    result["delta_week"]  = result["week"]  - PYPI_BASELINE["week"]
    result["delta_month"] = result["month"] - PYPI_BASELINE["month"]
    result["pct_week"]    = round((result["delta_week"] / PYPI_BASELINE["week"]) * 100, 1) if PYPI_BASELINE["week"] else 0
    return result


# ── 2. GitHub issues ─────────────────────────────────────────────────

def github_issues() -> list[dict]:
    hits = []
    seen = set()
    for kw in GITHUB_KEYWORDS:
        q = urllib.parse.quote(f"{kw} repo:{GITHUB_REPO} is:issue")
        url = f"https://api.github.com/search/issues?q={q}&sort=created&order=desc&per_page=5"
        data = _get(url)
        if not data:
            continue
        for item in data.get("items", []):
            if item["number"] in seen:
                continue
            seen.add(item["number"])
            hits.append({
                "number":  item["number"],
                "title":   item["title"],
                "state":   item["state"],
                "created": item["created_at"][:10],
                "url":     item["html_url"],
                "keyword": kw,
            })
    # Sort newest first
    hits.sort(key=lambda x: x["created"], reverse=True)
    return hits[:15]


# ── 3. CTX repo itself ──────────────────────────────────────────────

CTX_REPO = "jaytoone/CTX"

def ctx_repo_stats() -> dict:
    """Track CTX's own GitHub repo — stars, forks, open issues, latest release."""
    data = _get(f"https://api.github.com/repos/{CTX_REPO}")
    if not data:
        return {}
    result = {
        "stars":       data.get("stargazers_count", 0),
        "forks":       data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "watchers":    data.get("watchers_count", 0),
        "pushed_at":   (data.get("pushed_at") or "")[:10],
    }
    # Latest release tag
    rel = _get(f"https://api.github.com/repos/{CTX_REPO}/releases/latest")
    if rel:
        result["latest_release"] = rel.get("tag_name", "")
        result["release_date"]   = (rel.get("published_at") or "")[:10]
    # Open PRs
    prs = _get(f"https://api.github.com/repos/{CTX_REPO}/pulls?state=open&per_page=5")
    if prs:
        result["open_prs"] = len(prs)
        result["pr_titles"] = [pr["title"][:60] for pr in prs]
    return result


# ── 4. Channel reactions (direct post stats) ─────────────────────────
# Tracks engagement on the actual CTX posts across all channels

CTX_CHANNELS = {
    "geeknews": {
        "name": "GeekNews",
        "url":  "https://news.hada.io/topic?id=29124",
        "type": "html_scrape",
    },
    "hn": {
        "name": "Hacker News",
        "url":  "https://news.ycombinator.com/item?id=48017090",
        "api":  "https://hn.algolia.com/api/v1/items/48017090",
        "type": "hn_api",
    },
    "devto": {
        "name": "Dev.to",
        "url":  "https://dev.to/jaewon_jang_d63fddcf69ac2/ctx-i-gave-claude-code-a-memory-that-actually-works-45id",
        "api":  "https://dev.to/api/articles/2597891",
        "type": "devto_api",
    },
    "github": {
        "name": "GitHub (CTX repo)",
        "url":  "https://github.com/jaytoone/CTX",
        "api":  "https://api.github.com/repos/jaytoone/CTX",
        "type": "github_api",
    },
}


def channel_reactions() -> dict:
    """Fetch engagement metrics for each CTX post/channel."""
    results = {}
    for ch_id, ch in CTX_CHANNELS.items():
        result = {"name": ch["name"], "url": ch["url"]}
        try:
            if ch["type"] == "hn_api":
                data = _get(ch["api"])
                if data:
                    result["points"]   = data.get("points") or 0
                    result["comments"] = len(data.get("children") or [])
            elif ch["type"] == "devto_api":
                data = _get(ch["api"])
                if data:
                    result["reactions"] = data.get("public_reactions_count", 0)
                    result["comments"]  = data.get("comments_count", 0)
                    result["reads"]     = data.get("page_views_count", 0)
            elif ch["type"] == "github_api":
                data = _get(ch["api"])
                if data:
                    result["stars"]    = data.get("stargazers_count", 0)
                    result["forks"]    = data.get("forks_count", 0)
                    result["issues"]   = data.get("open_issues_count", 0)
            elif ch["type"] == "html_scrape":
                import re as _re
                req = urllib.request.Request(ch["url"], headers={"User-Agent": "ctx-market-signals/1.0"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    html = r.read().decode("utf-8", errors="replace")
                # GeekNews: <span id='tp{id}'>N</span> = points, data-topic-comment-count='N' = comments
                m_pts = _re.search(r"<span id='tp\d+'>([\d]+)</span>", html)
                m_cmt = _re.search(r"data-topic-comment-count='(\d+)'", html)
                if m_pts: result["points"] = int(m_pts.group(1))
                if m_cmt: result["comments"] = int(m_cmt.group(1))
        except Exception as e:
            result["error"] = str(e)[:60]
        results[ch_id] = result
    return results


# ── 5. HN Algolia ────────────────────────────────────────────────────

def hn_hits() -> list[dict]:
    results = []
    seen = set()
    for kw in HN_KEYWORDS:
        q = urllib.parse.quote(kw)
        url = f"https://hn.algolia.com/api/v1/search?query={q}&tags=story,comment&hitsPerPage=5"
        data = _get(url)
        if not data:
            continue
        for hit in data.get("hits", []):
            oid = hit.get("objectID")
            if oid in seen:
                continue
            seen.add(oid)
            results.append({
                "title":   hit.get("title") or hit.get("comment_text", "")[:80],
                "author":  hit.get("author", ""),
                "points":  hit.get("points", 0),
                "created": (hit.get("created_at") or "")[:10],
                "url":     f"https://news.ycombinator.com/item?id={oid}",
                "keyword": kw,
            })
    results.sort(key=lambda x: x.get("points") or 0, reverse=True)
    return results[:10]


# ── Report ───────────────────────────────────────────────────────────

def render(pypi: dict, gh: list, hn: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# CTX Market Signal Report — {now}", ""]

    # PyPI
    lines.append("## PyPI Downloads (ctx-retriever)")
    if pypi:
        d, w, m = pypi["day"], pypi["week"], pypi["month"]
        dd, dw, dm = pypi["delta_day"], pypi["delta_week"], pypi["delta_month"]
        pct = pypi["pct_week"]
        arrow = "+" if dw >= 0 else ""
        lines.append(f"  Day:   {d:>5}  ({arrow}{dd:+d} vs baseline)")
        lines.append(f"  Week:  {w:>5}  ({arrow}{dw:+d}, {arrow}{pct}%)")
        lines.append(f"  Month: {m:>5}  ({arrow}{dm:+d} vs baseline)")
        if abs(pct) > 20:
            lines.append(f"  ** SIGNAL: week downloads {'up' if pct > 0 else 'down'} {abs(pct)}% vs baseline **")
    else:
        lines.append("  [unavailable]")

    # GitHub
    lines.append("")
    lines.append(f"## GitHub Issues — {GITHUB_REPO}")
    lines.append(f"  Keywords: {', '.join(GITHUB_KEYWORDS)}")
    if gh:
        for item in gh[:8]:
            state_tag = "[open]" if item["state"] == "open" else "[closed]"
            lines.append(f"  {state_tag} #{item['number']} ({item['created']}) {item['title'][:70]}")
            lines.append(f"         match: '{item['keyword']}' | {item['url']}")
    else:
        lines.append("  No recent matches.")

    # HN
    lines.append("")
    lines.append("## Hacker News")
    lines.append(f"  Keywords: {', '.join(HN_KEYWORDS)}")
    if hn:
        for item in hn[:6]:
            pts = f"{item['points']}pts" if item.get("points") else "—"
            lines.append(f"  [{pts}] ({item['created']}) {item['title'][:70]}")
            lines.append(f"         match: '{item['keyword']}' | {item['url']}")
    else:
        lines.append("  No recent matches.")

    lines.append("")
    lines.append(f"Baseline date: 2026-05-06 | day={PYPI_BASELINE['day']} week={PYPI_BASELINE['week']} month={PYPI_BASELINE['month']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="CTX market signal monitor")
    parser.add_argument("--json",  action="store_true", help="Output raw JSON")
    parser.add_argument("--save",  action="store_true", help="Append to signal-log.jsonl")
    parser.add_argument("--pypi-only",   action="store_true")
    parser.add_argument("--github-only", action="store_true")
    parser.add_argument("--hn-only",     action="store_true")
    args = parser.parse_args()

    run_all = not (args.pypi_only or args.github_only or args.hn_only)

    print("Fetching signals...", file=sys.stderr)
    pypi     = pypi_stats()                   if (run_all or args.pypi_only)   else {}
    gh       = github_issues()                if (run_all or args.github_only) else []
    hn       = hn_hits()                      if (run_all or args.hn_only)     else []
    ctx      = ctx_repo_stats()               if run_all                       else {}
    channels = channel_reactions()            if run_all                       else {}

    result = {
        "ts":       datetime.now(timezone.utc).isoformat(),
        "pypi":     pypi,
        "github":   gh,
        "hn":       hn,
        "ctx_repo": ctx,
        "channels": channels,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    report = render(pypi, gh, hn)
    print(report)

    if args.save:
        import os
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), SIGNAL_LOG)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(result) + "\n")
        print(f"\n[saved to {SIGNAL_LOG}]", file=sys.stderr)


if __name__ == "__main__":
    main()
