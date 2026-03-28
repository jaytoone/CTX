#!/usr/bin/env python3
"""
CTX Latency Profiler — SOYA deployment non-functional requirements validation.

Measures: P50/P95/P99 retrieval latency across 5 trigger types × 3 codebase sizes.
Goal: verify P99 < 500ms for all trigger types (SOYA deployment threshold).

Also checks: error handling for edge cases (empty codebase, missing imports, 0-result queries).
"""

import sys
import os
import time
import statistics
import json

# Add CTX src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

# ---------------------------------------------------------------------------
# Test codebases
# ---------------------------------------------------------------------------

CTX_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))  # ~168 files
FLASK_DIR = os.path.expanduser("~/Project/CTX/external_codebases/flask")           # ~79 files
# For "small": use just the CTX src/ subdirectory (~30 files)
CTX_SRC   = os.path.join(CTX_DIR, "src")

CODEBASES = [
    ("small",  CTX_SRC,  "CTX src/ (~30 files)"),
    ("medium", CTX_DIR,  "CTX full (~168 files)"),
]
if os.path.exists(FLASK_DIR):
    CODEBASES.append(("large", FLASK_DIR, "Flask (~79 files)"))

# ---------------------------------------------------------------------------
# Test queries per trigger type
# ---------------------------------------------------------------------------

QUERIES = {
    "EXPLICIT_SYMBOL": [
        "Show me the AdaptiveTriggerRetriever class definition",
        "Where is TriggerClassifier.classify defined?",
        "Find the `_concept_retrieve` method",
    ],
    "SEMANTIC_CONCEPT": [
        "Find all code related to retrieval",
        "Show everything about BM25 indexing",
        "Find code handling import graph traversal",
    ],
    "TEMPORAL_HISTORY": [
        "What did we previously discuss about testing?",
        "Remember the earlier conversation about imports",
        "What was mentioned before about the classifier",
    ],
    "IMPLICIT_CONTEXT": [
        "Fully understand adaptive_trigger.py — what does it depend on?",
        "What imports are needed to understand the retrieval module?",
        "Show all dependencies of trigger_classifier.py",
    ],
    "DEFAULT": [
        "Explain the system architecture",
        "How does the retrieval work?",
        "What is this project?",
    ],
}

N_WARMUP = 2
N_MEASURE = 10

# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

def test_edge_cases(codebase_dir: str) -> dict:
    """Test error handling for edge cases."""
    results = {}

    # Edge 1: empty query
    try:
        r = AdaptiveTriggerRetriever(codebase_dir)
        result = r.retrieve("q0", "", k=5)
        results["empty_query"] = "OK" if result is not None else "FAIL"
    except Exception as e:
        results["empty_query"] = f"EXCEPTION: {type(e).__name__}: {str(e)[:80]}"

    # Edge 2: query with no matching symbols
    try:
        r = AdaptiveTriggerRetriever(codebase_dir)
        result = r.retrieve("q1", "show me NonExistentClass12345", k=5)
        results["no_match_symbol"] = f"OK (returned {len(result.retrieved_files)} files)"
    except Exception as e:
        results["no_match_symbol"] = f"EXCEPTION: {type(e).__name__}: {str(e)[:80]}"

    # Edge 3: k=0
    try:
        r = AdaptiveTriggerRetriever(codebase_dir)
        result = r.retrieve("q2", "find the main function", k=0)
        results["k_zero"] = f"OK (returned {len(result.retrieved_files)} files)"
    except Exception as e:
        results["k_zero"] = f"EXCEPTION: {type(e).__name__}: {str(e)[:80]}"

    # Edge 4: k=1 (minimum useful)
    try:
        r = AdaptiveTriggerRetriever(codebase_dir)
        result = r.retrieve("q3", "show AdaptiveTriggerRetriever", k=1)
        results["k_one"] = f"OK (returned {len(result.retrieved_files)} files)"
    except Exception as e:
        results["k_one"] = f"EXCEPTION: {type(e).__name__}: {str(e)[:80]}"

    # Edge 5: very long query (1000 chars)
    try:
        long_q = "show me the function that handles " + ("retrieval processing " * 50)
        r = AdaptiveTriggerRetriever(codebase_dir)
        result = r.retrieve("q4", long_q, k=5)
        results["long_query"] = f"OK (returned {len(result.retrieved_files)} files)"
    except Exception as e:
        results["long_query"] = f"EXCEPTION: {type(e).__name__}: {str(e)[:80]}"

    return results

# ---------------------------------------------------------------------------
# Main profiling
# ---------------------------------------------------------------------------

def profile_codebase(name: str, codebase_dir: str, label: str) -> dict:
    if not os.path.exists(codebase_dir):
        return {"error": f"Directory not found: {codebase_dir}"}

    print(f"\n{'='*60}")
    print(f"  {label} [{name}]")
    print(f"{'='*60}")

    # Index time
    t0 = time.perf_counter()
    retriever = AdaptiveTriggerRetriever(codebase_dir)
    index_time_ms = (time.perf_counter() - t0) * 1000
    n_files = len(retriever.file_paths)
    print(f"  Index: {n_files} files in {index_time_ms:.1f}ms")

    results_by_type = {}

    for trigger_type, queries in QUERIES.items():
        times = []

        # Warmup
        for q in queries[:N_WARMUP]:
            try:
                retriever.retrieve("warmup", q, k=5)
            except Exception:
                pass

        # Measure
        for _ in range(N_MEASURE):
            for q in queries:
                t0 = time.perf_counter()
                try:
                    retriever.retrieve("bench", q, k=5)
                except Exception:
                    pass
                times.append((time.perf_counter() - t0) * 1000)

        p50  = statistics.median(times)
        p95  = sorted(times)[int(len(times) * 0.95)]
        p99  = sorted(times)[int(len(times) * 0.99)]
        mean = statistics.mean(times)

        soya_ok = "✓" if p99 < 500 else "✗"
        print(f"  {trigger_type:<22}: P50={p50:6.1f}ms  P95={p95:6.1f}ms  P99={p99:6.1f}ms  {soya_ok}")

        results_by_type[trigger_type] = {
            "p50_ms": round(p50, 2), "p95_ms": round(p95, 2), "p99_ms": round(p99, 2),
            "mean_ms": round(mean, 2), "n_samples": len(times),
            "soya_p99_ok": p99 < 500,
        }

    # Overall P99
    all_p99 = [v["p99_ms"] for v in results_by_type.values()]
    max_p99 = max(all_p99)
    overall_ok = all(v["soya_p99_ok"] for v in results_by_type.values())
    print(f"\n  Overall: max P99={max_p99:.1f}ms — SOYA P99<500ms: {'PASS ✓' if overall_ok else 'FAIL ✗'}")

    # Edge cases
    print(f"\n  Edge cases:")
    edge = test_edge_cases(codebase_dir)
    for k, v in edge.items():
        print(f"    {k:<22}: {v}")

    return {
        "name": name, "label": label, "n_files": n_files,
        "index_time_ms": round(index_time_ms, 1),
        "latency_by_trigger": results_by_type,
        "max_p99_ms": round(max_p99, 2),
        "soya_latency_pass": overall_ok,
        "edge_cases": edge,
    }


def main():
    print("CTX Latency Profiler — SOYA Deployment Validation")
    print(f"Target: P99 < 500ms for all trigger types")
    print(f"Method: {N_MEASURE} × {len(list(QUERIES.values())[0])} queries per trigger type")

    all_results = []
    for name, cdir, label in CODEBASES:
        r = profile_codebase(name, cdir, label)
        all_results.append(r)

    print(f"\n{'='*60}")
    print("SOYA DEPLOYMENT — NON-FUNCTIONAL REQUIREMENTS SUMMARY")
    print(f"{'='*60}")
    print(f"{'Codebase':<12} {'Files':>6} {'Index':>8} {'MaxP99':>8} {'Latency':>10} {'EdgeCases':>12}")
    print("-" * 60)
    for r in all_results:
        if "error" in r:
            continue
        edge_ok = all("OK" in str(v) or v.startswith("OK") for v in r.get("edge_cases", {}).values())
        print(f"  {r['name']:<10} {r['n_files']:>6} {r['index_time_ms']:>7.0f}ms {r['max_p99_ms']:>7.1f}ms "
              f"  {'PASS ✓' if r['soya_latency_pass'] else 'FAIL ✗':>10} "
              f"  {'PASS ✓' if edge_ok else 'WARN ⚠':>12}")

    overall_soya = all(r.get("soya_latency_pass", False) for r in all_results if "error" not in r)
    print(f"\n  Overall SOYA non-functional verdict: {'PASS ✓' if overall_soya else 'FAIL ✗'}")

    out_path = os.path.join(os.path.dirname(__file__), "../results/latency_profile_20260328.json")
    with open(out_path, "w") as f:
        json.dump({"results": all_results, "soya_pass": overall_soya}, f, indent=2)
    print(f"\n[SAVED] {out_path}")

    return all_results


if __name__ == "__main__":
    main()
