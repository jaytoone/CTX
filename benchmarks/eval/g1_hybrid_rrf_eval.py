#!/usr/bin/env python3
"""
g1_hybrid_rrf_eval.py — A/B/C comparison on G1 (git decision) retrieval:
  A: BM25-only (baseline, no rerank, no dense)
  B: BM25 + semantic rerank (current production)
  C: BM25 + dense-RRF + semantic rerank (new hybrid)

Goal: Determine if hybrid BM25+dense RRF improves Recall@7 on CTX's own G1 corpus
vs. the public benchmark SOTA finding (MAB/LongMemEval: hybrid > BM25-only).

Also outputs a per-query human-loop evaluation table showing:
  - Which nodes each method found
  - Whether the gold node was retrieved (and at which rank)
  - Retrieval method comparison for manual relevance inspection

Usage:
  python3 benchmarks/eval/g1_hybrid_rrf_eval.py [--human-loop] [--quiet]

Output:
  benchmarks/results/g1_hybrid_rrf_eval.json
  benchmarks/results/g1_hybrid_rrf_eval.md   (human-loop report)
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
QA_PATH = REPO / "benchmarks" / "results" / "g1_qa_pairs.json"
OUT_JSON = REPO / "benchmarks" / "results" / "g1_hybrid_rrf_eval.json"
OUT_MD = REPO / "benchmarks" / "results" / "g1_hybrid_rrf_eval.md"
HOOK_PATH = Path.home() / ".claude" / "hooks" / "bm25-memory.py"
PROJECT_DIR = str(REPO)

HUMAN_LOOP = "--human-loop" in sys.argv
QUIET = "--quiet" in sys.argv


def load_hook():
    spec = importlib.util.spec_from_file_location("bm25_memory", HOOK_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def recall_at_k(retrieved_hashes, gold_hash, k=7):
    return int(gold_hash in retrieved_hashes[:k])


def gold_rank(retrieved_hashes, gold_hash):
    if gold_hash in retrieved_hashes:
        return retrieved_hashes.index(gold_hash) + 1
    return None


# ── Condition runners ─────────────────────────────────────────────

def run_bm25_only(hook, corpus, qa_pairs, top_k=7):
    """Condition A: pure BM25, no rerank, no dense."""
    results = []
    for item in qa_pairs:
        q = item["query"]
        gh = item["ground_truth"]["commit_hash"]
        # Monkey-patch both rerankers to no-ops for this condition
        orig_sr = hook.semantic_rerank_filter
        orig_dense = hook.dense_rank_decisions
        hook.semantic_rerank_filter = lambda cands, q, top_k, **kw: cands[:top_k]
        hook.dense_rank_decisions = lambda corpus, q, top_k=20: []
        retrieved = hook.bm25_rank_decisions(corpus, q, top_k=top_k, skip_rerank=True)
        hook.semantic_rerank_filter = orig_sr
        hook.dense_rank_decisions = orig_dense
        hashes = [c.get("hash", "") for c in retrieved]
        results.append({
            "query": q, "query_type": item.get("query_type", ""),
            "age_bucket": item.get("age_bucket", ""),
            "gold_hash": gh[:7], "gold_hash_full": gh,
            "hit": recall_at_k(hashes, gh, k=top_k),
            "gold_rank": gold_rank(hashes, gh),
            "top3_hashes": [h[:7] for h in hashes[:3]],
            "top3_subjects": [c.get("subject", "")[:60] for c in retrieved[:3]],
        })
    return results


def run_bm25_rerank(hook, corpus, qa_pairs, top_k=7):
    """Condition B: BM25 + semantic rerank (current production)."""
    results = []
    for item in qa_pairs:
        q = item["query"]
        gh = item["ground_truth"]["commit_hash"]
        retrieved = hook.bm25_rank_decisions(corpus, q, top_k=top_k)
        hashes = [c.get("hash", "") for c in retrieved]
        results.append({
            "query": q, "query_type": item.get("query_type", ""),
            "age_bucket": item.get("age_bucket", ""),
            "gold_hash": gh[:7], "gold_hash_full": gh,
            "hit": recall_at_k(hashes, gh, k=top_k),
            "gold_rank": gold_rank(hashes, gh),
            "top3_hashes": [h[:7] for h in hashes[:3]],
            "top3_subjects": [c.get("subject", "")[:60] for c in retrieved[:3]],
        })
    return results


def run_hybrid_rrf(hook, corpus, qa_pairs, top_k=7):
    """Condition C: BM25+dense RRF + semantic rerank (new hybrid)."""
    results = []
    for item in qa_pairs:
        q = item["query"]
        gh = item["ground_truth"]["commit_hash"]
        retrieved = hook.hybrid_rank_decisions(corpus, q, top_k=top_k)
        hashes = [c.get("hash", "") for c in retrieved]
        results.append({
            "query": q, "query_type": item.get("query_type", ""),
            "age_bucket": item.get("age_bucket", ""),
            "gold_hash": gh[:7], "gold_hash_full": gh,
            "hit": recall_at_k(hashes, gh, k=top_k),
            "gold_rank": gold_rank(hashes, gh),
            "top3_hashes": [h[:7] for h in hashes[:3]],
            "top3_subjects": [c.get("subject", "")[:60] for c in retrieved[:3]],
        })
    return results


# ── Summarize ─────────────────────────────────────────────────────

def summarize(results, label):
    n = len(results)
    hits = sum(r["hit"] for r in results)
    recall = hits / n if n else 0.0
    by_type = {}
    for r in results:
        t = r["query_type"]
        by_type.setdefault(t, []).append(r["hit"])
    by_age = {}
    for r in results:
        a = r["age_bucket"]
        by_age.setdefault(a, []).append(r["hit"])

    if not QUIET:
        print(f"\n{'='*55}")
        print(f"  {label}")
        print(f"{'='*55}")
        print(f"  Recall@7: {hits}/{n} = {recall:.3f}")
        for t, vals in sorted(by_type.items()):
            print(f"    [{t}]  {sum(vals)}/{len(vals)} = {sum(vals)/len(vals):.3f}")
        for a, vals in sorted(by_age.items()):
            print(f"    [{a}]  {sum(vals)}/{len(vals)} = {sum(vals)/len(vals):.3f}")

    return {
        "label": label,
        "recall7": round(recall, 4),
        "hits": hits,
        "n": n,
        "by_type": {t: round(sum(v)/len(v), 4) for t, v in by_type.items()},
        "by_age":  {a: round(sum(v)/len(v), 4) for a, v in by_age.items()},
    }


# ── Delta table: per-query diffs ──────────────────────────────────

def print_delta_table(results_a, results_b, results_c, label_a, label_b, label_c):
    """Show queries where ANY two conditions differ."""
    changed = []
    for a, b, c in zip(results_a, results_b, results_c):
        if a["hit"] != b["hit"] or a["hit"] != c["hit"] or b["hit"] != c["hit"]:
            changed.append({
                "query": a["query"][:55],
                "A": a["hit"], "B": b["hit"], "C": c["hit"],
                "A_rank": a["gold_rank"], "B_rank": b["gold_rank"], "C_rank": c["gold_rank"],
                "age": a["age_bucket"],
            })

    if not changed:
        print("\n  No per-query differences between any condition.")
        return

    print(f"\n  Per-query deltas ({len(changed)} queries differ across conditions):")
    hdr = f"  {'Query':<55} {label_a[:4]:>5} {label_b[:4]:>5} {label_c[:4]:>5} {'A_rnk':>7} {'B_rnk':>7} {'C_rnk':>7} {'age':>5}"
    print(hdr)
    for c in changed:
        print(f"  {c['query']:<55} {c['A']:>5} {c['B']:>5} {c['C']:>5} "
              f"{str(c['A_rank']):>7} {str(c['B_rank']):>7} {str(c['C_rank']):>7} {c['age']:>5}")


# ── Human-loop relevance report ───────────────────────────────────

def build_human_loop_report(qa, results_a, results_b, results_c, corpus):
    """Build a Markdown report for manual relevance inspection.

    Shows each query, gold answer, and top-3 retrieved nodes from each condition.
    Human reviewer can check: are the retrieved nodes actually relevant?

    This implements step 3 of the user's plan: human loop eval of retrieved nodes.
    """
    hash_to_item = {item.get("hash", ""): item for item in corpus}

    lines = ["# G1 Hybrid RRF — Human Loop Relevance Report\n",
             "**Purpose**: Manual verification that retrieved nodes are actually relevant.\n",
             "For each query, compare what each retrieval method found vs the gold commit.\n",
             "Mark each retrieved node: ✅ relevant | ❌ not relevant | ❓ partial\n",
             "---\n"]

    diff_count = 0
    for i, (a, b, c) in enumerate(zip(results_a, results_b, results_c)):
        # Only show queries where conditions differ (most interesting for human loop)
        if not HUMAN_LOOP and a["hit"] == b["hit"] == c["hit"]:
            continue
        diff_count += 1

        q = a["query"]
        gh = a["gold_hash_full"]
        gold_item = hash_to_item.get(gh, {})
        gold_subj = gold_item.get("subject", "(not in corpus)")
        gold_body = (gold_item.get("body", "") or "")[:200]

        lines.append(f"## Query {i+1}: `{q}`")
        lines.append(f"- **Type**: {a['query_type']} | **Age**: {a['age_bucket']}")
        lines.append(f"- **Gold commit**: `{gh[:7]}` — {gold_subj}")
        if gold_body:
            lines.append(f"  ```\n  {gold_body}\n  ```")
        lines.append("")

        for label, res in [(("A: BM25-only", a)), ("B: BM25+rerank", b), ("C: Hybrid-RRF", c)]:
            if isinstance(label, tuple):
                label, res = label
            status = "✅ HIT" if res["hit"] else "❌ MISS"
            rank_str = f"rank {res['gold_rank']}" if res["gold_rank"] else "not retrieved"
            lines.append(f"### {label} — {status} ({rank_str})")
            lines.append("| # | Hash | Subject | Your rating |")
            lines.append("|---|------|---------|-------------|")
            for j, subj in enumerate(res["top3_subjects"], 1):
                h = res["top3_hashes"][j-1] if j <= len(res["top3_hashes"]) else "?"
                marker = " ⭐" if h == gh[:7] else ""
                lines.append(f"| {j} | `{h}` | {subj}{marker} | [ ] |")
            lines.append("")

        lines.append("---\n")

    if diff_count == 0:
        lines.append("*All queries returned identical results across all 3 conditions.*\n")
        lines.append("*No differences to manually inspect — methods are equivalent on this corpus.*\n")

    lines.append(f"\n## Summary\n")
    lines.append(f"Queries with differences: {diff_count} / {len(results_a)}\n")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────

def main():
    if not QUIET:
        print("[G1 Hybrid RRF Eval] A=BM25-only / B=BM25+rerank / C=BM25+dense-RRF+rerank")
        print(f"  Hook: {HOOK_PATH}")
        print(f"  QA pairs: {QA_PATH}")

    if not HOOK_PATH.exists():
        print("[ERROR] bm25-memory.py not found"); sys.exit(1)
    if not QA_PATH.exists():
        print("[ERROR] g1_qa_pairs.json not found"); sys.exit(1)

    hook = load_hook()
    qa = json.loads(QA_PATH.read_text())
    if not QUIET:
        print(f"  Loaded {len(qa)} QA pairs")

    # Check if hybrid_rank_decisions is available
    if not hasattr(hook, "hybrid_rank_decisions"):
        print("[ERROR] hybrid_rank_decisions() not found in bm25-memory.py")
        print("  → Run this after the 2026-04-26 dense retrieval update")
        sys.exit(1)

    if not QUIET:
        print("\n[1] Building decision corpus (with embedding pre-computation)...")
    t0 = time.time()
    corpus = hook.get_decision_corpus(PROJECT_DIR)
    t_corpus = time.time() - t0
    if not QUIET:
        print(f"  Corpus size: {len(corpus)} commits ({t_corpus:.1f}s)")

    # Check coverage
    gt_hashes = {q["ground_truth"]["commit_hash"] for q in qa}
    corpus_hashes = {c.get("hash", "") for c in corpus}
    found = gt_hashes & corpus_hashes
    if not QUIET:
        print(f"  GT coverage: {len(found)}/{len(gt_hashes)} (missing: {len(gt_hashes)-len(found)})")

    # Check embedding coverage
    emb_count = sum(1 for c in corpus if c.get("emb"))
    if not QUIET:
        print(f"  Embeddings: {emb_count}/{len(corpus)} items embedded (dense retrieval {'ENABLED' if emb_count > 0 else 'DISABLED — vec-daemon down'})")

    if not QUIET:
        print("\n[2] Running A: BM25-only (no rerank, no dense)...")
    t0 = time.time()
    results_a = run_bm25_only(hook, corpus, qa)
    t_a = time.time() - t0
    sum_a = summarize(results_a, "A: BM25-only (baseline)")

    if not QUIET:
        print(f"\n[3] Running B: BM25 + semantic rerank (production)...")
    t0 = time.time()
    results_b = run_bm25_rerank(hook, corpus, qa)
    t_b = time.time() - t0
    sum_b = summarize(results_b, "B: BM25 + rerank (production)")

    if not QUIET:
        print(f"\n[4] Running C: Hybrid BM25+dense RRF + rerank (new)...")
    t0 = time.time()
    results_c = run_hybrid_rrf(hook, corpus, qa)
    t_c = time.time() - t0
    sum_c = summarize(results_c, "C: BM25+dense-RRF+rerank (hybrid)")

    # Summary table
    if not QUIET:
        print(f"\n{'='*55}")
        print(f"  RESULTS SUMMARY")
        print(f"{'='*55}")
        print(f"  {'Method':<32} {'Recall@7':>9} {'Delta vs A':>12}")
        for s, ref in [(sum_a, sum_a), (sum_b, sum_a), (sum_c, sum_a)]:
            delta = s["recall7"] - ref["recall7"]
            delta_str = f"{delta:+.4f}" if s is not ref else "  baseline"
            verdict = " ✅" if delta > 0 else (" ⚠" if delta < -0.001 else " =")
            print(f"  {s['label']:<32} {s['recall7']:>9.3f} {delta_str:>12}{verdict}")

        print(f"\n  Latency: A={t_a:.1f}s  B={t_b:.1f}s  C={t_c:.1f}s")
        print(f"  Corpus embeddings: {emb_count}/{len(corpus)}")

    print_delta_table(results_a, results_b, results_c, "A", "B", "C")

    # Human-loop report
    if HUMAN_LOOP:
        md_content = build_human_loop_report(qa, results_a, results_b, results_c, corpus)
        OUT_MD.write_text(md_content)
        print(f"\n[wrote human-loop report] {OUT_MD}")

    # JSON output
    output = {
        "n_queries": len(qa),
        "corpus_size": len(corpus),
        "emb_coverage": f"{emb_count}/{len(corpus)}",
        "bm25_only": sum_a,
        "bm25_rerank": sum_b,
        "hybrid_rrf": sum_c,
        "delta_hybrid_vs_bm25": round(sum_c["recall7"] - sum_a["recall7"], 4),
        "delta_rerank_vs_bm25": round(sum_b["recall7"] - sum_a["recall7"], 4),
        "latency_seconds": {"bm25_only": round(t_a, 2), "bm25_rerank": round(t_b, 2), "hybrid_rrf": round(t_c, 2)},
    }
    OUT_JSON.write_text(json.dumps(output, indent=2))
    if not QUIET:
        print(f"\n[wrote] {OUT_JSON}")


if __name__ == "__main__":
    main()
