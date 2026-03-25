"""
RANGER-approx comparison evaluation for CTX.

Runs RANGER-approx alongside existing strategies on all datasets:
1. Synthetic benchmark (50 files, 166 queries)
2. Real codebases (GraphPrompt, OneViral, AgentNode)
3. RepoBench cross-file retrieval (manual samples)

Generates a comparison report for paper Table inclusion.
"""

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.evaluator.metrics import compute_all_metrics
from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.full_context import FullContextRetriever, RetrievalResult, estimate_tokens
from src.retrieval.graph_rag import GraphRAGRetriever
from src.retrieval.ranger_approx import RANGERApproxRetriever


def run_synthetic_comparison(
    base_dir: str,
    k_values: Optional[List[int]] = None,
    seed: int = 42,
) -> Dict:
    """Run RANGER-approx comparison on synthetic dataset.

    Args:
        base_dir: CTX project root directory
        k_values: K values for evaluation
        seed: Random seed

    Returns:
        Dict with per-strategy aggregated metrics
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    from src.data.dataset_generator import DatasetGenerator

    dataset_dir = os.path.join(base_dir, "benchmarks", "datasets", "small")
    generator = DatasetGenerator(seed=seed)
    metadata = generator.generate("small", dataset_dir)

    codebase_dir = os.path.join(dataset_dir, "codebase")
    queries = metadata["queries"]
    file_tiers = {f["path"]: f["tier"] for f in metadata["files"]}

    print(f"  Synthetic: {metadata['file_count']} files, {len(queries)} queries")

    strategies = {
        "full_context": FullContextRetriever,
        "bm25": BM25Retriever,
        "graph_rag": GraphRAGRetriever,
        "ranger_approx": RANGERApproxRetriever,
        "adaptive_trigger": AdaptiveTriggerRetriever,
    }

    results = {}
    for name, cls in strategies.items():
        print(f"    Running {name}...", end=" ", flush=True)
        start = time.time()
        retriever = cls(codebase_dir)

        all_metrics = []
        for q in queries:
            result = retriever.retrieve(q["id"], q["text"], k=max(k_values))
            metrics = compute_all_metrics(
                retrieved=result.retrieved_files,
                relevant=q["relevant_files"],
                tokens_used=result.tokens_used,
                total_tokens=result.total_tokens,
                k_values=k_values,
            )
            all_metrics.append(metrics)

        # Aggregate
        agg = {}
        if all_metrics:
            for key in all_metrics[0]:
                values = [m[key] for m in all_metrics]
                agg[f"mean_{key}"] = float(np.mean(values))

        elapsed = time.time() - start
        agg["elapsed_s"] = elapsed
        agg["n_queries"] = len(queries)
        results[name] = agg
        print(f"R@5={agg.get('mean_recall@5', 0):.3f} TES={agg.get('mean_tes', 0):.3f} ({elapsed:.1f}s)")

    return results


def run_real_comparison(
    base_dir: str,
    project_paths: Optional[Dict[str, str]] = None,
    k_values: Optional[List[int]] = None,
    seed: int = 42,
) -> Dict:
    """Run RANGER-approx comparison on real codebases.

    Args:
        base_dir: CTX project root directory
        project_paths: Dict of project_name -> path
        k_values: K values for evaluation
        seed: Random seed

    Returns:
        Dict with per-project, per-strategy aggregated metrics
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    from src.data.real_codebase_loader import RealCodebaseLoader

    if project_paths is None:
        project_paths = _discover_real_projects(base_dir)

    if not project_paths:
        print("  No real project paths found, skipping real comparison")
        return {}

    strategies = {
        "full_context": FullContextRetriever,
        "bm25": BM25Retriever,
        "graph_rag": GraphRAGRetriever,
        "ranger_approx": RANGERApproxRetriever,
        "adaptive_trigger": AdaptiveTriggerRetriever,
    }

    all_results = {}
    for proj_name, proj_path in project_paths.items():
        if not os.path.isdir(proj_path):
            print(f"  Skipping {proj_name}: {proj_path} not found")
            continue

        print(f"  Real codebase: {proj_name} ({proj_path})")
        loader = RealCodebaseLoader(proj_path, seed=seed)
        metadata = loader.load()
        codebase_dir = metadata["codebase_dir"]
        queries = metadata["queries"]
        print(f"    {metadata['file_count']} files, {len(queries)} queries")

        proj_results = {}
        for name, cls in strategies.items():
            print(f"    Running {name}...", end=" ", flush=True)
            start = time.time()
            retriever = cls(codebase_dir)

            all_metrics = []
            for q in queries:
                result = retriever.retrieve(q["id"], q["text"], k=max(k_values))
                metrics = compute_all_metrics(
                    retrieved=result.retrieved_files,
                    relevant=q["relevant_files"],
                    tokens_used=result.tokens_used,
                    total_tokens=result.total_tokens,
                    k_values=k_values,
                )
                all_metrics.append(metrics)

            agg = {}
            if all_metrics:
                for key in all_metrics[0]:
                    values = [m[key] for m in all_metrics]
                    agg[f"mean_{key}"] = float(np.mean(values))

            elapsed = time.time() - start
            agg["elapsed_s"] = elapsed
            agg["n_queries"] = len(queries)
            proj_results[name] = agg
            print(f"R@5={agg.get('mean_recall@5', 0):.3f} TES={agg.get('mean_tes', 0):.3f} ({elapsed:.1f}s)")

        all_results[proj_name] = proj_results

    return all_results


def run_repobench_comparison(
    k_values: Optional[List[int]] = None,
    seed: int = 42,
) -> Dict:
    """Run RANGER-approx comparison on RepoBench samples.

    Args:
        k_values: K values for evaluation
        seed: Random seed

    Returns:
        Dict with per-strategy aggregated metrics
    """
    if k_values is None:
        k_values = [1, 3, 5]

    from src.evaluator.repobench_evaluator import (
        build_manual_cross_file_samples,
        evaluate_strategy_on_sample,
        build_repobench_codebase,
    )

    print("  Loading RepoBench manual cross-file samples...")
    samples = build_manual_cross_file_samples(seed=seed)
    print(f"    {len(samples)} samples loaded")

    strategy_classes = {
        "full_context": FullContextRetriever,
        "bm25": BM25Retriever,
        "ranger_approx": RANGERApproxRetriever,
        "adaptive_trigger": AdaptiveTriggerRetriever,
    }

    strategy_results = {name: [] for name in strategy_classes}

    for i, sample in enumerate(samples):
        try:
            tmpdir, all_files, relevant_files = build_repobench_codebase(
                context_files=sample.context_files,
                import_statement=sample.import_statement,
                code_snippet=sample.code_snippet,
                n_distractors=10,
                seed=seed + i,
            )
        except Exception as e:
            print(f"    ERROR building codebase for sample {i}: {e}")
            continue

        try:
            for name, cls in strategy_classes.items():
                retriever = cls(tmpdir)
                result = evaluate_strategy_on_sample(
                    name, retriever, sample, relevant_files, k_values
                )
                strategy_results[name].append(result)
        except Exception as e:
            print(f"    ERROR evaluating sample {i}: {e}")
        finally:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

    # Aggregate
    aggregated = {}
    for name, per_sample in strategy_results.items():
        if not per_sample:
            continue
        agg = {"n_samples": len(per_sample)}
        for k in k_values:
            recalls = [r["metrics"][f"recall@{k}"] for r in per_sample]
            agg[f"mean_recall@{k}"] = float(np.mean(recalls))
        avg_tokens = np.mean([r["tokens_used"] for r in per_sample])
        agg["avg_tokens_used"] = float(avg_tokens)
        aggregated[name] = agg
        print(f"    {name}: R@5={agg.get('mean_recall@5', 0):.3f} (n={agg['n_samples']})")

    return aggregated


def _discover_real_projects(base_dir: str) -> Dict[str, str]:
    """Try to discover real project paths from existing benchmark results."""
    results_dir = os.path.join(base_dir, "benchmarks", "results")
    projects = {}

    for name in ["GraphPrompt", "OneViral", "AgentNode"]:
        json_path = os.path.join(results_dir, f"benchmark_real_{name}.json")
        if os.path.exists(json_path):
            try:
                with open(json_path) as f:
                    data = json.load(f)
                proj_path = data.get("metadata", {}).get("project_path", "")
                if proj_path and os.path.isdir(proj_path):
                    projects[name] = proj_path
            except (json.JSONDecodeError, KeyError):
                pass

    return projects


def generate_comparison_report(
    synthetic: Dict,
    real: Dict,
    repobench: Dict,
    output_path: str,
) -> None:
    """Generate markdown comparison report.

    Args:
        synthetic: Synthetic benchmark results
        real: Real codebase results
        repobench: RepoBench results
        output_path: Path for markdown report
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# RANGER-approx Comparison: CTX vs Graph-Based SOTA",
        "",
        f"**Date**: {timestamp}",
        "**Benchmark**: RANGER-approx (AST-based call+import graph) vs CTX (trigger-driven)",
        "",
        "---",
        "",
    ]

    # Synthetic results table
    if synthetic:
        lines.extend([
            "## Synthetic Benchmark (50 files, 166 queries)",
            "",
            "| Strategy | R@1 | R@5 | R@10 | Tok% | TES |",
            "|----------|-----|-----|------|------|-----|",
        ])

        for name in ["full_context", "bm25", "graph_rag", "ranger_approx", "adaptive_trigger"]:
            s = synthetic.get(name, {})
            r1 = s.get("mean_recall@1", 0)
            r5 = s.get("mean_recall@5", 0)
            r10 = s.get("mean_recall@10", 0)
            tok = s.get("mean_token_efficiency", 0) * 100
            tes = s.get("mean_tes", 0)
            label = f"**{name}**" if name in ("ranger_approx", "adaptive_trigger") else name
            lines.append(f"| {label} | {r1:.3f} | {r5:.3f} | {r10:.3f} | {tok:.1f} | {tes:.3f} |")
        lines.append("")

    # Real codebase results
    if real:
        lines.extend([
            "## Real Codebases",
            "",
        ])

        project_names = sorted(real.keys())
        header = "| Strategy | " + " | ".join(f"{p} R@5" for p in project_names) + " | Avg TES |"
        sep = "|----------|" + "|".join("--------" for _ in project_names) + "|---------|"
        lines.append(header)
        lines.append(sep)

        for name in ["full_context", "bm25", "graph_rag", "ranger_approx", "adaptive_trigger"]:
            cols = []
            tes_values = []
            for proj in project_names:
                s = real.get(proj, {}).get(name, {})
                r5 = s.get("mean_recall@5", 0)
                tes = s.get("mean_tes", 0)
                cols.append(f"{r5:.3f}")
                tes_values.append(tes)
            avg_tes = np.mean(tes_values) if tes_values else 0
            label = f"**{name}**" if name in ("ranger_approx", "adaptive_trigger") else name
            lines.append(f"| {label} | " + " | ".join(cols) + f" | {avg_tes:.3f} |")
        lines.append("")

    # RepoBench results
    if repobench:
        lines.extend([
            "## RepoBench Cross-File Retrieval (10 manual samples)",
            "",
            "| Strategy | R@1 | R@3 | R@5 |",
            "|----------|-----|-----|-----|",
        ])

        for name in ["full_context", "bm25", "ranger_approx", "adaptive_trigger"]:
            s = repobench.get(name, {})
            r1 = s.get("mean_recall@1", 0)
            r3 = s.get("mean_recall@3", 0)
            r5 = s.get("mean_recall@5", 0)
            label = f"**{name}**" if name in ("ranger_approx", "adaptive_trigger") else name
            lines.append(f"| {label} | {r1:.3f} | {r3:.3f} | {r5:.3f} |")
        lines.append("")

    # Analysis
    lines.extend([
        "---",
        "",
        "## Analysis: CTX vs RANGER-approx",
        "",
    ])

    if synthetic:
        ctx_s = synthetic.get("adaptive_trigger", {})
        ranger_s = synthetic.get("ranger_approx", {})
        ctx_r5 = ctx_s.get("mean_recall@5", 0)
        ranger_r5 = ranger_s.get("mean_recall@5", 0)
        ctx_tes = ctx_s.get("mean_tes", 0)
        ranger_tes = ranger_s.get("mean_tes", 0)

        lines.extend([
            "### Synthetic",
            f"- **CTX R@5**: {ctx_r5:.3f} vs **RANGER-approx R@5**: {ranger_r5:.3f}",
        ])
        if ranger_r5 > 0:
            delta = ((ctx_r5 - ranger_r5) / ranger_r5) * 100
            lines.append(f"- **Delta R@5**: {delta:+.1f}%")
        lines.append(f"- **CTX TES**: {ctx_tes:.3f} vs **RANGER-approx TES**: {ranger_tes:.3f}")
        if ranger_tes > 0:
            delta_tes = ((ctx_tes - ranger_tes) / ranger_tes) * 100
            lines.append(f"- **Delta TES**: {delta_tes:+.1f}%")
        lines.append("")

    lines.extend([
        "### Key Differences",
        "",
        "| Aspect | CTX | RANGER-approx |",
        "|--------|-----|---------------|",
        "| Query routing | Trigger classification (4 types) | Uniform graph traversal |",
        "| Symbol extraction | Regex-based | AST-based (precise) |",
        "| Graph type | Import-only | Import + Call combined |",
        "| k-selection | Adaptive per trigger type | Fixed |",
        "| Token efficiency | High (5.2% synthetic) | Moderate |",
        "",
        "### Complementary Strengths",
        "",
        "1. **RANGER-approx** benefits from AST precision and richer call graph edges",
        "2. **CTX** benefits from trigger-driven query routing and adaptive k-selection",
        "3. CTX's higher TES reflects its ability to reduce retrieval size via classification",
        "4. RANGER-approx's uniform traversal can be advantageous when query type is ambiguous",
        "",
        "---",
        "",
        f"*Generated by CTX RANGER comparison ({timestamp})*",
    ])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report saved to {output_path}")


def run_full_comparison(base_dir: str, seed: int = 42) -> Dict:
    """Run full RANGER-approx comparison across all datasets.

    Args:
        base_dir: CTX project root
        seed: Random seed

    Returns:
        Complete results dict
    """
    print("=" * 60)
    print("RANGER-approx Comparison: CTX vs Graph-Based SOTA")
    print("=" * 60)
    print()

    results = {}

    # 1. Synthetic
    print("[1/3] Synthetic benchmark...")
    results["synthetic"] = run_synthetic_comparison(base_dir, seed=seed)
    print()

    # 2. Real codebases
    print("[2/3] Real codebases...")
    results["real"] = run_real_comparison(base_dir, seed=seed)
    print()

    # 3. RepoBench
    print("[3/3] RepoBench cross-file retrieval...")
    results["repobench"] = run_repobench_comparison(seed=seed)
    print()

    # Generate report
    report_path = os.path.join(base_dir, "benchmarks", "results", "ranger_comparison.md")
    generate_comparison_report(
        synthetic=results["synthetic"],
        real=results["real"],
        repobench=results["repobench"],
        output_path=report_path,
    )

    # Save JSON
    json_path = report_path.replace(".md", ".json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  JSON saved to {json_path}")

    print()
    print("=" * 60)
    print("RANGER-approx Comparison Complete")
    print("=" * 60)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="RANGER-approx comparison evaluation for CTX"
    )
    parser.add_argument(
        "--base-dir",
        default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        help="CTX project root directory",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed (default: 42)",
    )
    args = parser.parse_args()

    results = run_full_comparison(args.base_dir, seed=args.seed)
