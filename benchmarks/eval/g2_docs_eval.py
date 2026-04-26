"""
G2-DOCS Hybrid Retrieval Eval — BM25 vs Hybrid BM25+Dense RRF

Evaluates bm25_search_docs() vs hybrid_search_docs() on the 15-query
g2_docs_goldset.json corpus. Reports Hit@3, Hit@5, MRR per query type.

Usage:
    python3 benchmarks/eval/g2_docs_eval.py [--project-dir .] [--top-k 5]

Requirements:
    - vec-daemon running (for hybrid; BM25-only degrades gracefully)
    - ~/.claude/hooks/bm25-memory.py importable via sys.path injection
"""

import argparse
import json
import sys
from pathlib import Path


HOOK_PATH = Path.home() / ".claude" / "hooks" / "bm25-memory.py"


def _load_hook():
    """Import bm25_search_docs and hybrid_search_docs from bm25-memory.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("bm25_memory", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bm25_memory"] = mod
    spec.loader.exec_module(mod)
    return mod


def hit_at_k(results, gold_set, k):
    """1 if any gold doc filename appears in top-k results."""
    filenames = [r.split("\n", 1)[0] for r in results[:k]]
    return 1 if any(g in filenames for g in gold_set) else 0


def reciprocal_rank(results, gold_set):
    """1/rank of first gold doc; 0 if not found."""
    for i, r in enumerate(results, start=1):
        filename = r.split("\n", 1)[0]
        if filename in gold_set:
            return 1.0 / i
    return 0.0


def avg(values):
    return sum(values) / len(values) if values else 0.0


def run_eval(project_dir=".", top_k=5, goldset_path=None):
    if goldset_path is None:
        goldset_path = Path(__file__).parent / "g2_docs_goldset.json"

    with open(goldset_path, encoding="utf-8") as f:
        goldset = json.load(f)

    print(f"Loading bm25-memory hook from {HOOK_PATH}...")
    mod = _load_hook()
    bm25_fn = mod.bm25_search_docs
    hybrid_fn = mod.hybrid_search_docs

    queries = goldset["queries"]
    print(f"Evaluating {len(queries)} queries | top_k={top_k} | project={project_dir!r}")
    print()

    rows = []
    for q in queries:
        qid = q["id"]
        qtype = q["type"]
        query = q["query"]
        gold = set(q["gold"])

        bm25_results = bm25_fn(project_dir, query, top_k=top_k)
        hybrid_results = hybrid_fn(project_dir, query, top_k=top_k)

        rows.append({
            "id": qid, "type": qtype, "query": query[:50],
            "bm25_h3": hit_at_k(bm25_results, gold, 3),
            "bm25_h5": hit_at_k(bm25_results, gold, top_k),
            "bm25_mrr": reciprocal_rank(bm25_results, gold),
            "hyb_h3": hit_at_k(hybrid_results, gold, 3),
            "hyb_h5": hit_at_k(hybrid_results, gold, top_k),
            "hyb_mrr": reciprocal_rank(hybrid_results, gold),
            "bm25_top1": (bm25_results[0].split("\n", 1)[0] if bm25_results else "—"),
            "hyb_top1": (hybrid_results[0].split("\n", 1)[0] if hybrid_results else "—"),
            "gold": next(iter(gold)),
        })

    # Per-query table
    print(f"{'ID':<8} {'Type':<18} {'Query':<50}  BM25(H3/H5/MRR)  Hybrid(H3/H5/MRR)")
    print("-" * 112)
    for r in rows:
        b = f"{r['bm25_h3']}/{r['bm25_h5']}/{r['bm25_mrr']:.2f}"
        h = f"{r['hyb_h3']}/{r['hyb_h5']}/{r['hyb_mrr']:.2f}"
        print(f"{r['id']:<8} {r['type']:<18} {r['query']:<50}  {b:<17} {h}")

    print()
    print("TOP-1 comparison (gold → BM25 / Hybrid):")
    for r in rows:
        sb = "OK" if r["bm25_top1"] == r["gold"] else "MISS"
        sh = "OK" if r["hyb_top1"] == r["gold"] else "MISS"
        print(f"  {r['id']:<8} gold={r['gold'][:55]}")
        print(f"           BM25 [{sb}] {r['bm25_top1'][:60]}")
        print(f"           Hybrid [{sh}] {r['hyb_top1'][:60]}")

    # Aggregate by type + ALL
    print()
    header = (f"{'Type':<20} {'N':>3}  {'BM25 H@3':>8} {'BM25 H@5':>8} {'BM25 MRR':>9}  "
              f"{'Hyb H@3':>8} {'Hyb H@5':>8} {'Hyb MRR':>9}  {'DH@3':>6} {'DH@5':>6} {'DMRR':>6}")
    print(header)
    print("-" * 110)

    types = sorted(set(r["type"] for r in rows))
    for t in types + ["ALL"]:
        group = [r for r in rows if r["type"] == t] if t != "ALL" else rows
        n = len(group)
        bm3 = avg([r["bm25_h3"] for r in group])
        bm5 = avg([r["bm25_h5"] for r in group])
        bmr = avg([r["bm25_mrr"] for r in group])
        hy3 = avg([r["hyb_h3"] for r in group])
        hy5 = avg([r["hyb_h5"] for r in group])
        hyr = avg([r["hyb_mrr"] for r in group])
        print(f"{t:<20} {n:>3}  {bm3:>8.3f} {bm5:>8.3f} {bmr:>9.3f}  "
              f"{hy3:>8.3f} {hy5:>8.3f} {hyr:>9.3f}  "
              f"{hy3-bm3:>+6.3f} {hy5-bm5:>+6.3f} {hyr-bmr:>+6.3f}")

    n = len(rows)
    bm3_all = avg([r["bm25_h3"] for r in rows])
    hy3_all = avg([r["hyb_h3"] for r in rows])
    bm5_all = avg([r["bm25_h5"] for r in rows])
    hy5_all = avg([r["hyb_h5"] for r in rows])
    bmr_all = avg([r["bm25_mrr"] for r in rows])
    hyr_all = avg([r["hyb_mrr"] for r in rows])
    dh3 = hy3_all - bm3_all
    dh5 = hy5_all - bm5_all
    dmrr = hyr_all - bmr_all

    print()
    print("INTERPRETATION:")
    if dh3 > 0.10:
        print(f"  Hybrid BETTER (DH@3={dh3:+.3f}, DMRR={dmrr:+.3f})")
        print("  Dense first-stage retrieval contributes meaningfully to G2-DOCS.")
    elif dh3 > 0:
        print(f"  Hybrid MARGINAL (DH@3={dh3:+.3f}, DMRR={dmrr:+.3f})")
        print("  BM25 already strong; hybrid adds minor improvement.")
    elif dh3 < -0.05:
        print(f"  Hybrid WORSE (DH@3={dh3:+.3f}, DMRR={dmrr:+.3f})")
        print("  Dense embedding introducing noise; consider BM25-only for this corpus.")
    else:
        print(f"  Hybrid EQUIVALENT (DH@3={dh3:+.3f}, DMRR={dmrr:+.3f})")

    result = {
        "goldset": str(goldset_path),
        "project_dir": project_dir,
        "top_k": top_k,
        "n_queries": n,
        "bm25": {"hit_at_3": bm3_all, "hit_at_5": bm5_all, "mrr": bmr_all},
        "hybrid": {"hit_at_3": hy3_all, "hit_at_5": hy5_all, "mrr": hyr_all},
        "delta": {"hit_at_3": dh3, "hit_at_5": dh5, "mrr": dmrr},
        "per_query": rows,
    }
    out_path = Path(__file__).parent.parent / "results" / "g2_docs_eval.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved -> {out_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="G2-DOCS Hybrid vs BM25 Evaluation")
    parser.add_argument("--project-dir", default=".", help="CTX project root")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--goldset", default=None, help="Path to goldset JSON")
    args = parser.parse_args()

    run_eval(
        project_dir=args.project_dir,
        top_k=args.top_k,
        goldset_path=args.goldset,
    )
