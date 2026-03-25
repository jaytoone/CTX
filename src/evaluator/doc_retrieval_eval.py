#!/usr/bin/env python3
"""
Document retrieval evaluation for CTX hook.

Measures Recall@3 of the document retrieval component against a
manually curated query set using CTX project's own .md files as corpus.
Compares CTX-doc retrieval vs random baseline.

Usage:
    python src/evaluator/doc_retrieval_eval.py
"""

import importlib.util
import json
import os
import random
import re
import sys
from typing import Dict, List, Tuple

# Add project root to path
HOOK_PATH = os.path.expanduser("~/.claude/hooks/ctx_loader.py")
CTX_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import functions directly from ctx_loader hook file
spec = importlib.util.spec_from_file_location("ctx_loader", HOOK_PATH)
ctx_loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctx_loader)

walk_doc_files = ctx_loader.walk_doc_files
build_doc_index = ctx_loader.build_doc_index
retrieve_doc_semantic = ctx_loader.retrieve_doc_semantic

# ──────────────────────────────────────────────
# Query set — manually curated (query, ground truth relative path)
# ──────────────────────────────────────────────

QUERIES = [
    ("trigger accuracy 실험 결과", "benchmarks/results/trigger_accuracy.md"),
    ("external codebase evaluation Flask FastAPI", "benchmarks/results/external_codebase_eval.md"),
    ("LLM pass@1 openrouter gemini", "benchmarks/results/llm_quality_openrouter.md"),
    ("repobench cross-file retrieval", "benchmarks/results/repobench_eval.md"),
    ("CTX paper arXiv submission", "docs/paper_draft_outline.md"),
    ("hybrid dense retrieval evaluation", "benchmarks/results/hybrid_evaluation.md"),
    ("ablation study variants", "benchmarks/results/ablation_results.md"),
    ("error analysis failure patterns", "benchmarks/results/error_analysis.md"),
    ("claude code hook integration", "docs/claude_code_integration.md"),
    ("differentiation CTX vs Memori", "benchmarks/results/differentiation_analysis.md"),
]


def _path_match(ranked_path: str, ground_truth: str) -> bool:
    """Check if ranked_path matches ground_truth (normalized, suffix-tolerant)."""
    r_norm = ranked_path.replace("\\", "/")
    gt_norm = ground_truth.replace("\\", "/")
    return r_norm == gt_norm or r_norm.endswith(gt_norm) or gt_norm.endswith(r_norm)


def evaluate_ctx_doc_retrieval(
    cwd: str,
    queries: List[Tuple[str, str]],
    k: int = 3,
    random_seed: int = 42,
) -> Tuple[List[Dict], float, float]:
    """
    Run doc retrieval evaluation.

    Returns:
        (per_query_results, recall_at_k, random_baseline)
    """
    doc_files = walk_doc_files(cwd)
    contents_doc, heading_idx = build_doc_index(doc_files, cwd)
    doc_files_rel = list(contents_doc.keys())

    print(f"Indexed {len(doc_files_rel)} doc files from {cwd}")

    results = []
    for query, ground_truth in queries:
        ranked = retrieve_doc_semantic(query, contents_doc, heading_idx, k=k)
        hit = any(_path_match(r, ground_truth) for r in ranked)
        results.append({
            "query": query,
            "ground_truth": ground_truth,
            "ranked": ranked,
            "hit@3": hit,
        })

    recall_at_k = sum(r["hit@3"] for r in results) / len(results)

    # Random baseline: sample k files randomly, check if ground truth in sample
    rng = random.Random(random_seed)
    random_hits = 0
    for _, ground_truth in queries:
        if not doc_files_rel:
            break
        sample = rng.sample(doc_files_rel, min(k, len(doc_files_rel)))
        if any(_path_match(f, ground_truth) for f in sample):
            random_hits += 1
    random_baseline = random_hits / len(queries) if queries else 0.0

    return results, recall_at_k, random_baseline


def format_report(
    results: List[Dict],
    recall_at_k: float,
    random_baseline: float,
    k: int = 3,
    cwd: str = "",
) -> str:
    """Format evaluation results as markdown."""
    lines = [
        "# CTX Document Retrieval Evaluation",
        "",
        f"**Project**: {cwd}",
        f"**Date**: 2026-03-25",
        f"**Metric**: Recall@{k}",
        f"**Queries**: {len(results)}",
        "",
        "## Summary",
        "",
        f"| Method | Recall@{k} |",
        "|--------|-----------|",
        f"| CTX-doc (heading + keyword) | **{recall_at_k:.3f}** |",
        f"| Random baseline | {random_baseline:.3f} |",
        "",
    ]

    if random_baseline > 0:
        lift = (recall_at_k - random_baseline) / random_baseline * 100
        lines.append(f"**Lift over random**: +{lift:.1f}%")
    elif recall_at_k > 0:
        lines.append("**Lift over random**: random baseline = 0 (CTX-doc strictly better)")
    lines.append("")

    lines += [
        "## Per-Query Results",
        "",
        f"| Query | Ground Truth | Hit@{k} | Top-1 Result |",
        "|-------|-------------|---------|-------------|",
    ]
    for r in results:
        hit_mark = "HIT" if r["hit@3"] else "MISS"
        top1 = r["ranked"][0] if r["ranked"] else "(none)"
        query_short = r["query"][:50]
        gt_short = r["ground_truth"].split("/")[-1]
        lines.append(f"| {query_short} | {gt_short} | {hit_mark} | {top1} |")

    lines += ["", "## Analysis", ""]

    hits = [r for r in results if r["hit@3"]]
    misses = [r for r in results if not r["hit@3"]]

    if hits:
        lines.append(
            f"**Hits ({len(hits)})**: "
            + ", ".join(r["ground_truth"].split("/")[-1] for r in hits)
        )
    if misses:
        lines.append("")
        lines.append(f"**Misses ({len(misses)})**:")
        for r in misses:
            lines.append(f"- Query: `{r['query']}`")
            lines.append(f"  Expected: `{r['ground_truth']}`")
            lines.append(f"  Got: {r['ranked'][:3]}")

    lines += [
        "",
        "## Method Description",
        "",
        "CTX-doc uses a two-stage retrieval:",
        "1. **Heading match**: Exact/partial match against document headings"
        " (Markdown `##`, YAML keys, TOML sections)",
        "2. **Keyword fallback**: ASCII keyword frequency scoring across document content",
        "",
        f"Random baseline: uniformly sample {k} files from the {len(results)}-query corpus.",
    ]

    return "\n".join(lines)


def main() -> None:
    cwd = CTX_ROOT
    print(f"Running doc retrieval eval on: {cwd}")

    results, recall_at_3, random_baseline = evaluate_ctx_doc_retrieval(cwd, QUERIES, k=3)

    print(f"\nRecall@3:        {recall_at_3:.3f}")
    print(f"Random baseline: {random_baseline:.3f}")
    print("\nPer-query results:")
    for r in results:
        mark = "HIT " if r["hit@3"] else "MISS"
        print(f"  [{mark}] {r['query'][:50]}")
        print(f"         Expected: {r['ground_truth']}")
        print(f"         Got:      {r['ranked'][:3]}")

    report = format_report(results, recall_at_3, random_baseline, k=3, cwd=cwd)

    out_path = os.path.join(cwd, "benchmarks", "results", "doc_retrieval_eval.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
