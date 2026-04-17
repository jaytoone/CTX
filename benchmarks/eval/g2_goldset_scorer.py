#!/usr/bin/env python3
"""
g2_goldset_scorer.py — Score any G2 symbol-search variant against g2_goldset.json.

Usage:
    python3 benchmarks/eval/g2_goldset_scorer.py                 # score OLD (LIKE + length-ASC)
    python3 benchmarks/eval/g2_goldset_scorer.py --variant bm25  # score NEW-v3 (BM25 + v3 tokenizer)

Metrics:
  Hit@5       — any gold item appears in top-5 (1/0 per query → mean)
  MRR         — reciprocal rank of first gold item in top-N (N=20)
  RankedHit@5 — fraction of gold top-5 that appears in result top-5 (fractional)
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
GOLDSET = Path(__file__).parent / "g2_goldset.json"
DB = Path(os.path.expanduser("~/.cache/codebase-memory-mcp/home-jayone-Project-CTX.db"))


def search_OLD(keywords, limit=5):
    """Current hook behavior: per-keyword LIKE %kw% + length(name) ASC."""
    db = sqlite3.connect(str(DB))
    results, seen = [], set()
    for kw in keywords:
        rows = db.execute(
            "SELECT DISTINCT label, name, file_path FROM nodes "
            "WHERE name LIKE ? AND label IN ('Function','Method','Class') "
            "ORDER BY length(name) ASC LIMIT ?",
            (f"%{kw}%", 3),
        ).fetchall()
        for r in rows:
            key = (r[1], r[2])
            if key not in seen:
                seen.add(key)
                results.append(r)
        if len(results) < limit:
            frows = db.execute(
                "SELECT DISTINCT label, name, file_path FROM nodes "
                "WHERE file_path LIKE ? AND label IN ('Module','File') "
                "ORDER BY length(file_path) ASC LIMIT ?",
                (f"%{kw}%", 2),
            ).fetchall()
            for r in frows:
                key = (r[1], r[2])
                if key not in seen:
                    seen.add(key)
                    results.append(r)
    db.close()
    return results[:limit]


def _code_tokenize_v3(text):
    text = re.sub(r"([a-z])([A-Z])", r"\1_\2", text)
    text = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", text)
    parts = re.findall(r"[a-zA-Z0-9가-힣]+", text.lower())
    return [p for p in parts if p]


def search_BM25_v3(keywords, limit=5):
    """v3 tokenizer + BM25 over (name + file_path). From iter 1 exploration."""
    from rank_bm25 import BM25Okapi

    db = sqlite3.connect(str(DB))
    like = " OR ".join(["name LIKE ?"] * len(keywords))
    path_like = " OR ".join(["file_path LIKE ?"] * len(keywords))
    p = [f"%{kw}%" for kw in keywords]
    rows_name = db.execute(
        f"SELECT DISTINCT label, name, file_path FROM nodes "
        f"WHERE ({like}) AND label IN ('Function','Method','Class') LIMIT 60",
        p,
    ).fetchall()
    rows_path = db.execute(
        f"SELECT DISTINCT label, name, file_path FROM nodes "
        f"WHERE ({path_like}) AND label IN ('Module','File') LIMIT 40",
        p,
    ).fetchall()
    db.close()
    cands, seen = [], set()
    for r in rows_name + rows_path:
        k = (r[1], r[2])
        if k not in seen:
            seen.add(k)
            cands.append(r)
    if not cands:
        return []
    if len(cands) <= limit:
        return cands
    tokenized = [_code_tokenize_v3(f"{r[1]} {r[2]}") or [""] for r in cands]
    bm25 = BM25Okapi(tokenized)
    q = []
    for kw in keywords:
        q.extend(_code_tokenize_v3(kw))
    scores = bm25.get_scores(q)
    ranked = sorted(enumerate(scores), key=lambda x: -x[1])
    return [cands[i] for i, _ in ranked[:limit]]


def search_ROUTER(keywords, limit=5):
    """T1-C router: broad queries (>=5 tokens) → length-ASC, else BM25 v3."""
    if len(keywords) >= 5:
        return search_OLD(keywords, limit)
    return search_BM25_v3(keywords, limit)


VARIANTS = {"old": search_OLD, "bm25": search_BM25_v3, "router": search_ROUTER}


def score_query(results, gold):
    gold_keys = {(g["name"], g["label"]) for g in gold}
    top5 = results[:5]
    top5_keys = {(r[1], r[0]) for r in top5}
    hit5 = 1 if (top5_keys & gold_keys) else 0
    ranked_hit = len(top5_keys & gold_keys) / max(1, len(gold_keys))
    mrr = 0.0
    for i, r in enumerate(results[:20]):
        if (r[1], r[0]) in gold_keys:
            mrr = 1 / (i + 1)
            break
    return {"hit5": hit5, "ranked_hit5": ranked_hit, "mrr": mrr, "top5": top5}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(VARIANTS.keys()), default="old")
    args = ap.parse_args()

    if not DB.exists():
        sys.exit(f"DB missing: {DB}")

    goldset = json.loads(GOLDSET.read_text())
    search_fn = VARIANTS[args.variant]

    per_q = []
    print(f"Variant: {args.variant}  DB: {DB.name}")
    print(f"{'ID':<20s} {'Hit@5':>6s} {'MRR':>6s} {'RH@5':>6s}  Top-5 names")
    print("-" * 100)
    for q in goldset["queries"]:
        results = search_fn(q["keywords"], limit=10)
        s = score_query(results, q["gold"])
        per_q.append(s)
        top5_str = ", ".join(r[1][:18] for r in s["top5"])
        print(f"{q['id']:<20s} {s['hit5']:>6d} {s['mrr']:>6.2f} {s['ranked_hit5']:>6.2f}  {top5_str[:72]}")

    n = len(per_q)
    avg_hit5 = sum(p["hit5"] for p in per_q) / n
    avg_mrr = sum(p["mrr"] for p in per_q) / n
    avg_rh5 = sum(p["ranked_hit5"] for p in per_q) / n
    print("-" * 100)
    print(f"{'AVG':<20s} {avg_hit5:>6.2f} {avg_mrr:>6.2f} {avg_rh5:>6.2f}  (n={n})")


if __name__ == "__main__":
    main()
