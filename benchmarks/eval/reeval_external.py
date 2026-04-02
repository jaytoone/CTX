#!/usr/bin/env python3
"""
reeval_external.py — Re-run CTX adaptive_trigger on external codebases.

Loads existing benchmark JSONs (benchmark_real_eval_*.json) which contain
query definitions and ground truth, then re-runs retrieval with the CURRENT
adaptive_trigger code and computes updated R@5.

Usage:
  python3 benchmarks/eval/reeval_external.py
"""

import json
import os
import sys
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import numpy as np

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

RESULTS_DIR = ROOT / "benchmarks" / "results"

# External repos — clone to temp if needed
REPOS = {
    "flask": {
        "benchmark_json": "benchmark_real_eval_flask.json",
        "git_url": "https://github.com/pallets/flask.git",
        "subdir": "src/flask",  # Python source directory
    },
    "fastapi": {
        "benchmark_json": "benchmark_real_eval_fastapi.json",
        "git_url": "https://github.com/tiangolo/fastapi.git",
        "subdir": "",  # Root (many test dirs)
    },
    "requests": {
        "benchmark_json": "benchmark_real_eval_requests.json",
        "git_url": "https://github.com/psf/requests.git",
        "subdir": "src/requests",
    },
}


def get_repo_path(repo_name: str, config: dict) -> str:
    """Get local path to repo, using cached /tmp dir if available."""
    tmp_path = f"/tmp/eval_{repo_name}"
    if os.path.isdir(tmp_path):
        return tmp_path
    # Try project path from benchmark JSON
    bm_path = RESULTS_DIR / config["benchmark_json"]
    if bm_path.exists():
        with open(bm_path) as f:
            data = json.load(f)
        proj_path = data.get("metadata", {}).get("project_path", "")
        if os.path.isdir(proj_path):
            return proj_path
    # Clone to /tmp
    print(f"  Cloning {config['git_url']} to {tmp_path}...")
    subprocess.run(["git", "clone", "--depth=1", config["git_url"], tmp_path],
                   capture_output=True, check=True)
    return tmp_path


def load_python_files(repo_path: str) -> Dict[str, str]:
    """Load all .py files from a repo path."""
    files = {}
    for root, dirs, fnames in os.walk(repo_path):
        # Skip hidden dirs, __pycache__, .git
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for fname in fnames:
            if fname.endswith('.py'):
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, repo_path)
                try:
                    with open(fpath, 'r', errors='replace') as f:
                        files[rel] = f.read()
                except Exception:
                    pass
    return files


def compute_recall_at_k(retrieved: List[str], relevant: List[str], k: int = 5) -> float:
    """Compute Recall@K."""
    if not relevant:
        return 0.0
    relevant_set = set(relevant)
    hits = sum(1 for f in retrieved[:k] if f in relevant_set)
    return hits / len(relevant_set)


def eval_repo(repo_name: str, config: dict) -> dict:
    """Evaluate CTX on a single external repo."""
    # Load benchmark query data
    bm_path = RESULTS_DIR / config["benchmark_json"]
    if not bm_path.exists():
        print(f"  SKIP: {bm_path} not found")
        return {}

    with open(bm_path) as f:
        bm_data = json.load(f)

    queries = bm_data["_query_results"]["adaptive_trigger"]
    print(f"  Loaded {len(queries)} queries from {config['benchmark_json']}")

    # Get repo and load files
    repo_path = get_repo_path(repo_name, config)
    files = load_python_files(repo_path)
    print(f"  Loaded {len(files)} .py files from {repo_path}")

    # Create CTX retriever
    retriever = AdaptiveTriggerRetriever(
        codebase_dir=repo_path,
        use_dense=False,
    )

    # Re-run queries
    results_by_type = defaultdict(list)
    all_results = []

    for q in queries:
        qid = q["query_id"]
        qtext = q["query_text"]
        trigger_type = q["trigger_type"]
        relevant = q["relevant_files"]

        # Run retrieval
        result = retriever.retrieve(qid, qtext, k=5)
        r5 = compute_recall_at_k(result.retrieved_files, relevant, k=5)

        results_by_type[trigger_type].append(r5)
        all_results.append({
            "query_id": qid,
            "trigger_type": trigger_type,
            "recall@5": r5,
            "n_relevant": len(relevant),
            "old_recall@5": q["metrics"]["recall@5"],
        })

    # Compute aggregates
    overall_r5 = float(np.mean([r["recall@5"] for r in all_results]))
    old_r5 = float(np.mean([r["old_recall@5"] for r in all_results]))
    by_type = {}
    for ttype, scores in sorted(results_by_type.items()):
        old_scores = [r["old_recall@5"] for r in all_results if r["trigger_type"] == ttype]
        by_type[ttype] = {
            "r5": float(np.mean(scores)),
            "old_r5": float(np.mean(old_scores)),
            "n": len(scores),
        }

    return {
        "repo": repo_name,
        "n_files": len(files),
        "n_queries": len(queries),
        "overall_r5": overall_r5,
        "old_r5": old_r5,
        "delta": overall_r5 - old_r5,
        "by_type": by_type,
        "details": all_results,
    }


def main():
    print("=" * 70)
    print("CTX External Codebase Re-Evaluation (iter 11)")
    print("=" * 70)

    all_repo_results = {}
    for repo_name, config in REPOS.items():
        print(f"\n[{repo_name.upper()}]")
        result = eval_repo(repo_name, config)
        if result:
            all_repo_results[repo_name] = result

    # Summary table
    print("\n" + "=" * 70)
    print("SUMMARY — External R@5")
    print("=" * 70)
    print(f"{'Repo':<12} {'Old R@5':>8} {'New R@5':>8} {'Delta':>8}")
    print("-" * 40)
    means_old, means_new = [], []
    for repo_name, res in all_repo_results.items():
        print(f"{repo_name:<12} {res['old_r5']:>8.4f} {res['overall_r5']:>8.4f} {res['delta']:>+8.4f}")
        means_old.append(res["old_r5"])
        means_new.append(res["overall_r5"])
        # Per-type breakdown
        for ttype, data in sorted(res["by_type"].items()):
            delta = data["r5"] - data["old_r5"]
            marker = " **" if abs(delta) > 0.01 else ""
            print(f"  {ttype:<25} {data['old_r5']:>7.4f} → {data['r5']:>7.4f} ({delta:>+.4f}){marker}")

    if means_old:
        mean_old = float(np.mean(means_old))
        mean_new = float(np.mean(means_new))
        print("-" * 40)
        print(f"{'MEAN':<12} {mean_old:>8.4f} {mean_new:>8.4f} {mean_new - mean_old:>+8.4f}")

    # Save results
    out_path = RESULTS_DIR / "reeval_external_iter11.json"
    with open(out_path, "w") as f:
        json.dump(all_repo_results, f, indent=2, default=str)
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
