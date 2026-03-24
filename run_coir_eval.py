#!/usr/bin/env python3
"""
CTX COIR-style Evaluation using CodeSearchNet Python.

Usage:
    python3 run_coir_eval.py --n-queries 100
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.evaluator.coir_evaluator import run_coir_evaluation


def main():
    parser = argparse.ArgumentParser(
        description="CTX COIR-style evaluation using CodeSearchNet"
    )
    parser.add_argument(
        "--n-queries",
        type=int,
        default=100,
        help="Number of queries to evaluate (default: 100)",
    )
    parser.add_argument(
        "--corpus-multiplier",
        type=int,
        default=10,
        help="Corpus size multiplier (default: 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--results-dir",
        default="benchmarks/results",
        help="Results directory (default: benchmarks/results)",
    )
    args = parser.parse_args()

    start_time = time.time()
    results = run_coir_evaluation(
        n_queries=args.n_queries,
        corpus_multiplier=args.corpus_multiplier,
        seed=args.seed,
        results_dir=args.results_dir,
    )
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"COIR Evaluation DONE in {elapsed:.1f}s")
    for name, data in results["strategies"].items():
        print(f"  {name}: R@1={data['recall_at_1']:.3f}  R@5={data['recall_at_5']:.3f}  MRR={data['mrr']:.3f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
