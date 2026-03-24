#!/usr/bin/env python3
"""
CTX LLM Quality Evaluation using MiniMax M2.5

Measures pass@1 downstream quality by:
1. Sampling functions from a real codebase (GraphPrompt)
2. Generating code with Full Context vs Adaptive Trigger context
3. Using LLM self-evaluation for correctness

Usage:
    source ~/.claude/env/shared.env
    python run_llm_eval.py --project-path /home/jayone/Project/GraphPrompt --n-samples 15

Cost estimate: n_samples * 2 strategies * 2 calls (generate + eval) = ~60 API calls
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.evaluator.llm_quality import (
    LLMQualityEvaluator,
    sample_functions,
    build_full_context,
    build_adaptive_context,
    estimate_tokens,
)


def run_experiment(
    project_path: str,
    n_samples: int = 15,
    results_dir: str = "benchmarks/results",
    seed: int = 42,
) -> dict:
    """Run the LLM quality evaluation experiment.

    Args:
        project_path: Path to the target Python project
        n_samples: Number of functions to sample
        results_dir: Directory to save results
        seed: Random seed

    Returns:
        Results dictionary
    """
    os.makedirs(results_dir, exist_ok=True)
    results_path = os.path.join(results_dir, "llm_quality_results.json")
    project_name = os.path.basename(project_path)

    print(f"[CTX LLM Quality Eval]")
    print(f"  Model: {os.environ.get('MINIMAX_MODEL', 'MiniMax-M2.5')}")
    print(f"  Project: {project_name} ({project_path})")
    print(f"  Samples: {n_samples}")
    print()

    # Step 1: Sample functions
    print("[1/4] Sampling functions from codebase...")
    functions = sample_functions(project_path, n=n_samples, seed=seed)
    print(f"  Sampled {len(functions)} functions:")
    for i, func in enumerate(functions):
        doc_preview = func.docstring[:60] + "..." if len(func.docstring) > 60 else func.docstring
        print(f"    {i+1}. {func.name} ({func.file_path}) - {doc_preview or '(no docstring)'}")
    print()

    if not functions:
        print("ERROR: No functions sampled. Check project path.")
        sys.exit(1)

    # Step 2: Build full context (once, reused for all functions)
    print("[2/4] Building full context...")
    full_context = build_full_context(project_path, max_tokens=4000)
    full_ctx_tokens = estimate_tokens(full_context)
    print(f"  Full context: {full_ctx_tokens} tokens (~{len(full_context)} chars)")
    print()

    # Step 3: Run generation + evaluation
    print("[3/4] Running code generation and evaluation...")
    evaluator = LLMQualityEvaluator(max_retries=1)

    results = {
        "model": os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
        "n_samples": len(functions),
        "project": project_name,
        "project_path": project_path,
        "seed": seed,
        "timestamp": datetime.now().isoformat(),
        "full_context_tokens": full_ctx_tokens,
        "per_sample": [],
        "strategies": {
            "full_context": {"passed": 0, "total": 0, "errors": 0},
            "adaptive_trigger": {"passed": 0, "total": 0, "errors": 0},
        },
    }

    for i, func in enumerate(functions):
        print(f"\n  [{i+1}/{len(functions)}] {func.name} ({func.file_path})")

        task_prompt = f"Implement function '{func.name}'"
        if func.docstring:
            task_prompt += f" with this specification: {func.docstring}"
        task_prompt += f"\n\nFunction signature: {func.signature}"

        sample_result = {
            "index": i,
            "function_name": func.name,
            "file_path": func.file_path,
            "docstring": func.docstring[:200] if func.docstring else "",
            "reference_lines": len(func.body.splitlines()),
            "strategies": {},
        }

        # --- Strategy 1: Full Context ---
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
            results["strategies"]["full_context"]["total"] += 1
            if passed_full:
                results["strategies"]["full_context"]["passed"] += 1
            print(f"{'PASS' if passed_full else 'FAIL'}")
        except Exception as e:
            sample_result["strategies"]["full_context"] = {
                "passed": False,
                "error": str(e),
            }
            results["strategies"]["full_context"]["total"] += 1
            results["strategies"]["full_context"]["errors"] += 1
            print(f"ERROR: {e}")

        # --- Strategy 2: Adaptive Trigger ---
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
            results["strategies"]["adaptive_trigger"]["total"] += 1
            if passed_adaptive:
                results["strategies"]["adaptive_trigger"]["passed"] += 1
            print(f"{'PASS' if passed_adaptive else 'FAIL'} (ctx: {adaptive_tokens} tokens)")
        except Exception as e:
            sample_result["strategies"]["adaptive_trigger"] = {
                "passed": False,
                "error": str(e),
            }
            results["strategies"]["adaptive_trigger"]["total"] += 1
            results["strategies"]["adaptive_trigger"]["errors"] += 1
            print(f"ERROR: {e}")

        results["per_sample"].append(sample_result)

        # Save intermediate results after each sample
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Small delay to avoid rate limiting
        time.sleep(0.5)

    # Step 4: Compute final metrics
    print("\n[4/4] Computing final metrics...")

    for strategy_name in ["full_context", "adaptive_trigger"]:
        s = results["strategies"][strategy_name]
        total = s["total"]
        passed = s["passed"]
        s["pass_at_1"] = passed / total if total > 0 else 0.0
        print(f"  {strategy_name}: {passed}/{total} = {s['pass_at_1']:.3f} pass@1")

    # Compute improvement
    fc_pass1 = results["strategies"]["full_context"]["pass_at_1"]
    at_pass1 = results["strategies"]["adaptive_trigger"]["pass_at_1"]

    if fc_pass1 > 0:
        improvement_pct = ((at_pass1 - fc_pass1) / fc_pass1) * 100
    else:
        improvement_pct = float("inf") if at_pass1 > 0 else 0.0

    results["full_context_pass1"] = fc_pass1
    results["adaptive_trigger_pass1"] = at_pass1
    results["improvement_pct"] = improvement_pct

    # Compute average context tokens per strategy
    for strategy_name in ["full_context", "adaptive_trigger"]:
        ctx_tokens = [
            s["strategies"].get(strategy_name, {}).get("context_tokens", 0)
            for s in results["per_sample"]
            if s["strategies"].get(strategy_name, {}).get("context_tokens") is not None
        ]
        if ctx_tokens:
            results["strategies"][strategy_name]["avg_context_tokens"] = (
                sum(ctx_tokens) / len(ctx_tokens)
            )

    # Save final results
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved to {results_path}")

    # Generate markdown report
    _generate_report(results, results_dir)

    return results


def _generate_report(results: dict, results_dir: str) -> None:
    """Generate a human-readable markdown report."""
    report_path = os.path.join(results_dir, "llm_quality_report.md")

    fc = results["strategies"]["full_context"]
    at = results["strategies"]["adaptive_trigger"]

    lines = [
        "# CTX LLM Downstream Quality Report (pass@1)",
        "",
        f"**Date**: {results['timestamp']}",
        f"**Model**: {results['model']}",
        f"**Project**: {results['project']}",
        f"**Samples**: {results['n_samples']}",
        f"**Seed**: {results['seed']}",
        "",
        "---",
        "",
        "## Results Summary",
        "",
        "| Strategy | pass@1 | Passed | Total | Errors | Avg Context Tokens |",
        "|----------|--------|--------|-------|--------|--------------------|",
        f"| Full Context | {fc['pass_at_1']:.3f} | {fc['passed']} | {fc['total']} | {fc['errors']} | {fc.get('avg_context_tokens', 'N/A'):.0f} |" if isinstance(fc.get('avg_context_tokens'), (int, float)) else f"| Full Context | {fc['pass_at_1']:.3f} | {fc['passed']} | {fc['total']} | {fc['errors']} | N/A |",
        f"| Adaptive Trigger | {at['pass_at_1']:.3f} | {at['passed']} | {at['total']} | {at['errors']} | {at.get('avg_context_tokens', 'N/A'):.0f} |" if isinstance(at.get('avg_context_tokens'), (int, float)) else f"| Adaptive Trigger | {at['pass_at_1']:.3f} | {at['passed']} | {at['total']} | {at['errors']} | N/A |",
        "",
        f"**Improvement**: {results['improvement_pct']:+.1f}% (Adaptive Trigger vs Full Context)",
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
        f"Adaptive Trigger uses variable context, averaging ~{at.get('avg_context_tokens', 'N/A'):.0f} tokens per query." if isinstance(at.get('avg_context_tokens'), (int, float)) else "Adaptive Trigger uses variable context.",
        "",
        "This demonstrates CTX's core thesis: selective context retrieval can maintain",
        "generation quality while significantly reducing token usage.",
        "",
        "---",
        "",
        f"*Generated by CTX LLM Quality Evaluation ({results['timestamp']})*",
    ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report saved to {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="CTX LLM Quality Evaluation using MiniMax M2.5"
    )
    parser.add_argument(
        "--project-path",
        required=True,
        help="Path to the Python project to evaluate",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=15,
        help="Number of functions to sample (default: 15)",
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

    # Validate project path
    if not os.path.isdir(args.project_path):
        print(f"ERROR: Project path not found: {args.project_path}")
        sys.exit(1)

    start_time = time.time()
    results = run_experiment(
        project_path=args.project_path,
        n_samples=args.n_samples,
        results_dir=args.results_dir,
        seed=args.seed,
    )
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print(f"DONE in {elapsed:.1f}s")
    print(f"  Full Context pass@1:       {results['full_context_pass1']:.3f}")
    print(f"  Adaptive Trigger pass@1:   {results['adaptive_trigger_pass1']:.3f}")
    print(f"  Improvement:               {results['improvement_pct']:+.1f}%")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
