"""
g1_regression_ctx_v2.py — G1 Recall@7 regression test: ctx vs ctx_v2.

P0 gate: Does Porter stemmer + recency boost in ctx_v2 hurt the existing
G1 benchmark (current production Recall@7 = 0.746)?

Method:
  1. Load 59 QA pairs + decision_commits
  2. Build corpus as (subject, hash) tuples, same as production bm25-memory.py
  3. Run BOTH retrievers on each query, compare Recall@7 by commit_hash match
  4. Report: absolute/relative accuracy delta + per-query wins/losses
"""
import json
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "benchmarks" / "eval"))

HOOK = Path.home() / ".claude" / "hooks" / "bm25-memory.py"
spec = importlib.util.spec_from_file_location("bm25mem", str(HOOK))
bm25mem = importlib.util.module_from_spec(spec); spec.loader.exec_module(bm25mem)

from retrieve_ctx_v2 import retrieve_ctx_v2, _stem_tokens
from rank_bm25 import BM25Okapi
import math


def build_corpus(commits):
    """Commit list -> corpus of {subject, text, hash, date}."""
    corpus = []
    for c in commits:
        subj = c.get("subject", "")
        if subj:
            corpus.append({
                "subject": subj,
                "text": subj,
                "hash": c.get("hash", ""),
                "date": c.get("timestamp", "")[:10] if c.get("timestamp") else None,
            })
    return corpus


def retrieve_ctx_production(corpus, query, top_k=7):
    """Production path — bm25_rank_decisions with default min_score=0.5."""
    # Lower threshold for fair eval; commit subjects are short and BM25 can stay <0.5
    return bm25mem.bm25_rank_decisions(corpus, query, top_k=top_k, min_score=0.01)


def retrieve_ctx_v2_flat(corpus, query, top_k=7):
    """Adapter: apply Porter stemmer + pure BM25 (no recency — corpus has no ordering here)."""
    q = _stem_tokens(query)
    tok = [_stem_tokens(c["text"]) for c in corpus]
    bm25 = BM25Okapi(tok)
    scores = bm25.get_scores(q)
    ranked = sorted(zip(scores, corpus), key=lambda x: -x[0])
    return [c for s, c in ranked if s > 0.01][:top_k]


def score(hits, ground_truth_hash, top_k=7):
    """Recall@k: is the ground-truth commit in the top-k?"""
    for i, h in enumerate(hits[:top_k], 1):
        if h.get("hash") == ground_truth_hash:
            return 1
    return 0


def main():
    qa = json.load(open(ROOT / "benchmarks/results/g1_qa_pairs.json"))
    commits = json.load(open(ROOT / "benchmarks/results/g1_decision_commits.json"))
    corpus = build_corpus(commits)
    print(f"[regression] {len(qa)} queries, {len(corpus)} commits")

    ctx_correct = 0; v2_correct = 0
    per_query = []
    for i, item in enumerate(qa, 1):
        q = item["query"]
        gt = item["ground_truth"]["commit_hash"]
        age = item.get("age_bucket", "")

        hits_ctx = retrieve_ctx_production(corpus, q, top_k=7)
        hits_v2 = retrieve_ctx_v2_flat(corpus, q, top_k=7)
        s_ctx = score(hits_ctx, gt)
        s_v2 = score(hits_v2, gt)
        ctx_correct += s_ctx
        v2_correct += s_v2
        per_query.append({"query": q[:60], "age": age, "ctx": s_ctx, "v2": s_v2})

    N = len(qa)
    print(f"\n== G1 Recall@7 (N={N}) ==")
    print(f"  ctx        : {ctx_correct}/{N} = {ctx_correct/N:.3f}")
    print(f"  ctx_v2     : {v2_correct}/{N} = {v2_correct/N:.3f}")
    print(f"  delta      : {v2_correct - ctx_correct:+d} ({(v2_correct - ctx_correct)/N:+.3f})")

    # Per-age breakdown
    print(f"\n== Per age bucket ==")
    buckets = {}
    for p in per_query:
        b = p["age"] or "unknown"
        buckets.setdefault(b, {"n": 0, "ctx": 0, "v2": 0})
        buckets[b]["n"] += 1
        buckets[b]["ctx"] += p["ctx"]
        buckets[b]["v2"] += p["v2"]
    for b, d in buckets.items():
        n = d["n"]
        print(f"  {b:<10} n={n:<3}  ctx={d['ctx']/n:.3f}  ctx_v2={d['v2']/n:.3f}  delta={(d['v2']-d['ctx'])/n:+.3f}")

    # Net change classification
    ctx_only = sum(1 for p in per_query if p["ctx"] == 1 and p["v2"] == 0)
    v2_only = sum(1 for p in per_query if p["ctx"] == 0 and p["v2"] == 1)
    both = sum(1 for p in per_query if p["ctx"] == 1 and p["v2"] == 1)
    neither = sum(1 for p in per_query if p["ctx"] == 0 and p["v2"] == 0)
    print(f"\n== Per-query overlap ==")
    print(f"  both correct    : {both}")
    print(f"  ctx only        : {ctx_only}  (regression — v2 LOSES these)")
    print(f"  ctx_v2 only     : {v2_only}  (improvement — v2 GAINS these)")
    print(f"  neither correct : {neither}")

    # Verdict
    delta = (v2_correct - ctx_correct) / N
    print(f"\n== Verdict ==")
    if delta >= 0:
        print(f"  PASS — ctx_v2 maintains or improves G1 Recall@7 (delta={delta:+.3f})")
    elif delta >= -0.03:
        print(f"  MARGINAL — minor regression within noise (delta={delta:+.3f}, threshold -0.03)")
    else:
        print(f"  FAIL — ctx_v2 significantly regresses G1 (delta={delta:+.3f})")

    # Save JSON
    out = ROOT / "benchmarks/results/g1_regression_ctx_v2.json"
    out.write_text(json.dumps({
        "n": N,
        "ctx_recall_at_7": ctx_correct/N,
        "ctx_v2_recall_at_7": v2_correct/N,
        "delta_absolute": (v2_correct - ctx_correct)/N,
        "per_age_bucket": {b: {"n": d["n"], "ctx": d["ctx"]/d["n"], "ctx_v2": d["v2"]/d["n"]}
                           for b, d in buckets.items()},
        "overlap": {"both": both, "ctx_only": ctx_only, "ctx_v2_only": v2_only, "neither": neither},
    }, indent=2))
    print(f"\n[wrote] {out}")


if __name__ == "__main__":
    main()
