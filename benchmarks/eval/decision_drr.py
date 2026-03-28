"""
Decision Recall Rate (DRR) measurement.

Tests whether TEMPORAL_HISTORY trigger + unified AdaptiveTriggerRetriever
can surface relevant decision documents (docs/decisions/*.md) when given
natural language queries about past technical choices.

Ground truth: 5 known decisions from this session.
Metric: DRR@k = fraction of decisions correctly retrieved at rank <= k.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever


KNOWN_DECISIONS = [
    {
        "id": "D1",
        "file": "docs/decisions/20260326-import-bfs-over-ast.md",
        "queries": [
            "why did we choose import BFS over AST parsing",
            "previously decided to use regex import instead of AST graph",
            "IMPLICIT_CONTEXT traversal strategy decision",
            "what modules are imported using BFS traversal",
        ],
    },
    {
        "id": "D2",
        "file": "docs/decisions/20260326-non-symbols-frozenset.md",
        "queries": [
            "why we added NON_SYMBOLS frozenset",
            "previously filter action verbs from trigger classifier",
            "how we fixed Find being classified as a symbol",
            "SEMANTIC_CONCEPT false positive fix frozenset",
        ],
    },
    {
        "id": "D3",
        "file": "docs/decisions/20260326-path-derived-module-to-file.md",
        "queries": [
            "why we derive module names from file paths",
            "module_to_file was empty in real codebases",
            "path derived module mapping decision",
            "how we fixed 5x performance collapse",
        ],
    },
    {
        "id": "D4",
        "file": "docs/decisions/20260326-unified-doc-code-indexing.md",
        "queries": [
            "why we added markdown file indexing",
            "decision to index .md files alongside Python",
            "unified document and code retrieval decision",
            "previously decided to extend retriever to include docs",
        ],
    },
    {
        "id": "D5",
        "file": "docs/decisions/20260326-concept-extraction-sema-conc.md",
        "queries": [
            "why we extract concept from related to X pattern",
            "how we fixed semantic concept value extraction",
            "SEMANTIC_CONCEPT query parsing fix",
            "previously decided to parse actual concept from query",
        ],
    },
]


def hit_at_k(retrieved: list, target: str, k: int) -> bool:
    target_base = os.path.basename(target)
    for r in retrieved[:k]:
        r_norm = r.replace("\\", "/")
        target_norm = target.replace("\\", "/")
        if (target_norm in r_norm or r_norm in target_norm or
                target_base in r_norm or os.path.basename(r_norm) in target_norm):
            return True
    return False


def run_drr(codebase_dir: str = ".") -> dict:
    print(f"Indexing: {codebase_dir}")
    retriever = AdaptiveTriggerRetriever(codebase_dir)

    py_n = sum(1 for f in retriever.file_paths if f.endswith('.py'))
    md_n = sum(1 for f in retriever.file_paths if f.endswith('.md'))
    print(f"Index: {py_n} .py  +  {md_n} .md  =  {py_n + md_n} total")

    decision_files = [f for f in retriever.file_paths if 'decisions' in f.replace("\\", "/")]
    print(f"Decision files indexed: {len(decision_files)}")
    for f in decision_files:
        print(f"  ✓ {f}")

    if not decision_files:
        print("ERROR: No decision files in index. Check docs/decisions/ path.")
        return {}

    k_values = [1, 3, 5]
    results = []

    for dec in KNOWN_DECISIONS:
        target = dec["file"]
        # For each query, check hit at each k
        query_hits = {k: [] for k in k_values}
        best_query = {}

        for q in dec["queries"]:
            res = retriever.retrieve(f"drr_{dec['id']}", q, k=5)
            for k in k_values:
                h = hit_at_k(res.retrieved_files, target, k)
                query_hits[k].append(h)
                if h and k == 3:
                    best_query[q] = True

        # Decision is "recalled" if ANY query hits at rank <= k
        per_dec = {k: 1.0 if any(query_hits[k]) else 0.0 for k in k_values}
        results.append({
            "id": dec["id"],
            "file": target,
            "n_queries": len(dec["queries"]),
            **{f"hit@{k}": per_dec[k] for k in k_values},
            "best_query": next(iter(best_query), None),
        })

    drr = {
        f"DRR@{k}": sum(r[f"hit@{k}"] for r in results) / len(results)
        for k in k_values
    }

    return {"decisions": results, "drr": drr, "n": len(results)}


def main():
    result = run_drr(_ROOT)
    if not result:
        return

    drr = result["drr"]
    print("\n=== Decision Recall Rate ===")
    for k in [1, 3, 5]:
        val = drr.get(f"DRR@{k}", 0.0)
        thr = {1: None, 3: 0.7, 5: 0.8}[k]
        status = "" if thr is None else ("✅ PASS" if val >= thr else "❌ FAIL")
        print(f"  DRR@{k}: {val:.3f}  {status}")

    print("\n=== Per-Decision ===")
    for r in result["decisions"]:
        h = lambda v: "HIT " if v else "MISS"
        print(f"  {r['id']}: @1={h(r['hit@1'])}  @3={h(r['hit@3'])}  @5={h(r['hit@5'])}  {r['file'].split('/')[-1]}")
        if r.get("best_query"):
            print(f"       best: \"{r['best_query']}\"")

    # Write report
    out = os.path.join(_ROOT, "benchmarks/results/decision_recall_eval.md")
    lines = [
        "# Decision Recall Rate (DRR) Measurement",
        "",
        "**Date**: 2026-03-26",
        f"**Decisions tested**: {result['n']} (from docs/decisions/)",
        "**Queries per decision**: 4 natural language queries",
        "**Hit criterion**: any of 4 queries retrieves target file within top-k",
        "",
        "## Results",
        "",
        "| Metric | Score | Threshold | Status |",
        "|--------|-------|-----------|--------|",
    ]
    for k, thr in [(1, None), (3, 0.7), (5, 0.8)]:
        val = drr.get(f"DRR@{k}", 0.0)
        thr_str = "—" if thr is None else f"≥ {thr}"
        status = "—" if thr is None else ("✅ PASS" if val >= thr else "❌ FAIL")
        lines.append(f"| DRR@{k} | {val:.3f} | {thr_str} | {status} |")

    lines += ["", "## Per-Decision", "",
              "| ID | File | Hit@1 | Hit@3 | Hit@5 | Best Query |",
              "|----|------|-------|-------|-------|------------|"]
    for r in result["decisions"]:
        h = lambda v: "✅" if v else "❌"
        bq = r.get("best_query") or "—"
        if len(bq) > 40:
            bq = bq[:40] + "..."
        lines.append(
            f"| {r['id']} | `{r['file'].split('/')[-1]}` "
            f"| {h(r['hit@1'])} | {h(r['hit@3'])} | {h(r['hit@5'])} | {bq} |"
        )

    lines += [
        "", "## Interpretation",
        "",
        "DRR measures the **결정 기억 복원** capability of the unified AdaptiveTriggerRetriever.",
        "A decision is 'recalled' if at least one of 4 natural language queries about it",
        "surfaces the corresponding `docs/decisions/*.md` file within top-k results.",
    ]

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()
