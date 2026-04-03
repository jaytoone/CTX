#!/usr/bin/env python3
"""
trigger_surfacing_g1_eval.py — G1 Trigger→Surfacing Evaluation

Measures the TRUE G1: "When user types a work prompt, does CTX surface
the files they'll actually need?"

Ground truth: git commit history — files modified together in a commit
represent "files needed for that task."

Protocol:
  1. Extract commit messages + modified files from git log
  2. For each commit: use message as "trigger prompt"
  3. CTX retrieves files for that prompt
  4. Measure: how many of the actually-modified files are in CTX's top-K?

This is fundamentally different from "project understanding questions":
- Old eval: "What is BM25?" → check if LLM answers correctly
- New eval: "fix BM25 keyword retrieval" → check if CTX finds adaptive_trigger.py

Usage:
  python3 benchmarks/eval/trigger_surfacing_g1_eval.py [--project-path .] [--k 5] [--n-commits 20]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

RESULTS_DIR = ROOT / "benchmarks" / "results"


def extract_commit_tasks(project_path: str, n_commits: int = 30) -> List[dict]:
    """Extract work tasks from git history.

    Each commit = one "work trigger" with:
    - trigger: commit message (= what the user was working on)
    - ground_truth: files modified in that commit (= files they needed)
    """
    try:
        result = subprocess.run(
            ["git", "log", f"-{n_commits}", "--name-only", "--format=COMMIT_SEP%n%H%n%s", "--", "*.py"],
            cwd=project_path, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return []
    except Exception:
        return []

    tasks = []
    blocks = result.stdout.split("COMMIT_SEP\n")

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if len(lines) < 2:
            continue

        commit_hash = lines[0].strip()
        message = lines[1].strip()
        files = [l.strip() for l in lines[2:] if l.strip() and l.strip().endswith(".py")]

        if not files or not message:
            continue

        # Skip merge commits and version bumps
        if message.startswith("Merge") or message.startswith("v"):
            continue

        # Extract a natural "trigger" from commit message
        # Remove prefixes like "20260402 1717" or "live-inf iter N:"
        trigger = re.sub(r'^\d{8}\s+\d{4}\s+', '', message)
        trigger = re.sub(r'^(live-inf|live-infinite|omc-live)\s+iter\s+\d+/[∞\d]+:\s*', '', trigger)
        trigger = re.sub(r'^(success|partial)\s*\|\s*goal_v\d+:\s*', '', trigger)
        trigger = trigger.strip()

        if len(trigger) < 10:
            continue

        tasks.append({
            "commit": commit_hash[:8],
            "trigger": trigger,
            "ground_truth_files": files,
            "n_files": len(files),
        })

    return tasks


def eval_surfacing(
    project_path: str = ".",
    k: int = 5,
    n_commits: int = 30,
) -> dict:
    """Evaluate CTX's trigger→surfacing quality."""
    project_path = os.path.abspath(project_path)

    # Extract tasks from git
    tasks = extract_commit_tasks(project_path, n_commits)
    print(f"Extracted {len(tasks)} work tasks from git history")

    if not tasks:
        return {"error": "no_tasks"}

    # Build CTX retriever
    retriever = AdaptiveTriggerRetriever(codebase_dir=project_path, use_dense=False)

    # Evaluate each task
    results = []
    hit_at_k = []
    file_recall = []

    for task in tasks:
        trigger = task["trigger"]
        gt_files = set(task["ground_truth_files"])

        # CTX retrieves files for this trigger
        result = retriever.retrieve("g1_trigger", trigger, k=k)
        retrieved = set(result.retrieved_files[:k])

        # Metrics:
        # 1. Hit@K: is ANY ground truth file in top-K? (binary)
        hit = 1.0 if retrieved & gt_files else 0.0

        # 2. File Recall@K: fraction of ground truth files found in top-K
        if gt_files:
            recall = len(retrieved & gt_files) / len(gt_files)
        else:
            recall = 0.0

        # 3. Precision: fraction of retrieved files that are in ground truth
        precision = len(retrieved & gt_files) / len(retrieved) if retrieved else 0.0

        hit_at_k.append(hit)
        file_recall.append(recall)

        results.append({
            "commit": task["commit"],
            "trigger": trigger[:80],
            "n_gt_files": len(gt_files),
            "hit_at_k": hit,
            "file_recall": round(recall, 3),
            "precision": round(precision, 3),
            "gt_files": list(gt_files)[:5],
            "retrieved": list(retrieved)[:5],
            "overlap": list(retrieved & gt_files),
        })

    # Aggregates
    mean_hit = float(np.mean(hit_at_k))
    mean_recall = float(np.mean(file_recall))

    # Also compute random baseline: what if we picked K random .py files?
    all_py = [f for f in retriever.file_paths if f.endswith(".py")]
    random_hits = []
    random_recalls = []
    np.random.seed(42)
    for task in tasks:
        gt_files = set(task["ground_truth_files"])
        random_k = set(np.random.choice(all_py, min(k, len(all_py)), replace=False))
        random_hits.append(1.0 if random_k & gt_files else 0.0)
        random_recalls.append(len(random_k & gt_files) / len(gt_files) if gt_files else 0.0)

    mean_random_hit = float(np.mean(random_hits))
    mean_random_recall = float(np.mean(random_recalls))

    output = {
        "eval_type": "trigger_surfacing_g1",
        "project_path": project_path,
        "timestamp": datetime.now().isoformat(),
        "k": k,
        "n_tasks": len(tasks),
        "n_py_files": len(all_py),
        "overall": {
            "ctx_hit_at_k": round(mean_hit, 4),
            "ctx_file_recall": round(mean_recall, 4),
            "random_hit_at_k": round(mean_random_hit, 4),
            "random_file_recall": round(mean_random_recall, 4),
            "hit_delta": round(mean_hit - mean_random_hit, 4),
            "recall_delta": round(mean_recall - mean_random_recall, 4),
        },
        "per_task": results,
    }

    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", default=".")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--n-commits", type=int, default=30)
    args = parser.parse_args()

    print("=" * 60)
    print("G1 Trigger→Surfacing Evaluation")
    print("  'When you type a work prompt, does CTX find the right files?'")
    print("=" * 60)

    result = eval_surfacing(args.project_path, args.k, args.n_commits)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        return

    o = result["overall"]
    print(f"\n{'='*60}")
    print(f"RESULTS — Trigger→Surfacing (k={args.k}, {result['n_tasks']} tasks)")
    print(f"{'='*60}")
    print(f"CTX Hit@{args.k}:        {o['ctx_hit_at_k']:.4f}  (found >= 1 needed file)")
    print(f"Random Hit@{args.k}:     {o['random_hit_at_k']:.4f}")
    print(f"Hit Delta:          {o['hit_delta']:+.4f}")
    print(f"")
    print(f"CTX File Recall:    {o['ctx_file_recall']:.4f}  (fraction of needed files found)")
    print(f"Random File Recall: {o['random_file_recall']:.4f}")
    print(f"Recall Delta:       {o['recall_delta']:+.4f}")

    # Show sample tasks
    print(f"\nSample tasks:")
    for r in result["per_task"][:5]:
        marker = "HIT" if r["hit_at_k"] else "MISS"
        print(f"  [{marker}] {r['trigger'][:50]}...")
        print(f"    needed: {r['gt_files'][:3]} | got: {r['retrieved'][:3]}")

    out_path = RESULTS_DIR / "trigger_surfacing_g1_results.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
