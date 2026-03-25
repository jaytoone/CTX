#!/usr/bin/env python3
"""
CTX Hook Effectiveness Evaluation

Measures how well ctx_loader.py injects relevant context
for different query types (EXPLICIT_SYMBOL, SEMANTIC_CONCEPT,
IMPLICIT_CONTEXT, TEMPORAL_HISTORY).

Metrics:
  - Context Hit Rate (CHR): ground truth file in injected context
  - Precision: fraction of injected files that are relevant
  - Mean response time per query
  - Session continuity: TEMPORAL queries inject session files
"""

import io
import json
import os
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

# CTX project root
CWD = "/home/jayone/Project/CTX"

# ──────────────────────────────────────────────
# Test cases
# ──────────────────────────────────────────────

TEST_CASES: List[Tuple[str, Optional[List[str]]]] = [
    # EXPLICIT_SYMBOL (10)
    ("TriggerClassifier class 구현 보여줘", ["src/trigger/trigger_classifier.py"]),
    ("AdaptiveTriggerRetriever retrieve 메서드", ["src/retrieval/adaptive_trigger.py"]),
    ("BenchmarkRunner class 어디있어?", ["src/evaluator/benchmark_runner.py"]),
    ("FullContextRetriever 구현", ["src/retrieval/full_context.py"]),
    ("HybridDenseCTXRetriever 어떻게 동작해?", ["src/retrieval/hybrid_dense_ctx.py"]),
    ("TES metric 계산 함수", ["src/evaluator/metrics.py"]),
    ("RANGERApproxRetriever 구현 보여줘", ["src/retrieval/ranger_approx.py"]),
    ("RepoBenchSample class 찾아줘", ["src/evaluator/repobench_evaluator.py"]),
    ("GraphRAGRetriever class", ["src/retrieval/graph_rag.py"]),
    ("LLMQualityEvaluator class", ["src/evaluator/llm_quality.py"]),

    # SEMANTIC_CONCEPT (10)
    ("token efficiency 계산 로직", ["src/evaluator/metrics.py"]),
    ("import graph traversal 구현", ["src/retrieval/adaptive_trigger.py", "src/retrieval/hybrid_dense_ctx.py"]),
    ("recall at k 평가 로직", ["src/evaluator/metrics.py", "src/evaluator/benchmark_runner.py"]),
    ("LLM pass@1 실험 코드", ["run_llm_eval_openrouter.py", "run_llm_eval_opensource.py"]),
    ("BFS 구현 코드", ["src/retrieval/adaptive_trigger.py"]),
    ("trigger accuracy 실험 결과", ["benchmarks/results/trigger_accuracy.md"]),
    ("claude code integration 방법", ["docs/claude_code_integration.md"]),
    ("repobench evaluation 결과", ["benchmarks/results/repobench_eval.md"]),
    ("external codebase flask fastapi 결과", ["benchmarks/results/external_codebase_eval.md"]),
    ("openrouter gemini pass@1 결과", ["benchmarks/results/llm_quality_openrouter.md"]),

    # IMPLICIT_CONTEXT (5)
    ("AdaptiveTriggerRetriever dependencies 이해", ["src/retrieval/adaptive_trigger.py", "src/trigger/trigger_classifier.py"]),
    ("BenchmarkRunner imports 추적", ["src/evaluator/benchmark_runner.py", "src/retrieval/adaptive_trigger.py"]),
    ("HybridDenseCTXRetriever 의존 모듈", ["src/retrieval/hybrid_dense_ctx.py"]),
    ("metrics.py 사용하는 코드 파악", ["src/evaluator/metrics.py"]),
    ("trigger_classifier 호출하는 모듈", ["src/trigger/trigger_classifier.py", "src/retrieval/adaptive_trigger.py"]),

    # TEMPORAL_HISTORY / Session (5)
    ("이전에 작업하던 파일 보여줘", None),
    ("지난번에 편집한 코드 계속해줘", None),
    ("방금 전에 봤던 함수 다시 보여줘", None),
    ("이전 작업 이어서 진행", None),
    ("최근 수정한 파일 목록", None),
]

# Session simulation: access these files before TEMPORAL tests
SESSION_SIMULATION_FILES = [
    "src/trigger/trigger_classifier.py",
    "src/retrieval/adaptive_trigger.py",
    "src/evaluator/benchmark_runner.py",
    "src/evaluator/metrics.py",
    "src/retrieval/hybrid_dense_ctx.py",
]


# ──────────────────────────────────────────────
# Hook runner
# ──────────────────────────────────────────────

def run_hook(prompt: str, cwd: str) -> Dict:
    """Call ctx_loader.py via subprocess with JSON on stdin."""
    hook_path = os.path.expanduser("~/.claude/hooks/ctx_loader.py")
    payload = json.dumps({"prompt": prompt, "cwd": cwd})

    start = time.time()
    try:
        proc = subprocess.run(
            ["python3", hook_path],
            input=payload,
            text=True,
            capture_output=True,
            timeout=10,
        )
        elapsed = time.time() - start
        output = proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return {"context": "", "elapsed": 10.0, "error": "timeout"}
    except Exception as e:
        return {"context": "", "elapsed": time.time() - start, "error": str(e)}

    try:
        result = json.loads(output)
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
    except Exception:
        ctx = ""

    return {"context": ctx, "elapsed": elapsed}


def simulate_session(cwd: str, files_to_access: List[str]) -> None:
    """Simulate file access events in ctx_session_tracker.py."""
    tracker_path = os.path.expanduser("~/.claude/hooks/ctx_session_tracker.py")
    for rel_path in files_to_access:
        abs_path = os.path.join(cwd, rel_path)
        event = {
            "tool_name": "Read",
            "tool_input": {"file_path": abs_path},
            "cwd": cwd,
        }
        try:
            subprocess.run(
                ["python3", tracker_path],
                input=json.dumps(event),
                text=True,
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass


# ──────────────────────────────────────────────
# Metric helpers
# ──────────────────────────────────────────────

def extract_injected_files(context: str) -> List[str]:
    """Extract file paths from bullet lines in additionalContext."""
    # Matches "• path/to/file.py [symbols]"
    return re.findall(r"•\s+([^\s\[]+)", context)


def compute_hit_and_precision(
    context: str,
    ground_truth: Optional[List[str]],
    is_temporal: bool,
) -> Tuple[bool, float, List[str]]:
    """Return (hit, precision, injected_files)."""
    injected = extract_injected_files(context)

    if is_temporal:
        # TEMPORAL: hit if "Recent session" section is present
        hit = "Recent session" in context
        precision = 1.0 if hit else 0.0
        return hit, precision, injected

    if ground_truth is None:
        return False, 0.0, injected

    def _matches(gt: str, inj: str) -> bool:
        # Accept if one is a suffix of the other (handles abs vs rel paths)
        return gt in inj or inj.endswith(gt) or gt.endswith(inj)

    hit = any(
        any(_matches(gt, inj) for inj in injected)
        for gt in ground_truth
    )
    if injected:
        relevant = sum(
            1 for inj in injected
            if any(_matches(gt, inj) for gt in ground_truth)
        )
        precision = relevant / len(injected)
    else:
        precision = 0.0

    return hit, precision, injected


# ──────────────────────────────────────────────
# Trigger classification (import from hook)
# ──────────────────────────────────────────────

def classify_trigger_subprocess(prompt: str) -> Tuple[str, str, float]:
    """Classify trigger by importing ctx_loader inline (avoids sys.path pollution)."""
    hook_dir = os.path.expanduser("~/.claude/hooks")
    code = f"""
import sys, json
sys.path.insert(0, {repr(hook_dir)})
import ctx_loader
t, v, c = ctx_loader.classify_trigger({repr(prompt)})
print(json.dumps([t, v, c]))
"""
    try:
        proc = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True, timeout=5
        )
        result = json.loads(proc.stdout.strip())
        return result[0], result[1], result[2]
    except Exception:
        return "UNKNOWN", prompt[:30], 0.0


# ──────────────────────────────────────────────
# Evaluation loop
# ──────────────────────────────────────────────

def evaluate(test_cases: List, cwd: str) -> List[Dict]:
    results = []
    for i, (prompt, ground_truth) in enumerate(test_cases):
        is_temporal = (ground_truth is None)
        r = run_hook(prompt, cwd)
        hit, precision, injected = compute_hit_and_precision(
            r["context"], ground_truth, is_temporal
        )
        trigger, value, conf = classify_trigger_subprocess(prompt)

        results.append({
            "idx": i + 1,
            "prompt": prompt,
            "prompt_short": prompt[:50],
            "trigger": trigger,
            "confidence": round(conf, 2),
            "ground_truth": ground_truth,
            "hit": hit,
            "precision": round(precision, 3),
            "injected_files": injected,
            "injected_count": len(injected),
            "elapsed_ms": round(r["elapsed"] * 1000, 1),
            "context_preview": r["context"][:150],
            "is_temporal": is_temporal,
        })
    return results


# ──────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────

def generate_report(results: List[Dict]) -> str:
    total = len(results)
    hits = sum(1 for r in results if r["hit"])
    overall_chr = hits / total if total else 0.0
    avg_precision = sum(r["precision"] for r in results) / total if total else 0.0
    avg_elapsed = sum(r["elapsed_ms"] for r in results) / total if total else 0.0

    # Per-trigger-type breakdown
    by_trigger: Dict[str, List] = {}
    for r in results:
        by_trigger.setdefault(r["trigger"], []).append(r)

    type_order = ["EXPLICIT_SYMBOL", "SEMANTIC_CONCEPT", "IMPLICIT_CONTEXT",
                  "TEMPORAL_HISTORY", "UNKNOWN"]

    lines = [
        "# CTX Hook Effectiveness Evaluation",
        "",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}",
        f"Target: {CWD}",
        f"Total queries: {total}",
        "",
        "## Overall Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Context Hit Rate (CHR) | {overall_chr:.1%} ({hits}/{total}) |",
        f"| Mean Precision | {avg_precision:.3f} |",
        f"| Mean Response Time | {avg_elapsed:.1f} ms |",
        "",
        "## Per-Trigger-Type Results",
        "",
        "| Trigger Type | N | CHR | Mean Precision | Mean RT (ms) | Goal |",
        "|-------------|---|-----|----------------|--------------|------|",
    ]

    goals = {
        "EXPLICIT_SYMBOL": "≥ 80%",
        "SEMANTIC_CONCEPT": "≥ 60%",
        "IMPLICIT_CONTEXT": "≥ 60%",
        "TEMPORAL_HISTORY": "≥ 80%",
    }

    for ttype in type_order:
        group = by_trigger.get(ttype, [])
        if not group:
            continue
        n = len(group)
        chr_val = sum(1 for r in group if r["hit"]) / n
        prec = sum(r["precision"] for r in group) / n
        rt = sum(r["elapsed_ms"] for r in group) / n
        goal = goals.get(ttype, "-")
        pass_mark = "PASS" if (
            (ttype == "EXPLICIT_SYMBOL" and chr_val >= 0.80) or
            (ttype == "SEMANTIC_CONCEPT" and chr_val >= 0.60) or
            (ttype == "IMPLICIT_CONTEXT" and chr_val >= 0.60) or
            (ttype == "TEMPORAL_HISTORY" and chr_val >= 0.80)
        ) else "FAIL"
        lines.append(
            f"| {ttype} | {n} | {chr_val:.1%} ({pass_mark}) | "
            f"{prec:.3f} | {rt:.1f} | {goal} |"
        )

    lines += [
        "",
        "## Per-Query Results",
        "",
        "| # | Trigger | Prompt | Hit | Precision | Files | RT(ms) |",
        "|---|---------|--------|-----|-----------|-------|--------|",
    ]

    for r in results:
        hit_mark = "Y" if r["hit"] else "N"
        prompt_short = r["prompt_short"].replace("|", "/")
        lines.append(
            f"| {r['idx']} | {r['trigger'][:10]} | {prompt_short} | "
            f"{hit_mark} | {r['precision']:.2f} | {r['injected_count']} | {r['elapsed_ms']} |"
        )

    # Failure analysis
    failures = [r for r in results if not r["hit"]]
    if failures:
        lines += [
            "",
            "## Failure Analysis",
            "",
            f"Total failures: {len(failures)}/{total}",
            "",
        ]
        for r in failures:
            lines.append(f"### Query {r['idx']}: {r['prompt_short']}")
            lines.append(f"- Trigger: {r['trigger']} (conf={r['confidence']})")
            lines.append(f"- Ground truth: {r['ground_truth']}")
            lines.append(f"- Injected: {r['injected_files']}")
            lines.append(f"- Context preview: `{r['context_preview']}`")
            lines.append("")

    lines += [
        "",
        "## Session Continuity Detail",
        "",
    ]
    temporal = [r for r in results if r["is_temporal"]]
    if temporal:
        for r in temporal:
            hit_mark = "HIT" if r["hit"] else "MISS"
            lines.append(f"- [{hit_mark}] {r['prompt_short']}")
            lines.append(f"  Preview: `{r['context_preview'][:100]}`")
    else:
        lines.append("No TEMPORAL queries found.")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    print(f"[CTX Hook Eval] Target: {CWD}")
    print(f"[CTX Hook Eval] Running {len(TEST_CASES)} test cases...")
    print()

    # Split into non-temporal and temporal
    non_temporal = [(p, g) for p, g in TEST_CASES if g is not None]
    temporal = [(p, g) for p, g in TEST_CASES if g is None]

    # Run non-temporal first
    print(f"[1/3] Evaluating {len(non_temporal)} non-temporal queries...")
    results_non_temporal = evaluate(non_temporal, CWD)

    # Simulate session before temporal tests
    print(f"[2/3] Simulating session: accessing {len(SESSION_SIMULATION_FILES)} files...")
    simulate_session(CWD, SESSION_SIMULATION_FILES)
    # Small delay so session log is flushed
    time.sleep(0.2)

    # Run temporal
    print(f"[3/3] Evaluating {len(temporal)} temporal queries...")
    results_temporal = evaluate(temporal, CWD)

    # Merge results in original order
    all_results = results_non_temporal + results_temporal
    # Re-number
    for i, r in enumerate(all_results):
        r["idx"] = i + 1

    # Print summary
    total = len(all_results)
    hits = sum(1 for r in all_results if r["hit"])
    print(f"\n=== Results ===")
    print(f"Overall CHR: {hits}/{total} = {hits/total:.1%}")

    by_trigger: Dict[str, List] = {}
    for r in all_results:
        by_trigger.setdefault(r["trigger"], []).append(r)
    for ttype, group in sorted(by_trigger.items()):
        n = len(group)
        h = sum(1 for r in group if r["hit"])
        print(f"  {ttype}: {h}/{n} = {h/n:.1%}")

    avg_rt = sum(r["elapsed_ms"] for r in all_results) / total
    print(f"Mean RT: {avg_rt:.1f} ms")

    # Generate and save report
    report = generate_report(all_results)
    out_path = os.path.join(CWD, "benchmarks/results/hook_effectiveness_eval.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport saved: {out_path}")

    # Also save raw JSON
    json_path = os.path.join(CWD, "benchmarks/results/hook_effectiveness_eval.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Raw data: {json_path}")


if __name__ == "__main__":
    main()
