#!/usr/bin/env python3
"""pass@1 evaluation via OpenRouter API -- large LLM (reproducible).

Model: google/gemini-flash-1.5 (128K context window)
Fallback: meta-llama/llama-3.1-8b-instruct
Base URL: https://openrouter.ai/api/v1
n=30 samples (GraphPrompt codebase)
Compare: Full Context vs CTX Adaptive Trigger
Save: benchmarks/results/llm_quality_openrouter.md

Usage:
    source ~/.claude/env/shared.env
    python3 run_llm_eval_openrouter.py \\
        --project-path /home/jayone/Project/GraphPrompt \\
        --n-samples 30
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime

import numpy as np
from openai import OpenAI
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.evaluator.llm_quality import (
    sample_functions,
    build_full_context,
    build_adaptive_context,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# OpenRouter-based evaluator
# ---------------------------------------------------------------------------

class OpenRouterEvaluator:
    """Evaluates code generation quality using OpenRouter API."""

    PRIMARY_MODEL = "google/gemini-flash-1.5"
    FALLBACK_MODEL = "meta-llama/llama-3.1-8b-instruct"

    def __init__(self, model: str = None, max_retries: int = 2, timeout: int = 30):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENROUTER_API_KEY environment variable not set")

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=timeout,
        )
        self.model = model or self.PRIMARY_MODEL
        self.max_retries = max_retries
        self.timeout = timeout

    def _call(self, messages: list, max_tokens: int = 800) -> str:
        """Make a chat completion call with retry + model fallback."""
        models_to_try = [self.model]
        if self.model != self.FALLBACK_MODEL:
            models_to_try.append(self.FALLBACK_MODEL)

        last_err = None
        for model in models_to_try:
            for attempt in range(1 + self.max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=0.0,
                        extra_headers={
                            "HTTP-Referer": "https://github.com/CTX-eval",
                            "X-Title": "CTX pass@1 evaluation",
                        },
                    )
                    return response.choices[0].message.content or ""
                except Exception as e:
                    last_err = e
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)  # exponential backoff
                    continue
            # model exhausted, try fallback
        raise RuntimeError(f"All models failed. Last error: {last_err}")

    def generate_code(self, task_prompt: str, context: str) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Python code completion assistant. "
                    "Generate only the function implementation (the def line "
                    "and body). Do not include explanations, markdown, or "
                    "anything other than Python code."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Here is the codebase context:\n\n{context}\n\n"
                    f"---\n\nTask: {task_prompt}\n\n"
                    f"Generate the Python function:"
                ),
            },
        ]
        return self._call(messages, max_tokens=800)

    def evaluate_pass(self, generated: str, reference: str, task_desc: str):
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a code correctness evaluator. Compare the "
                    "generated code against the reference implementation. "
                    "Judge whether the generated code correctly implements "
                    "the core logic described in the task. Minor style "
                    "differences (variable names, comments, import order) "
                    "are acceptable. Answer only YES or NO."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task: {task_desc}\n\n"
                    f"--- Generated Code ---\n{generated}\n\n"
                    f"--- Reference Code ---\n{reference}\n\n"
                    f"Does the generated code correctly implement the task? "
                    f"(YES/NO)"
                ),
            },
        ]
        try:
            raw = self._call(messages, max_tokens=20)
            passed = "YES" in raw.upper()
            return passed, raw
        except Exception as e:
            return False, f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Statistics helpers (same as v2)
# ---------------------------------------------------------------------------

def compute_mcnemar(results_per_sample: list) -> dict:
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

    if b + c == 0:
        chi2, p_value = 0.0, 1.0
    else:
        chi2 = (abs(b - c) - 1) ** 2 / (b + c)
        p_value = 1.0 - stats.chi2.cdf(chi2, df=1)

    return {
        "contingency": {"both_pass": a, "fc_only": b, "at_only": c, "both_fail": d},
        "chi2": chi2,
        "p_value": float(p_value),
        "n": len(results_per_sample),
    }


def compute_confidence_interval(passed: int, total: int, confidence: float = 0.95):
    if total == 0:
        return (0.0, 0.0)
    p = passed / total
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denominator = 1 + z ** 2 / total
    center = (p + z ** 2 / (2 * total)) / denominator
    spread = z * np.sqrt((p * (1 - p) + z ** 2 / (4 * total)) / total) / denominator
    return (max(0.0, center - spread), min(1.0, center + spread))


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def run_openrouter_experiment(
    project_path: str,
    n_samples: int = 30,
    results_dir: str = "benchmarks/results",
    seed: int = 42,
    model: str = None,
) -> dict:
    os.makedirs(results_dir, exist_ok=True)
    json_path = os.path.join(results_dir, "llm_quality_openrouter.json")
    project_name = os.path.basename(project_path)

    evaluator = OpenRouterEvaluator(model=model)
    actual_model = evaluator.model

    print(f"\n[CTX pass@1 Evaluation — OpenRouter]")
    print(f"  Model:   {actual_model}")
    print(f"  Project: {project_name} ({project_path})")
    print(f"  Samples: {n_samples}  Seed: {seed}")
    print()

    # Sample functions
    functions = sample_functions(project_path, n=n_samples, seed=seed)
    print(f"  Sampled {len(functions)} functions from {project_name}")
    for i, f in enumerate(functions):
        preview = (f.docstring[:55] + "...") if len(f.docstring) > 55 else f.docstring
        print(f"    {i+1:2d}. {f.name} — {preview or '(no docstring)'}")
    print()

    # Build full context once
    print("Building full context...")
    full_context = build_full_context(project_path, max_tokens=4000)
    full_ctx_tokens = estimate_tokens(full_context)
    print(f"  Full context: {full_ctx_tokens} tokens\n")

    per_sample = []

    for i, func in enumerate(functions):
        print(f"[{i+1}/{n_samples}] {func.name} ({func.file_path})")
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
        print("  Full Context:    ", end="", flush=True)
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
            print("PASS" if passed_full else "FAIL")
        except Exception as e:
            sample_result["strategies"]["full_context"] = {
                "passed": False,
                "context_tokens": full_ctx_tokens,
                "error": str(e),
            }
            print(f"ERROR: {e}")

        # --- Strategy 2: Adaptive Trigger ---
        print("  Adaptive Trigger:", end="", flush=True)
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
            print(f" {'PASS' if passed_adaptive else 'FAIL'} (ctx: {adaptive_tokens} tokens)")
        except Exception as e:
            sample_result["strategies"]["adaptive_trigger"] = {
                "passed": False,
                "error": str(e),
            }
            print(f" ERROR: {e}")

        per_sample.append(sample_result)

        # Save intermediate after each sample
        with open(json_path, "w") as f:
            json.dump({"model": actual_model, "per_sample": per_sample,
                       "timestamp": datetime.now().isoformat()}, f, indent=2)

        time.sleep(0.3)  # gentle rate-limit buffer

    # ---------------------------------------------------------------------------
    # Aggregate metrics
    # ---------------------------------------------------------------------------
    total_n = len(per_sample)

    fc_passed = sum(1 for s in per_sample if s["strategies"].get("full_context", {}).get("passed", False))
    at_passed = sum(1 for s in per_sample if s["strategies"].get("adaptive_trigger", {}).get("passed", False))
    fc_errors = sum(1 for s in per_sample if s["strategies"].get("full_context", {}).get("error"))
    at_errors = sum(1 for s in per_sample if s["strategies"].get("adaptive_trigger", {}).get("error"))

    fc_pass1 = fc_passed / total_n if total_n > 0 else 0.0
    at_pass1 = at_passed / total_n if total_n > 0 else 0.0
    fc_ci = compute_confidence_interval(fc_passed, total_n)
    at_ci = compute_confidence_interval(at_passed, total_n)
    improvement_pct = ((at_pass1 - fc_pass1) / fc_pass1 * 100) if fc_pass1 > 0 else (float("inf") if at_pass1 > 0 else 0.0)
    mcnemar = compute_mcnemar(per_sample)

    at_tokens_list = [
        s["strategies"].get("adaptive_trigger", {}).get("context_tokens", 0)
        for s in per_sample
        if s["strategies"].get("adaptive_trigger", {}).get("context_tokens") is not None
    ]
    avg_at_tokens = sum(at_tokens_list) / len(at_tokens_list) if at_tokens_list else 0

    results = {
        "model": actual_model,
        "n_samples": total_n,
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
                "avg_context_tokens": full_ctx_tokens,
            },
            "adaptive_trigger": {
                "passed": at_passed,
                "total": total_n,
                "errors": at_errors,
                "pass_at_1": at_pass1,
                "ci_95": list(at_ci),
                "avg_context_tokens": avg_at_tokens,
            },
        },
        "improvement_pct": improvement_pct,
        "mcnemar_test": mcnemar,
        "per_sample": per_sample,
    }

    # Save final JSON
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  JSON saved to {json_path}")

    # Generate markdown report
    _generate_report(results, results_dir)

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


def _generate_report(results: dict, results_dir: str) -> None:
    report_path = os.path.join(results_dir, "llm_quality_openrouter.md")

    fc = results["strategies"]["full_context"]
    at = results["strategies"]["adaptive_trigger"]
    mc = results["mcnemar_test"]

    token_reduction = ""
    if fc["avg_context_tokens"] > 0:
        pct = (1 - at["avg_context_tokens"] / fc["avg_context_tokens"]) * 100
        token_reduction = f"Token reduction: {pct:.1f}% fewer tokens via Adaptive Trigger."

    lines = [
        "# CTX pass@1 Evaluation — OpenRouter API",
        "",
        f"**Date**: {results['timestamp']}",
        f"**Model**: {results['model']}",
        f"**Project**: {results['project']}",
        f"**Samples**: {results['n_samples']}  **Seed**: {results['seed']}",
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
        "## Context Token Comparison",
        "",
        f"- Full Context: fixed ~{results.get('full_context_tokens', 'N/A')} tokens per query.",
        f"- Adaptive Trigger: average ~{at['avg_context_tokens']:.0f} tokens per query.",
        token_reduction,
        "",
        "---",
        "",
        "## Per-Sample Results",
        "",
        "| # | Function | File | Full Context | Adaptive Trigger |",
        "|---|----------|------|-------------|-----------------|",
    ]

    for s in results["per_sample"]:
        fc_r = s["strategies"].get("full_context", {})
        at_r = s["strategies"].get("adaptive_trigger", {})
        fc_str = "PASS" if fc_r.get("passed") else ("ERROR" if fc_r.get("error") else "FAIL")
        at_str = "PASS" if at_r.get("passed") else ("ERROR" if at_r.get("error") else "FAIL")
        lines.append(f"| {s['index']+1} | `{s['function_name']}` | {s['file_path']} | {fc_str} | {at_str} |")

    lines.extend([
        "",
        "---",
        "",
        f"*Generated by CTX OpenRouter Evaluation ({results['timestamp']})*",
    ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report saved to {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CTX pass@1 Evaluation via OpenRouter API"
    )
    parser.add_argument("--project-path", required=True, help="Path to Python project")
    parser.add_argument("--n-samples", type=int, default=30, help="Number of samples (default: 30)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--model", default=None,
                        help=f"OpenRouter model ID (default: {OpenRouterEvaluator.PRIMARY_MODEL})")
    parser.add_argument("--results-dir", default="benchmarks/results",
                        help="Output directory (default: benchmarks/results)")
    args = parser.parse_args()

    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set.")
        print("Run: source ~/.claude/env/shared.env")
        sys.exit(1)

    if not os.path.isdir(args.project_path):
        print(f"ERROR: Project path not found: {args.project_path}")
        sys.exit(1)

    start = time.time()
    run_openrouter_experiment(
        project_path=args.project_path,
        n_samples=args.n_samples,
        results_dir=args.results_dir,
        seed=args.seed,
        model=args.model,
    )
    print(f"\nTotal time: {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
