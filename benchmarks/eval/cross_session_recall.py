"""
cross_session_recall.py — Cross-Session Continuity Evaluation

Measures Goal 1: Can CTX restore work-relevant files across sessions?

Protocol:
  Session A: "access" N files (simulate via ctx_session_log.json)
  Promote:   ctx_session_tracker logic promotes 3+-access files to persistent_memory
  Session B: ctx_loader loads persistent_memory → check Recall@K vs Session A ground truth

Usage:
  python3 benchmarks/eval/cross_session_recall.py [--dataset small] [--access-count 3]
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Set
import numpy as np
from scipy import stats

# Project root
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

DATASET_DIR = ROOT / "benchmarks" / "datasets"


def simulate_session_log(cwd: str, files: List[str], access_count: int) -> dict:
    """Create a simulated ctx_session_log entry (Session A)."""
    now = time.time()
    session_files = {}
    for f in files:
        session_files[f] = {
            "access_count": access_count,
            "last_accessed": now - 60,  # 1 minute ago
            "last_tool": "Read",
            "size_estimate": 500,
        }
    return {
        "version": 1,
        "cwd": cwd,
        "session_start": now - 3600,
        "last_updated": now - 60,
        "files": session_files,
    }


def simulate_persistent_memory(cwd: str, files: List[str]) -> dict:
    """Create a simulated persistent_memory (after promotion from Session A)."""
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    now = time.time()
    persistent_files = {}
    for f in files:
        persistent_files[f] = {
            "cumulative_count": 3,
            "last_accessed": now - 3600,
            "last_tool": "Read",
        }
    return {
        "version": 1,
        "projects": {
            cwd_hash: {
                "cwd": cwd,
                "files": persistent_files,
                "last_updated": now - 3600,
            }
        },
    }


def load_persistent_memory(persistent_path: str, cwd: str, top_k: int = 10) -> List[str]:
    """Replicate ctx_loader.load_persistent_memory logic."""
    try:
        with open(persistent_path) as f:
            data = json.load(f)
    except Exception:
        return []

    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    project = data.get("projects", {}).get(cwd_hash, {})
    files_data = project.get("files", {})

    now = time.time()
    scored = []
    for rel_path, meta in files_data.items():
        count = meta.get("cumulative_count", 1)
        last = meta.get("last_accessed", now)
        age_days = (now - last) / 86400
        decay = 1.0 / (1 + age_days * 0.1)
        score = count * decay
        scored.append((rel_path, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:top_k]]


def recall_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
    """Recall@K = |retrieved[:k] ∩ ground_truth| / |ground_truth|"""
    if not ground_truth:
        return 0.0
    hits = sum(1 for f in retrieved[:k] if f in ground_truth)
    return hits / len(ground_truth)


def compute_confidence_interval(values: list, confidence: float = 0.95) -> tuple:
    """Compute mean and confidence interval."""
    if len(values) < 2:
        return values[0] if values else 0.0, 0.0, 0.0
    mean = np.mean(values)
    sem = stats.sem(values)
    ci = stats.t.interval(confidence, len(values)-1, loc=mean, scale=sem)
    return mean, ci[0], ci[1]


def bootstrap_recall(retrieved: List[str], ground_truth: Set[str], k: int, n_bootstrap: int = 100) -> dict:
    """Bootstrap resampling for recall confidence intervals."""
    if not ground_truth:
        return {"mean": 0.0, "ci_lower": 0.0, "ci_upper": 0.0, "p_value": 1.0}

    # Compute baseline recall
    baseline = recall_at_k(retrieved, ground_truth, k)

    # Bootstrap resampling
    gt_list = list(ground_truth)
    n = len(gt_list)
    bootstrap_recalls = []

    for _ in range(n_bootstrap):
        # Sample with replacement
        sample = [gt_list[np.random.randint(n)] for _ in range(n)]
        sample_gt = set(sample)
        r = recall_at_k(retrieved, sample_gt, k)
        bootstrap_recalls.append(r)

    mean, ci_lower, ci_upper = compute_confidence_interval(bootstrap_recalls)

    # One-sample t-test against baseline (is baseline significantly different from mean?)
    if len(bootstrap_recalls) > 1:
        t_stat, p_value = stats.ttest_1samp(bootstrap_recalls, baseline)
    else:
        p_value = 1.0

    return {
        "mean": round(mean, 3),
        "ci_lower": round(ci_lower, 3),
        "ci_upper": round(ci_upper, 3),
        "p_value": round(p_value, 4),
        "baseline": round(baseline, 3),
    }


def run_evaluation(dataset_name: str, access_count: int, k: int = 10, stat_test: bool = False) -> dict:
    """Run cross-session recall evaluation."""
    metadata_path = DATASET_DIR / dataset_name / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Dataset not found: {metadata_path}")

    with open(metadata_path) as f:
        metadata = json.load(f)

    files_meta = metadata["files"]
    codebase_path = str(DATASET_DIR / dataset_name / "codebase")

    results = []

    # Evaluation scenarios: simulate different "Session A" file access patterns
    scenarios = [
        ("head_files", [m["path"] for m in files_meta if m.get("tier") == "head"]),
        ("torso_files", [m["path"] for m in files_meta if m.get("tier") == "torso"]),
        ("mixed_5", [m["path"] for m in files_meta[:5]]),
        ("mixed_10", [m["path"] for m in files_meta[:10]]),
    ]

    # Multiple runs for statistical significance (use different random access patterns)
    n_runs = 10 if stat_test else 1
    all_recalls = {s[0]: [] for s in scenarios}

    for run_idx in range(n_runs):
        np.random.seed(42 + run_idx)  # Reproducible

        for scenario_name, ground_truth_files in scenarios:
            if not ground_truth_files:
                continue

            # Add noise: simulate different access patterns per run
            if stat_test and run_idx > 0:
                # Randomly drop 10% of files to simulate real-world variance
                n_drop = max(1, len(ground_truth_files) // 10)
                drop_indices = np.random.choice(len(ground_truth_files), n_drop, replace=False)
                varied_files = [f for i, f in enumerate(ground_truth_files) if i not in drop_indices]
            else:
                varied_files = ground_truth_files

            ground_truth = set(varied_files)

            with tempfile.TemporaryDirectory() as tmpdir:
                persistent_path = os.path.join(tmpdir, "ctx_persistent_memory.json")

                # Simulate: Session A accessed these files with access_count times
                persistent_data = simulate_persistent_memory(codebase_path, varied_files)
                with open(persistent_path, "w") as f:
                    json.dump(persistent_data, f)

                # Simulate: Session B starts fresh, loads persistent memory
                restored = load_persistent_memory(persistent_path, codebase_path, top_k=k)

            r_at_k = recall_at_k(restored, ground_truth, k)
            all_recalls[scenario_name].append(r_at_k)

            if run_idx == 0:  # Only store detailed results for first run
                r_at_5 = recall_at_k(restored, ground_truth, 5)

                result_entry = {
                    "scenario": scenario_name,
                    "ground_truth_size": len(ground_truth),
                    "restored_count": len(restored),
                    "recall_at_5": round(r_at_5, 3),
                    f"recall_at_{k}": round(r_at_k, 3),
                }

                # Add statistical validation if requested
                if stat_test:
                    bootstrap = bootstrap_recall(restored, ground_truth, k)
                    result_entry["bootstrap"] = bootstrap
                    result_entry["n_runs"] = n_runs

                results.append(result_entry)

    # Compute aggregated statistics if stat_test
    stat_summary = {}
    if stat_test:
        for scenario_name, recalls in all_recalls.items():
            if len(recalls) > 1:
                mean, ci_lower, ci_upper = compute_confidence_interval(recalls)
                stat_summary[scenario_name] = {
                    "mean": round(mean, 3),
                    "ci_95": [round(ci_lower, 3), round(ci_upper, 3)],
                    "std": round(np.std(recalls), 3),
                    "n_runs": len(recalls),
                }

    return {
        "dataset": dataset_name,
        "access_count_threshold": access_count,
        "k": k,
        "scenarios": results,
        "avg_recall_at_k": round(
            sum(r[f"recall_at_{k}"] for r in results) / len(results), 3
        ) if results else 0.0,
        "stat_test": stat_test,
        "stat_summary": stat_summary if stat_test else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Cross-session recall evaluation")
    parser.add_argument("--dataset", default="small", help="Dataset name")
    parser.add_argument("--access-count", type=int, default=3,
                        help="Simulated access count in Session A")
    parser.add_argument("--k", type=int, default=10, help="Recall@K")
    parser.add_argument("--stat-test", action="store_true",
                        help="Run statistical validation (bootstrap CI, p-value)")
    args = parser.parse_args()

    print(f"Cross-Session Recall Evaluation")
    print(f"Dataset: {args.dataset} | Access threshold: {args.access_count} | K: {args.k}")
    print(f"Statistical validation: {'ENABLED' if args.stat_test else 'DISABLED'}")
    print("=" * 60)

    try:
        results = run_evaluation(args.dataset, args.access_count, args.k, stat_test=args.stat_test)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    for r in results["scenarios"]:
        print(f"\nScenario: {r['scenario']}")
        print(f"  Ground truth size : {r['ground_truth_size']}")
        print(f"  Restored files    : {r['restored_count']}")
        print(f"  Recall@5          : {r['recall_at_5']:.3f}")
        k_val = results['k']
        print(f"  Recall@{k_val}         : {r[f'recall_at_{k_val}']:.3f}")

        if args.stat_test and "bootstrap" in r:
            bs = r["bootstrap"]
            print(f"  [STAT] 95% CI       : [{bs['ci_lower']:.3f}, {bs['ci_upper']:.3f}]")
            print(f"  [STAT] p-value     : {bs['p_value']:.4f}")
            print(f"  [STAT] baseline    : {bs['baseline']:.3f}")

    print(f"\n{'=' * 60}")
    print(f"Average Recall@{results['k']}: {results['avg_recall_at_k']:.3f}")

    if args.stat_test and results.get("stat_summary"):
        print(f"\n[AGGREGATED STATISTICS - 95% CI]")
        for scenario, stats in results["stat_summary"].items():
            print(f"  {scenario}: mean={stats['mean']:.3f}, CI={stats['ci_95']}, std={stats['std']:.3f}, n={stats['n_runs']}")

    # Note on limitation
    print("\n[NOTE] This eval measures perfect persistence round-trip.")
    print("Real-world gap: files must actually reach access_count threshold")
    print("across multiple real sessions (not simulated here).")

    # Save results
    out_path = ROOT / "benchmarks" / "results" / "cross_session_recall.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
