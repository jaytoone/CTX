#!/usr/bin/env python3
"""
CTX LLM Quality Evaluation v2 -- Incremental pass@1 with 50 samples.

Reuses existing 15-sample results and adds 35 new samples.
Computes McNemar test for statistical significance.

Usage:
    source ~/.claude/env/shared.env
    python3 run_llm_eval_v2.py \
        --project-path /home/jayone/Project/GraphPrompt \
        --n-samples 50 \
        --existing-results benchmarks/results/llm_quality_results.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.evaluator.llm_quality import (
    LLMQualityEvaluator,
    sample_functions,
    build_full_context,
    build_adaptive_context,
    estimate_tokens,
)


def compute_mcnemar(results_per_sample: list) -> dict:
    """Compute McNemar test comparing Full Context vs Adaptive Trigger.

    Args:
        results_per_sample: List of per-sample result dicts

    Returns:
        Dict with contingency table and p-value
    """
    # Build 2x2 contingency table
    # a = both pass, b = FC pass + AT fail, c = FC fail + AT pass, d = both fail
    a, b, c, d = 0, 0, 0, 0

    for s in results_per_sample:
        fc = s["strategies"].get("full_context", {}).get("passed", False)
        at = s["strategies"].get("adaptive_trigger", {}).get("passed", False)

        if fc and at:
            a += 1
        elif fc and not at:
            b += 1
        elif not fc and at:
            c += 1
        else:
            d += 1

    # McNemar test (with continuity correction)
    if b + c == 0:
        p_value = 1.0
    else:
        chi2 = (abs(b - c) - 1) ** 2 / (b + c) if (b + c) > 0 else 0
        p_value = 1.0 - stats.chi2.cdf(chi2, df=1)

    return {
        "contingency": {"both_pass": a, "fc_only": b, "at_only": c, "both_fail": d},
        "chi2": chi2 if b + c > 0 else 0,
        "p_value": p_value,
        "n": len(results_per_sample),
    }


def compute_confidence_interval(passed: int, total: int, confidence: float = 0.95) -> tuple:
    """Compute Wilson score confidence interval for a proportion.

    Args:
        passed: Number of successes
        total: Total trials
        confidence: Confidence level

    Returns:
        Tuple of (lower, upper) bounds
    """
    if total == 0:
        return (0.0, 0.0)

    p = passed / total
    z = stats.norm.ppf(1 - (1 - confidence) / 2)

    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    spread = z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return (lower, upper)


def run_incremental_experiment(
    project_path: str,
    n_samples: int = 50,
    existing_results_path: str = None,
    results_dir: str = "benchmarks/results",
    seed: int = 42,
) -> dict:
    """Run incremental LLM quality evaluation.

    Reuses existing results and only runs new samples.

    Args:
        project_path: Path to Python project
        n_samples: Total desired samples
        existing_results_path: Path to existing results JSON
        results_dir: Output directory
        seed: Random seed

    Returns:
        Results dictionary
    """
    os.makedirs(results_dir, exist_ok=True)
    results_path = os.path.join(results_dir, "llm_quality_results_v2.json")
    project_name = os.path.basename(project_path)

    # Load existing results
    existing_per_sample = []
    existing_func_names = set()
    if existing_results_path and os.path.exists(existing_results_path):
        with open(existing_results_path) as f:
            existing = json.load(f)
        existing_per_sample = existing.get("per_sample", [])
        existing_func_names = {s["function_name"] for s in existing_per_sample}
        print(f"[Incremental Mode] Loaded {len(existing_per_sample)} existing results")
        print(f"  Existing functions: {', '.join(sorted(existing_func_names))}")
    else:
        print("[Fresh Mode] No existing results found, running from scratch")

    n_existing = len(existing_per_sample)
    n_new = n_samples - n_existing

    if n_new <= 0:
        print(f"  Already have {n_existing} >= {n_samples} samples. Nothing to do.")
        # Still recompute stats
        n_new = 0

    print(f"\n[CTX LLM Quality Eval v2]")
    print(f"  Model: {os.environ.get('MINIMAX_MODEL', 'MiniMax-M2.5')}")
    print(f"  Project: {project_name} ({project_path})")
    print(f"  Total samples: {n_samples} ({n_existing} existing + {n_new} new)")
    print()

    # Sample more functions (use same seed but request more)
    all_functions = sample_functions(project_path, n=n_samples, seed=seed)
    print(f"  Total available functions: {len(all_functions)}")

    # Filter out already-evaluated functions
    new_functions = [f for f in all_functions if f.name not in existing_func_names]
    new_functions = new_functions[:n_new]

    print(f"  New functions to evaluate: {len(new_functions)}")
    for i, func in enumerate(new_functions):
        doc_preview = func.docstring[:60] + "..." if len(func.docstring) > 60 else func.docstring
        print(f"    {n_existing + i + 1}. {func.name} ({func.file_path}) - {doc_preview or '(no docstring)'}")
    print()

    # Build full context
    print("Building full context...")
    full_context = build_full_context(project_path, max_tokens=4000)
    full_ctx_tokens = estimate_tokens(full_context)
    print(f"  Full context: {full_ctx_tokens} tokens")
    print()

    # Initialize evaluator
    evaluator = LLMQualityEvaluator(max_retries=1) if n_new > 0 else None

    # Combine existing + new results
    all_per_sample = list(existing_per_sample)  # copy existing

    # Run new evaluations
    if n_new > 0 and evaluator:
        print(f"Running {len(new_functions)} new evaluations...")
        for i, func in enumerate(new_functions):
            idx = n_existing + i
            print(f"\n  [{idx + 1}/{n_samples}] {func.name} ({func.file_path})")

            task_prompt = f"Implement function '{func.name}'"
            if func.docstring:
                task_prompt += f" with this specification: {func.docstring}"
            task_prompt += f"\n\nFunction signature: {func.signature}"

            sample_result = {
                "index": idx,
                "function_name": func.name,
                "file_path": func.file_path,
                "docstring": func.docstring[:200] if func.docstring else "",
                "reference_lines": len(func.body.splitlines()),
                "strategies": {},
            }

            # Strategy 1: Full Context
            print("    Full Context: ", end="", flush=True)
            try:
                generated_full = evaluator.generate_code(task_prompt, full_context)
                passed_full, eval_resp_full = evaluator.evaluate_pass(
                    generated_full, func.full_source, task_prompt
                )
                sample_result["strategies"]["full_context"] = {
                    "passed": passed_full,
                    "context_tokens": full_ctx_tokens,
                    "generated_preview": generated_full[:300],
                    "eval_response": eval_resp_full[:100],
                    "error": None,
                }
                print(f"{'PASS' if passed_full else 'FAIL'}")
            except Exception as e:
                sample_result["strategies"]["full_context"] = {
                    "passed": False,
                    "context_tokens": full_ctx_tokens,
                    "error": str(e),
                }
                print(f"ERROR: {e}")

            # Strategy 2: Adaptive Trigger
            print("    Adaptive Trigger: ", end="", flush=True)
            try:
                adaptive_ctx = build_adaptive_context(project_path, func, max_tokens=2000)
                adaptive_tokens = estimate_tokens(adaptive_ctx)

                generated_adaptive = evaluator.generate_code(task_prompt, adaptive_ctx)
                passed_adaptive, eval_resp_adaptive = evaluator.evaluate_pass(
                    generated_adaptive, func.full_source, task_prompt
                )
                sample_result["strategies"]["adaptive_trigger"] = {
                    "passed": passed_adaptive,
                    "context_tokens": adaptive_tokens,
                    "generated_preview": generated_adaptive[:300],
                    "eval_response": eval_resp_adaptive[:100],
                    "error": None,
                }
                print(f"{'PASS' if passed_adaptive else 'FAIL'} (ctx: {adaptive_tokens} tokens)")
            except Exception as e:
                sample_result["strategies"]["adaptive_trigger"] = {
                    "passed": False,
                    "error": str(e),
                }
                print(f"ERROR: {e}")

            all_per_sample.append(sample_result)

            # Save intermediate results
            _save_intermediate(all_per_sample, full_ctx_tokens, project_name,
                               project_path, seed, results_path)

            time.sleep(0.5)

    # Compute final metrics
    print(f"\n{'='*60}")
    print("Computing final metrics...")

    total_n = len(all_per_sample)

    fc_passed = sum(
        1 for s in all_per_sample
        if s["strategies"].get("full_context", {}).get("passed", False)
    )
    fc_errors = sum(
        1 for s in all_per_sample
        if s["strategies"].get("full_context", {}).get("error") is not None
        and s["strategies"]["full_context"]["error"] is not None
        and not s["strategies"]["full_context"].get("passed", False)
    )
    at_passed = sum(
        1 for s in all_per_sample
        if s["strategies"].get("adaptive_trigger", {}).get("passed", False)
    )
    at_errors = sum(
        1 for s in all_per_sample
        if s["strategies"].get("adaptive_trigger", {}).get("error") is not None
        and s["strategies"]["adaptive_trigger"]["error"] is not None
        and not s["strategies"]["adaptive_trigger"].get("passed", False)
    )

    fc_pass1 = fc_passed / total_n if total_n > 0 else 0.0
    at_pass1 = at_passed / total_n if total_n > 0 else 0.0

    fc_ci = compute_confidence_interval(fc_passed, total_n)
    at_ci = compute_confidence_interval(at_passed, total_n)

    if fc_pass1 > 0:
        improvement_pct = ((at_pass1 - fc_pass1) / fc_pass1) * 100
    else:
        improvement_pct = float("inf") if at_pass1 > 0 else 0.0

    # McNemar test
    mcnemar = compute_mcnemar(all_per_sample)

    # Average context tokens
    fc_tokens_list = [
        s["strategies"].get("full_context", {}).get("context_tokens", 0)
        for s in all_per_sample
        if s["strategies"].get("full_context", {}).get("context_tokens") is not None
    ]
    at_tokens_list = [
        s["strategies"].get("adaptive_trigger", {}).get("context_tokens", 0)
        for s in all_per_sample
        if s["strategies"].get("adaptive_trigger", {}).get("context_tokens") is not None
    ]

    results = {
        "model": os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
        "n_samples": total_n,
        "n_existing": n_existing,
        "n_new": len(all_per_sample) - n_existing,
        "project": project_name,
        "project_path": project_path,
        "seed": seed,
        "timestamp": datetime.now().isoformat(),
        "full_context_tokens": full_ctx_tokens,
        "strategies": {
            "full_context": {
                "passed": fc_passed,
                "total": total_n,
                "errors": fc_errors,
                "pass_at_1": fc_pass1,
                "ci_95": list(fc_ci),
                "avg_context_tokens": sum(fc_tokens_list) / len(fc_tokens_list) if fc_tokens_list else 0,
            },
            "adaptive_trigger": {
                "passed": at_passed,
                "total": total_n,
                "errors": at_errors,
                "pass_at_1": at_pass1,
                "ci_95": list(at_ci),
                "avg_context_tokens": sum(at_tokens_list) / len(at_tokens_list) if at_tokens_list else 0,
            },
        },
        "improvement_pct": improvement_pct,
        "mcnemar_test": mcnemar,
        "per_sample": all_per_sample,
    }

    # Save final results
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  Results saved to {results_path}")

    # Generate report
    _generate_report_v2(results, results_dir)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Full Context:      {fc_passed}/{total_n} = {fc_pass1:.3f} pass@1  95% CI [{fc_ci[0]:.3f}, {fc_ci[1]:.3f}]")
    print(f"  Adaptive Trigger:  {at_passed}/{total_n} = {at_pass1:.3f} pass@1  95% CI [{at_ci[0]:.3f}, {at_ci[1]:.3f}]")
    print(f"  Improvement:       {improvement_pct:+.1f}%")
    print(f"  McNemar p-value:   {mcnemar['p_value']:.4f}")
    print(f"  Contingency:       both_pass={mcnemar['contingency']['both_pass']}, "
          f"fc_only={mcnemar['contingency']['fc_only']}, "
          f"at_only={mcnemar['contingency']['at_only']}, "
          f"both_fail={mcnemar['contingency']['both_fail']}")
    print(f"{'='*60}")

    return results


def _save_intermediate(per_sample, full_ctx_tokens, project_name, project_path, seed, path):
    """Save intermediate results after each sample."""
    intermediate = {
        "model": os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
        "n_samples": len(per_sample),
        "project": project_name,
        "project_path": project_path,
        "seed": seed,
        "timestamp": datetime.now().isoformat(),
        "full_context_tokens": full_ctx_tokens,
        "per_sample": per_sample,
    }
    with open(path, "w") as f:
        json.dump(intermediate, f, indent=2, ensure_ascii=False)


def _generate_report_v2(results: dict, results_dir: str) -> None:
    """Generate a markdown report with 95% CI and McNemar test."""
    report_path = os.path.join(results_dir, "llm_quality_report_v2.md")

    fc = results["strategies"]["full_context"]
    at = results["strategies"]["adaptive_trigger"]
    mc = results["mcnemar_test"]

    lines = [
        "# CTX LLM Downstream Quality Report v2 (pass@1, 50 samples)",
        "",
        f"**Date**: {results['timestamp']}",
        f"**Model**: {results['model']}",
        f"**Project**: {results['project']}",
        f"**Total Samples**: {results['n_samples']} ({results['n_existing']} reused + {results['n_new']} new)",
        f"**Seed**: {results['seed']}",
        "",
        "---",
        "",
        "## Results Summary",
        "",
        "| Strategy | pass@1 | 95% CI | Passed | Total | Errors | Avg Context Tokens |",
        "|----------|--------|--------|--------|-------|--------|--------------------|",
        f"| Full Context | {fc['pass_at_1']:.3f} | [{fc['ci_95'][0]:.3f}, {fc['ci_95'][1]:.3f}] | {fc['passed']} | {fc['total']} | {fc['errors']} | {fc['avg_context_tokens']:.0f} |",
        f"| Adaptive Trigger | {at['pass_at_1']:.3f} | [{at['ci_95'][0]:.3f}, {at['ci_95'][1]:.3f}] | {at['passed']} | {at['total']} | {at['errors']} | {at['avg_context_tokens']:.0f} |",
        "",
        f"**Improvement**: {results['improvement_pct']:+.1f}% (Adaptive Trigger vs Full Context)",
        "",
        "---",
        "",
        "## Statistical Significance (McNemar Test)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Chi-squared | {mc['chi2']:.4f} |",
        f"| p-value | {mc['p_value']:.4f} |",
        f"| Significant (p<0.05)? | {'Yes' if mc['p_value'] < 0.05 else 'No'} |",
        f"| Both Pass | {mc['contingency']['both_pass']} |",
        f"| FC Only Pass | {mc['contingency']['fc_only']} |",
        f"| AT Only Pass | {mc['contingency']['at_only']} |",
        f"| Both Fail | {mc['contingency']['both_fail']} |",
        "",
        "---",
        "",
        "## Per-Sample Results",
        "",
        "| # | Function | File | Full Context | Adaptive Trigger |",
        "|---|----------|------|-------------|-----------------|",
    ]

    for s in results["per_sample"]:
        fc_result = s["strategies"].get("full_context", {})
        at_result = s["strategies"].get("adaptive_trigger", {})

        fc_str = "PASS" if fc_result.get("passed") else ("ERROR" if fc_result.get("error") else "FAIL")
        at_str = "PASS" if at_result.get("passed") else ("ERROR" if at_result.get("error") else "FAIL")

        lines.append(
            f"| {s['index']+1} | `{s['function_name']}` | {s['file_path']} | {fc_str} | {at_str} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Context Token Comparison",
        "",
        f"Full Context uses a fixed context window of ~{results.get('full_context_tokens', 'N/A')} tokens for all queries.",
        f"Adaptive Trigger uses variable context, averaging ~{at['avg_context_tokens']:.0f} tokens per query.",
        f"Token reduction: {(1 - at['avg_context_tokens'] / fc['avg_context_tokens']) * 100:.1f}% fewer tokens." if fc['avg_context_tokens'] > 0 else "",
        "",
        "---",
        "",
        f"*Generated by CTX LLM Quality Evaluation v2 ({results['timestamp']})*",
    ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="CTX LLM Quality Evaluation v2 (incremental, with McNemar test)"
    )
    parser.add_argument(
        "--project-path",
        required=True,
        help="Path to the Python project to evaluate",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=50,
        help="Total number of functions to evaluate (default: 50)",
    )
    parser.add_argument(
        "--existing-results",
        default="benchmarks/results/llm_quality_results.json",
        help="Path to existing results JSON to reuse",
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
        help="Directory to save results (default: benchmarks/results)",
    )
    args = parser.parse_args()

    # Validate environment
    required_vars = ["MINIMAX_API_KEY", "MINIMAX_BASE_URL"]
    missing = [v for v in required_vars if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Run: source ~/.claude/env/shared.env")
        sys.exit(1)

    if not os.path.isdir(args.project_path):
        print(f"ERROR: Project path not found: {args.project_path}")
        sys.exit(1)

    start_time = time.time()
    results = run_incremental_experiment(
        project_path=args.project_path,
        n_samples=args.n_samples,
        existing_results_path=args.existing_results,
        results_dir=args.results_dir,
        seed=args.seed,
    )
    elapsed = time.time() - start_time

    print(f"\nTotal time: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
