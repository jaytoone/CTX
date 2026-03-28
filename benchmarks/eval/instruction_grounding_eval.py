"""
instruction_grounding_eval.py — Instruction-to-File Grounding Evaluation

Measures Goal 2: Does CTX find relevant files when user gives natural language instructions?

Unlike Recall@K on symbol queries, this tests instruction-driven queries:
  "fix the authentication flow" → should retrieve auth files
  "implement database migration" → should retrieve database files
  "add caching to the API" → should retrieve api + cache files

Uses the dataset's concept/tier metadata to generate instruction queries and ground truth.

Usage:
  python3 benchmarks/eval/instruction_grounding_eval.py [--dataset small] [--k 5]
"""

import argparse
import json
import numpy as np
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

DATASET_DIR = ROOT / "benchmarks" / "datasets"

# Instruction templates mapped to concept keywords
# Format: (instruction_template, concept_keywords_to_match)
INSTRUCTION_TEMPLATES: List[Tuple[str, List[str]]] = [
    ("fix the authentication flow", ["auth", "session", "jwt", "login", "password"]),
    ("implement database connection pooling", ["database", "db", "connection", "transaction", "migration"]),
    ("add caching layer to reduce latency", ["cache", "caching", "redis", "memory", "ttl"]),
    ("improve API rate limiting", ["api", "rate", "limit", "endpoint", "request"]),
    ("debug the logging pipeline", ["logging", "log", "event", "audit", "trace"]),
    ("refactor the scheduling module", ["schedule", "scheduler", "cron", "job", "task"]),
    ("update the security middleware", ["security", "middleware", "auth", "permission", "token"]),
    ("optimize the search functionality", ["search", "index", "query", "filter", "ranking"]),
    ("implement email notification system", ["email", "notification", "message", "alert", "smtp"]),
    ("add user analytics tracking", ["analytics", "metrics", "tracking", "event", "user"]),
]


def build_instruction_ground_truth(
    files_meta: List[dict],
    concept_keywords: List[str],
) -> List[str]:
    """Find ground truth files for an instruction based on concept keyword overlap."""
    gt = []
    for fm in files_meta:
        file_concepts = [c.lower() for c in fm.get("concepts", [])]
        module_name = fm.get("module_name", "").lower()
        file_path = fm.get("path", "").lower()

        # Match if any concept keyword appears in file's concepts, name, or path
        for kw in concept_keywords:
            if (kw in file_concepts or
                    kw in module_name or
                    kw in file_path):
                gt.append(fm["path"])
                break

    return gt


def recall_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
    if not ground_truth:
        return 1.0  # No ground truth = trivially satisfied (skip)
    hits = sum(1 for f in retrieved[:k] if f in ground_truth)
    return hits / len(ground_truth)


def ndcg_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
    """Compute NDCG@K (standard IR metric for top-tier papers).

    Ideal DCG: relevance=1 for all ground truth items
    NDCG = DCG / IDCG
    """
    if not ground_truth:
        return 1.0

    dcg = 0.0
    for i, f in enumerate(retrieved[:k], 1):
        if f in ground_truth:
            dcg += 1.0 / np.log2(i + 1)  # Standard DCG discount

    # Ideal DCG: all ground truth items at top positions
    idcg = sum(1.0 / np.log2(i + 1) for i in range(1, min(len(ground_truth), k) + 1))

    if idcg == 0:
        return 0.0

    return dcg / idcg


def precision_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
    if not retrieved or k == 0:
        return 0.0
    hits = sum(1 for f in retrieved[:k] if f in ground_truth)
    return hits / min(k, len(retrieved))


def run_evaluation(dataset_name: str, k: int = 5) -> dict:
    metadata_path = DATASET_DIR / dataset_name / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Dataset not found: {metadata_path}")

    with open(metadata_path) as f:
        metadata = json.load(f)

    files_meta = metadata["files"]
    codebase_dir = str(DATASET_DIR / dataset_name / "codebase")

    # Import retriever here (requires codebase to exist)
    try:
        from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever
        from src.retrieval.full_context import FullContextRetriever
        retriever = AdaptiveTriggerRetriever(codebase_dir)
        full_ctx = FullContextRetriever(codebase_dir)
        has_retriever = True
    except Exception as e:
        print(f"[WARN] Could not load retriever: {e}")
        print("[WARN] Running ground-truth-only mode (no retrieval comparison)")
        retriever = None
        full_ctx = None
        has_retriever = False

    results = []
    skipped = 0

    for instruction, concept_keywords in INSTRUCTION_TEMPLATES:
        gt_files = build_instruction_ground_truth(files_meta, concept_keywords)

        if len(gt_files) == 0:
            skipped += 1
            continue

        gt_set = set(gt_files)

        if has_retriever:
            result = retriever.retrieve(
                query_id=instruction[:20],
                query_text=instruction,
                k=k,
            )
            retrieved = result.retrieved_files
            trigger_type = retriever.classifier.classify_primary(instruction).value
        else:
            retrieved = []
            trigger_type = "N/A"

        r_at_k = recall_at_k(retrieved, gt_set, k)
        p_at_k = precision_at_k(retrieved, gt_set, k)
        ndcg = ndcg_at_k(retrieved, gt_set, k)

        results.append({
            "instruction": instruction,
            "concept_keywords": concept_keywords,
            "ndcg_at_k": round(ndcg, 3),
            "ground_truth_size": len(gt_files),
            "trigger_type_detected": trigger_type,
            "retrieved_count": len(retrieved),
            f"recall_at_{k}": round(r_at_k, 3),
            f"precision_at_{k}": round(p_at_k, 3),
        })

    avg_recall = (
        sum(r[f"recall_at_{k}"] for r in results) / len(results)
        if results else 0.0
    )
    avg_precision = (
        sum(r[f"precision_at_{k}"] for r in results) / len(results)
        if results else 0.0
    )
    avg_ndcg = (
        sum(r["ndcg_at_k"] for r in results) / len(results)
        if results else 0.0
    )

    # Trigger type distribution
    trigger_dist: Dict[str, int] = {}
    for r in results:
        t = r["trigger_type_detected"]
        trigger_dist[t] = trigger_dist.get(t, 0) + 1

    return {
        "dataset": dataset_name,
        "k": k,
        "total_queries": len(results),
        "skipped_no_gt": skipped,
        "avg_recall_at_k": round(avg_recall, 3),
        "avg_precision_at_k": round(avg_precision, 3),
        "avg_ndcg_at_k": round(avg_ndcg, 3),
        "trigger_type_distribution": trigger_dist,
        "per_query": results,
        "goal": "instruction-to-file grounding (Goal 2: find relevant files from user instructions)",
        "note": (
            "Ground truth = files whose concepts/module-name match instruction keywords. "
            "Eval target: IMPLICIT_CONTEXT trigger handling 'fix/implement/add' instructions."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Instruction-to-file grounding evaluation")
    parser.add_argument("--dataset", default="small", help="Dataset name")
    parser.add_argument("--k", type=int, default=5, help="Recall@K and Precision@K")
    args = parser.parse_args()

    print("Instruction-to-File Grounding Evaluation")
    print(f"Dataset: {args.dataset} | K: {args.k}")
    print("=" * 60)

    try:
        results = run_evaluation(args.dataset, args.k)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"\nTotal queries: {results['total_queries']} (skipped: {results['skipped_no_gt']})")
    print(f"\nTrigger type distribution:")
    for t, count in results["trigger_type_distribution"].items():
        print(f"  {t}: {count}")

    print(f"\nPer-query results:")
    for r in results["per_query"]:
        k_val = results['k']
        print(f"\n  [{r['trigger_type_detected']}] \"{r['instruction']}\"")
        print(f"    GT: {r['ground_truth_size']} files | "
              f"Retrieved: {r['retrieved_count']} | "
              f"R@{k_val}={r[f'recall_at_{k_val}']:.3f} | "
              f"P@{k_val}={r[f'precision_at_{k_val}']:.3f}")

    print(f"\n{'=' * 60}")
    print(f"Average Recall@{results['k']}   : {results['avg_recall_at_k']:.3f}")
    print(f"Average Precision@{results['k']} : {results['avg_precision_at_k']:.3f}")
    print(f"Average NDCG@{results['k']}      : {results['avg_ndcg_at_k']:.3f}  ← [CoIR standard]")

    print(f"\n[GOAL 2 ASSESSMENT]")
    threshold = 0.5
    if results["avg_recall_at_k"] >= threshold:
        print(f"  PASS: Avg Recall@{results['k']} = {results['avg_recall_at_k']:.3f} >= {threshold}")
    else:
        print(f"  FAIL: Avg Recall@{results['k']} = {results['avg_recall_at_k']:.3f} < {threshold}")
        print(f"  → IMPLICIT_CONTEXT trigger or concept index needs improvement")

    # Trigger type check
    implicit_count = results["trigger_type_distribution"].get("IMPLICIT_CONTEXT", 0)
    total = results["total_queries"]
    implicit_rate = implicit_count / total if total > 0 else 0
    print(f"\n[TRIGGER CLASSIFICATION]")
    print(f"  IMPLICIT_CONTEXT rate: {implicit_count}/{total} = {implicit_rate:.1%}")
    if implicit_rate >= 0.7:
        print("  PASS: Most instruction queries correctly classified as IMPLICIT_CONTEXT")
    else:
        print("  WARN: Many instruction queries not classified as IMPLICIT_CONTEXT")
        print("  → Check trigger_classifier.py ACTION_VERBS coverage")

    # Save
    out_path = ROOT / "benchmarks" / "results" / "instruction_grounding_eval.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
