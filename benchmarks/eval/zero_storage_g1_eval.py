#!/usr/bin/env python3
"""
zero_storage_g1_eval.py — G1 Assessment Without Persistent Storage

Measures: Can CTX's adaptive_trigger surface work-relevant files
from a query ALONE, without persistent_memory or session_log?

Protocol:
  Session A: User works on files (ground truth)
  Session B: NO persistent_memory loaded. User types a query.
             CTX adaptive_trigger retrieves files.
             Measure Recall@K against Session A ground truth.

This is the "updated G1" — zero-storage instant retrieval quality.

Usage:
  python3 benchmarks/eval/zero_storage_g1_eval.py [--dataset small] [--k 5]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
from scipy import stats

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

DATASET_DIR = ROOT / "benchmarks" / "datasets"
RESULTS_DIR = ROOT / "benchmarks" / "results"


# ─── Query Templates ────────────────────────────────────────────────────────

def generate_session_queries(files_meta: List[dict], codebase_path: str) -> List[dict]:
    """Generate natural language queries that a user might type to recall files.

    Each query simulates: 'I was working on X, show me the relevant files'
    without any stored session state.
    """
    queries = []
    qid = 0

    for meta in files_meta:
        fpath = meta["path"]
        tier = meta.get("tier", "unknown")
        concepts = meta.get("concepts", [])
        basename = os.path.splitext(os.path.basename(fpath))[0]

        # Type 1: Module name query (EXPLICIT_SYMBOL-like)
        queries.append({
            "query_id": f"zg1_{qid:04d}",
            "query_text": f"Show me the code for {basename}",
            "query_type": "module_name",
            "ground_truth": fpath,
            "tier": tier,
        })
        qid += 1

        # Type 2: Concept query (SEMANTIC_CONCEPT-like)
        if concepts:
            for concept in concepts[:2]:
                queries.append({
                    "query_id": f"zg1_{qid:04d}",
                    "query_text": f"Find code related to {concept}",
                    "query_type": "concept",
                    "ground_truth": fpath,
                    "tier": tier,
                })
                qid += 1

        # Type 3: Task context query (IMPLICIT_CONTEXT-like)
        queries.append({
            "query_id": f"zg1_{qid:04d}",
            "query_text": f"What modules are needed to understand {basename}",
            "query_type": "implicit",
            "ground_truth": fpath,
            "tier": tier,
        })
        qid += 1

    return queries


def generate_session_queries_from_codebase(
    retriever: AdaptiveTriggerRetriever,
    ground_truth_files: List[str],
    codebase_path: str,
) -> List[dict]:
    """Generate queries from actual codebase file content.

    Extracts function/class names from ground truth files to create
    realistic "I was working on X" queries.
    """
    queries = []
    qid = 0

    for fpath in ground_truth_files:
        basename = os.path.splitext(os.path.basename(fpath))[0]

        # Module name query
        queries.append({
            "query_id": f"zg1_{qid:04d}",
            "query_text": f"Show me the code for {basename}",
            "query_type": "module_name",
            "ground_truth": fpath,
        })
        qid += 1

        # Extract symbols from file content
        content = retriever.files.get(fpath, "")
        symbols = re.findall(r'(?:def|class)\s+([a-zA-Z_][a-zA-Z0-9_]{3,})', content)
        for sym in symbols[:3]:  # Max 3 symbol queries per file
            queries.append({
                "query_id": f"zg1_{qid:04d}",
                "query_text": f"Find the function {sym} and show its implementation",
                "query_type": "symbol",
                "ground_truth": fpath,
            })
            qid += 1

        # Implicit context query
        queries.append({
            "query_id": f"zg1_{qid:04d}",
            "query_text": f"What modules are needed to understand {basename}",
            "query_type": "implicit",
            "ground_truth": fpath,
        })
        qid += 1

    return queries


def recall_at_k(retrieved: List[str], ground_truth: str, k: int) -> float:
    """R@K for single ground truth file."""
    return 1.0 if ground_truth in retrieved[:k] else 0.0


def run_zero_storage_dataset(
    dataset_name: str = "small",
    k: int = 5,
) -> dict:
    """Run zero-storage G1 on a benchmark dataset."""
    metadata_path = DATASET_DIR / dataset_name / "metadata.json"
    codebase_path = str(DATASET_DIR / dataset_name / "codebase")

    if not metadata_path.exists():
        print(f"Dataset {dataset_name} not found, using CTX project itself")
        return run_self_assessment(k=k)

    with open(metadata_path) as f:
        metadata = json.load(f)

    files_meta = metadata["files"]

    # Build CTX retriever on the dataset codebase
    retriever = AdaptiveTriggerRetriever(codebase_dir=codebase_path, use_dense=False)

    # Generate queries
    ground_truth_files = [m["path"] for m in files_meta]
    queries = generate_session_queries(files_meta, codebase_path)

    print(f"Dataset: {dataset_name}")
    print(f"Files: {len(ground_truth_files)}, Queries: {len(queries)}")

    # Run assessment
    results_by_type = defaultdict(list)
    results_by_tier = defaultdict(list)
    all_results = []

    for q in queries:
        result = retriever.retrieve(q["query_id"], q["query_text"], k=k)
        r_at_k = recall_at_k(result.retrieved_files, q["ground_truth"], k)
        results_by_type[q["query_type"]].append(r_at_k)
        if "tier" in q:
            results_by_tier[q["tier"]].append(r_at_k)
        all_results.append({
            "query_id": q["query_id"],
            "query_type": q["query_type"],
            "recall_at_k": r_at_k,
            "ground_truth": q["ground_truth"],
            "retrieved": result.retrieved_files[:k],
        })

    # Aggregates
    overall_r_at_k = float(np.mean([r["recall_at_k"] for r in all_results]))
    by_type = {t: {"r_at_k": float(np.mean(scores)), "n": len(scores)}
               for t, scores in sorted(results_by_type.items())}
    by_tier = {t: {"r_at_k": float(np.mean(scores)), "n": len(scores)}
               for t, scores in sorted(results_by_tier.items())}

    return {
        "assessment_type": "zero_storage_g1",
        "dataset": dataset_name,
        "k": k,
        "n_files": len(ground_truth_files),
        "n_queries": len(queries),
        "overall_recall_at_k": round(overall_r_at_k, 4),
        "by_query_type": by_type,
        "by_tier": by_tier,
        "per_query": all_results,
    }


def run_self_assessment(k: int = 5) -> dict:
    """Run on CTX project itself as a fallback."""
    project_path = str(ROOT)
    retriever = AdaptiveTriggerRetriever(codebase_dir=project_path, use_dense=False)

    # Use key files as ground truth
    key_files = [
        "src/retrieval/adaptive_trigger.py",
        "src/trigger/trigger_classifier.py",
        "src/retrieval/full_context.py",
    ]
    key_files = [f for f in key_files if f in retriever.files]

    queries = generate_session_queries_from_codebase(retriever, key_files, project_path)
    print(f"Self-assessment: {len(key_files)} ground truth files, {len(queries)} queries")

    results = []
    for q in queries:
        result = retriever.retrieve(q["query_id"], q["query_text"], k=k)
        r_at_k = recall_at_k(result.retrieved_files, q["ground_truth"], k)
        results.append({"recall_at_k": r_at_k, "query_type": q["query_type"]})

    overall = float(np.mean([r["recall_at_k"] for r in results]))
    by_type = defaultdict(list)
    for r in results:
        by_type[r["query_type"]].append(r["recall_at_k"])
    by_type_agg = {t: {"r_at_k": float(np.mean(s)), "n": len(s)} for t, s in by_type.items()}

    return {
        "assessment_type": "zero_storage_g1_self",
        "dataset": "CTX",
        "k": k,
        "n_queries": len(queries),
        "overall_recall_at_k": round(overall, 4),
        "by_query_type": by_type_agg,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="small")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    print("=" * 60)
    print("G1 Zero-Storage Assessment")
    print("=" * 60)

    result = run_zero_storage_dataset(args.dataset, args.k)

    print(f"\n{'='*60}")
    print(f"RESULTS — Zero-Storage G1 Recall@{args.k}")
    print(f"{'='*60}")
    print(f"Overall R@{args.k}: {result['overall_recall_at_k']:.4f}")
    print(f"\nBy query type:")
    for qtype, data in result.get("by_query_type", {}).items():
        print(f"  {qtype:<20} R@{args.k}={data['r_at_k']:.4f}  (n={data['n']})")
    if result.get("by_tier"):
        print(f"\nBy tier:")
        for tier, data in result["by_tier"].items():
            print(f"  {tier:<20} R@{args.k}={data['r_at_k']:.4f}  (n={data['n']})")

    # Save
    out_path = RESULTS_DIR / "zero_storage_g1_results.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
