#!/usr/bin/env python3
"""
CTX Experiment Runner

Main entry point for the Context-Triggered eXperimentation benchmark.

Usage:
    # Synthetic dataset
    python run_experiment.py --dataset-size small --strategy all
    python run_experiment.py --dataset-size medium --strategy trigger

    # Real codebase
    python run_experiment.py --dataset-source real --project-path /path/to/project --strategy all
"""

import argparse
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.evaluator.benchmark_runner import BenchmarkRunner
from src.visualizer.report import generate_report, save_report


STRATEGY_ALIASES = {
    "all": ["full_context", "bm25", "dense_tfidf", "graph_rag", "adaptive_trigger", "llamaindex", "chroma_dense", "hybrid_dense_ctx"],
    "trigger": ["adaptive_trigger"],
    "full": ["full_context"],
    "graph": ["graph_rag"],
    "baselines": ["full_context", "bm25", "dense_tfidf", "graph_rag", "llamaindex", "chroma_dense", "hybrid_dense_ctx"],
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="CTX Experiment: Context-Triggered Retrieval Benchmark"
    )
    parser.add_argument(
        "--dataset-source",
        choices=["synthetic", "real"],
        default="synthetic",
        help="Dataset source: synthetic (generated) or real (existing codebase)",
    )
    parser.add_argument(
        "--dataset-size",
        choices=["small", "medium"],
        default="small",
        help="Size of synthetic dataset to generate (default: small)",
    )
    parser.add_argument(
        "--project-path",
        type=str,
        default=None,
        help="Path to real Python project (required when --dataset-source=real)",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="all",
        help=(
            "Retrieval strategies to run. Options: "
            "all, trigger, full, bm25, dense_tfidf, adaptive_trigger, "
            "or comma-separated list (default: all)"
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--k-values",
        type=str,
        default="1,3,5,10",
        help="Comma-separated K values for Recall@K (default: 1,3,5,10)",
    )
    parser.add_argument(
        "--mode",
        choices=["benchmark", "ablation"],
        default="benchmark",
        help="Run mode: benchmark (standard) or ablation (ablation study)",
    )
    return parser.parse_args()


def resolve_strategies(strategy_arg: str) -> list:
    """Resolve strategy argument to list of strategy names."""
    if strategy_arg in STRATEGY_ALIASES:
        return STRATEGY_ALIASES[strategy_arg]

    # Comma-separated list
    parts = [s.strip() for s in strategy_arg.split(",")]
    resolved = []
    for part in parts:
        if part in STRATEGY_ALIASES:
            resolved.extend(STRATEGY_ALIASES[part])
        else:
            resolved.append(part)
    return resolved


def main():
    args = parse_args()

    if args.dataset_source == "real" and args.project_path is None:
        print("ERROR: --project-path is required when --dataset-source=real")
        sys.exit(1)

    strategies = resolve_strategies(args.strategy)
    k_values = [int(k) for k in args.k_values.split(",")]

    print("=" * 70)
    print("  CTX Experiment: Context-Triggered Retrieval Benchmark")
    print("=" * 70)
    print(f"  Dataset source: {args.dataset_source}")
    if args.dataset_source == "real":
        print(f"  Project path : {args.project_path}")
    else:
        print(f"  Dataset size : {args.dataset_size}")
    print(f"  Strategies   : {', '.join(strategies)}")
    print(f"  K values     : {k_values}")
    print(f"  Seed         : {args.seed}")
    print("=" * 70)

    runner = BenchmarkRunner(base_dir=PROJECT_ROOT, seed=args.seed)

    if args.mode == "ablation":
        # Ablation study mode
        if args.dataset_source == "real":
            from src.data.real_codebase_loader import RealCodebaseLoader
            loader = RealCodebaseLoader(args.project_path, seed=args.seed)
            metadata = loader.load()
            codebase_dir = metadata["codebase_dir"]
            queries = metadata["queries"]
            file_tiers = {f["path"]: f.get("tier", "tail") for f in metadata["files"]}
            label = f"real_{os.path.basename(args.project_path)}"
        else:
            from src.data.dataset_generator import DatasetGenerator
            dataset_dir = os.path.join(PROJECT_ROOT, "benchmarks", "datasets", args.dataset_size)
            generator = DatasetGenerator(seed=args.seed)
            metadata = generator.generate(args.dataset_size, dataset_dir)
            codebase_dir = os.path.join(dataset_dir, "codebase")
            queries = metadata["queries"]
            file_tiers = {f["path"]: f["tier"] for f in metadata["files"]}
            label = args.dataset_size

        benchmark = runner.run_ablation(
            codebase_dir=codebase_dir,
            queries=queries,
            file_tiers=file_tiers,
            k_values=k_values,
            dataset_label=label,
            metadata={"file_count": metadata["file_count"], "query_count": len(queries)},
        )
        report_label = f"ablation_{label}"
    elif args.dataset_source == "real":
        benchmark = runner.run_real(
            project_path=args.project_path,
            strategies=strategies,
            k_values=k_values,
        )
        report_label = f"real_{os.path.basename(args.project_path)}"
    else:
        benchmark = runner.run(
            dataset_size=args.dataset_size,
            strategies=strategies,
            k_values=k_values,
        )
        report_label = args.dataset_size

    # Generate report
    report_path = os.path.join(
        PROJECT_ROOT, "benchmarks", "results",
        f"report_{report_label}.txt",
    )
    save_report(benchmark, report_path)

    print("\nExperiment completed successfully.")


if __name__ == "__main__":
    main()
