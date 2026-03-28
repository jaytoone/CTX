"""
aggregated_stat_report.py — Aggregated Statistical Report Across All Benchmarks

Reads all benchmark result JSON files from benchmarks/results/ and produces
a unified statistical report with:
- Cross-dataset p-values from real statistical_tests_*.json
- Effect size (Cohen's d)
- 95% confidence intervals from real evaluations
- CTX vs BM25 significance across multiple real codebases

Usage:
  python3 benchmarks/eval/aggregated_stat_report.py [--stat-test]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats as sp_stats

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
RESULTS_DIR = ROOT / "benchmarks" / "results"


# ---------------------------------------------------------------------------
# Result loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[dict]:
    """Safely load a JSON file."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_all_results() -> Dict[str, dict]:
    """Load all available benchmark results."""
    result_files = {
        "cross_session_recall": RESULTS_DIR / "cross_session_recall.json",
        "multi_dataset_cross_session": RESULTS_DIR / "multi_dataset_cross_session_eval.json",
        "coir_evaluation": RESULTS_DIR / "coir_evaluation.json",
        "repobench_eval": RESULTS_DIR / "repobench_eval.json",
        "coir_repobench_integrated": RESULTS_DIR / "coir_repobench_integrated.json",
        "instruction_grounding": RESULTS_DIR / "instruction_grounding_eval.json",
        "hook_effectiveness": RESULTS_DIR / "hook_effectiveness_eval.json",
        "ranger_comparison": RESULTS_DIR / "ranger_comparison.json",
    }

    # Per-dataset benchmark results
    for suffix in ["small", "real_AgentNode", "real_GraphPrompt", "real_OneViral",
                    "real_eval_flask", "real_eval_requests", "real_eval_fastapi"]:
        key = f"benchmark_{suffix}"
        result_files[key] = RESULTS_DIR / f"benchmark_{suffix}.json"

    # Statistical tests (real data with proper CIs)
    for suffix in ["small", "real_AgentNode", "real_GraphPrompt", "real_OneViral",
                    "real_eval_flask", "real_eval_requests", "real_eval_fastapi"]:
        stat_key = f"statistical_tests_{suffix}"
        result_files[stat_key] = RESULTS_DIR / f"statistical_tests_{suffix}.json"

    loaded = {}
    for name, path in result_files.items():
        data = _load_json(path)
        if data is not None:
            loaded[name] = data

    return loaded


# ---------------------------------------------------------------------------
# Statistical analysis
# ---------------------------------------------------------------------------

def cohens_d(group1: list, group2: list) -> float:
    """Compute Cohen's d effect size."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return 0.0
    m1, m2 = np.mean(group1), np.mean(group2)
    s1, s2 = np.std(group1, ddof=1), np.std(group2, ddof=1)
    pooled = np.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2))
    if pooled == 0:
        return 0.0
    return float((m1 - m2) / pooled)


def extract_goal1_metrics(all_results: Dict[str, dict]) -> dict:
    """Extract Goal 1 (Cross-Session Recall) metrics from multi_dataset_cross_session eval."""
    metrics = {}

    # From multi_dataset_cross_session (now uses real data)
    multi_ds = all_results.get("multi_dataset_cross_session")
    if multi_ds and "datasets" in multi_ds:
        for ds_name, ds_data in multi_ds["datasets"].items():
            if isinstance(ds_data, dict) and "scenarios" in ds_data:
                scenario_recalls = {}
                for s in ds_data["scenarios"]:
                    k = ds_data.get("k", 10)
                    key = f"recall_at_{k}"
                    scenario_recalls[s["scenario"]] = s.get(key, 0)

                ci = ds_data.get("confidence_intervals", {}).get("adaptive_trigger", {})
                metrics[ds_name] = {
                    "avg_recall_at_k": ds_data.get("avg_recall_at_k", 0),
                    "per_scenario": scenario_recalls,
                    "k": k,
                    "n_files": ds_data.get("n_files", 0),
                    "n_queries": ds_data.get("n_queries", 0),
                    "source": ds_data.get("source", "unknown"),
                    "ci_95": [ci.get("ci_lower", 0), ci.get("ci_upper", 0)] if ci else None,
                    "ci_n": ci.get("n", 0) if ci else 0,
                }

    # From single cross_session_recall (backup for small dataset)
    if "small" not in metrics:
        single_cs = all_results.get("cross_session_recall")
        if single_cs and "scenarios" in single_cs:
            k = single_cs.get("k", 10)
            scenario_recalls = {}
            for s in single_cs["scenarios"]:
                key = f"recall_at_{k}"
                scenario_recalls[s["scenario"]] = s.get(key, 0)
            metrics["small"] = {
                "avg_recall_at_k": single_cs.get("avg_recall_at_k", 0),
                "per_scenario": scenario_recalls,
                "k": k,
                "source": "cross_session_recall.json",
            }

    return metrics


def extract_goal2_metrics(all_results: Dict[str, dict]) -> dict:
    """Extract Goal 2 (Instruction Grounding / COIR) metrics."""
    metrics = {}

    coir = all_results.get("coir_evaluation")
    if coir and "strategies" in coir:
        for strat_name, strat_data in coir["strategies"].items():
            metrics[f"coir_{strat_name}"] = {
                "recall_at_5": strat_data.get("recall_at_5", 0),
                "mrr": strat_data.get("mrr", 0),
                "ndcg_at_10": strat_data.get("ndcg_at_10", 0),
            }

    integrated = all_results.get("coir_repobench_integrated")
    if integrated:
        for bench in ["coir", "repobench"]:
            bench_data = integrated.get(bench, {})
            for strat_name, strat_data in bench_data.get("strategies", {}).items():
                metrics[f"integrated_{bench}_{strat_name}"] = {
                    "recall_at_5": strat_data.get("recall_at_5", 0),
                    "ndcg_at_5": strat_data.get("ndcg_at_5", 0),
                    "ndcg_at_10": strat_data.get("ndcg_at_10", 0),
                }

    ig = all_results.get("instruction_grounding")
    if ig:
        if "avg_ndcg_at_5" in ig:
            metrics["instruction_grounding"] = {
                "ndcg_at_5": ig.get("avg_ndcg_at_5", 0),
                "recall_at_5": ig.get("avg_recall_at_5", 0),
            }

    return metrics


def extract_real_statistical_tests(all_results: Dict[str, dict]) -> dict:
    """Extract real statistical test results (CTX vs BM25) from statistical_tests_*.json files.

    These contain proper Wilcoxon signed-rank tests, McNemar tests, and 95% CIs
    computed on actual per-query recall values from real codebases.
    """
    tests = {}

    stat_keys = [k for k in all_results.keys() if k.startswith("statistical_tests_")]
    for key in sorted(stat_keys):
        data = all_results[key]
        ds_name = key.replace("statistical_tests_", "")

        ci = data.get("confidence_intervals", {})
        pw = data.get("pairwise_tests", {})

        at_ci = ci.get("adaptive_trigger", {})
        bm25_ci = ci.get("bm25", {})
        bm25_pw = pw.get("bm25", {})

        tests[ds_name] = {
            "ctx_recall_at_5": {
                "mean": at_ci.get("mean", 0),
                "ci_95": [at_ci.get("ci_lower", 0), at_ci.get("ci_upper", 0)],
                "n": at_ci.get("n", 0),
            },
            "bm25_recall_at_5": {
                "mean": bm25_ci.get("mean", 0),
                "ci_95": [bm25_ci.get("ci_lower", 0), bm25_ci.get("ci_upper", 0)],
                "n": bm25_ci.get("n", 0),
            },
            "ctx_vs_bm25": {
                "wilcoxon_p_value": bm25_pw.get("wilcoxon_p_value", 1.0),
                "wilcoxon_significant": bm25_pw.get("wilcoxon_significant", False),
                "mcnemar_p_value": bm25_pw.get("mcnemar_p_value", 1.0),
                "mcnemar_significant": bm25_pw.get("mcnemar_significant", False),
            },
        }

    return tests


def extract_per_dataset_benchmark_metrics(all_results: Dict[str, dict]) -> dict:
    """Extract CTX vs baseline metrics from per-dataset benchmark results."""
    metrics = {}
    for key, data in all_results.items():
        if key.startswith("benchmark_") and "strategies" in data:
            ds_name = key.replace("benchmark_", "")
            ctx_data = None
            baseline_data = None
            for strat_name, strat_info in data["strategies"].items():
                if "adaptive_trigger" in strat_name.lower():
                    ctx_data = strat_info
                elif "bm25" in strat_name.lower():
                    baseline_data = strat_info

            # Fallback: try full_context or other ctx-like strategies
            if not ctx_data:
                for strat_name, strat_info in data["strategies"].items():
                    if "ctx" in strat_name.lower() or "full_context" in strat_name.lower():
                        ctx_data = strat_info
                        break

            if ctx_data:
                agg = ctx_data.get("aggregate_metrics", {})
                metrics[ds_name] = {
                    "ctx_recall_at_5": agg.get("mean_recall@5", 0),
                    "ctx_recall_at_10": agg.get("mean_recall@10", 0),
                    "ctx_ndcg_at_5": agg.get("mean_ndcg@5", 0),
                }
                if baseline_data:
                    bl_agg = baseline_data.get("aggregate_metrics", {})
                    metrics[ds_name]["bm25_recall_at_5"] = bl_agg.get("mean_recall@5", 0)
                    metrics[ds_name]["bm25_ndcg_at_5"] = bl_agg.get("mean_ndcg@5", 0)

    return metrics


def run_cross_dataset_significance_tests(
    goal1_metrics: dict,
    goal2_metrics: dict,
    real_stat_tests: dict,
    per_dataset: dict,
) -> dict:
    """Run significance tests across all datasets using real statistical test data."""
    tests = {}

    # --- Goal 1: Cross-dataset CTX recall consistency ---
    recall_values = []
    recall_labels = []
    for ds_name, ds_data in goal1_metrics.items():
        val = ds_data.get("avg_recall_at_k", 0)
        recall_values.append(val)
        recall_labels.append(ds_name)

    if len(recall_values) >= 3:
        mean_r = float(np.mean(recall_values))
        std_r = float(np.std(recall_values, ddof=1))
        t_stat, p_val = sp_stats.ttest_1samp(recall_values, 0.0)
        tests["goal1_recall_above_zero"] = {
            "datasets": recall_labels,
            "values": [round(v, 3) for v in recall_values],
            "mean": round(mean_r, 3),
            "std": round(std_r, 3),
            "t_stat": round(float(t_stat), 4),
            "p_value": round(float(p_val), 6),
            "significant": float(p_val) < 0.05,
            "interpretation": (
                "CTX recall is significantly above zero across all real datasets"
                if float(p_val) < 0.05
                else "Cannot confirm CTX recall significantly above zero"
            ),
        }

    # --- CTX vs BM25: aggregate across real statistical tests ---
    if real_stat_tests:
        ctx_means = []
        bm25_means = []
        p_values = []
        significant_datasets = []
        per_ds_comparison = {}

        for ds_name, st in real_stat_tests.items():
            ctx_r5 = st.get("ctx_recall_at_5", {}).get("mean", 0)
            bm25_r5 = st.get("bm25_recall_at_5", {}).get("mean", 0)
            ctx_means.append(ctx_r5)
            bm25_means.append(bm25_r5)

            pw = st.get("ctx_vs_bm25", {})
            p = pw.get("wilcoxon_p_value", 1.0)
            p_values.append(p)
            if pw.get("wilcoxon_significant", False):
                significant_datasets.append(ds_name)

            per_ds_comparison[ds_name] = {
                "ctx_recall_at_5": round(ctx_r5, 4),
                "bm25_recall_at_5": round(bm25_r5, 4),
                "diff": round(ctx_r5 - bm25_r5, 4),
                "wilcoxon_p": round(p, 6),
                "significant": pw.get("wilcoxon_significant", False),
            }

        # Compute effect size across all datasets
        d = cohens_d(ctx_means, bm25_means) if len(ctx_means) >= 2 else 0.0

        # Paired t-test across dataset means (CTX vs BM25)
        if len(ctx_means) >= 3:
            paired_t, paired_p = sp_stats.ttest_rel(ctx_means, bm25_means)
        else:
            paired_t, paired_p = 0.0, 1.0

        tests["ctx_vs_bm25_real_data"] = {
            "n_datasets": len(real_stat_tests),
            "n_significant_wilcoxon": len(significant_datasets),
            "significant_datasets": significant_datasets,
            "ctx_mean_recall_at_5": round(float(np.mean(ctx_means)), 4),
            "bm25_mean_recall_at_5": round(float(np.mean(bm25_means)), 4),
            "cohens_d": round(d, 4),
            "paired_t_stat": round(float(paired_t), 4),
            "paired_t_p_value": round(float(paired_p), 6),
            "paired_t_significant": float(paired_p) < 0.05,
            "per_dataset": per_ds_comparison,
        }

    # --- Goal 1 per-scenario consistency ---
    scenario_values = {"head": [], "torso": [], "tail": []}
    for ds_name, ds_data in goal1_metrics.items():
        for scenario in ["head", "torso", "tail"]:
            val = ds_data.get("per_scenario", {}).get(scenario)
            if val is not None:
                scenario_values[scenario].append(val)

    for scenario, vals in scenario_values.items():
        if len(vals) >= 2:
            mean_v = float(np.mean(vals))
            std_v = float(np.std(vals, ddof=1))
            tests[f"goal1_{scenario}_consistency"] = {
                "values": [round(v, 3) for v in vals],
                "mean": round(mean_v, 3),
                "std": round(std_v, 3),
                "consistent": std_v < 0.15,
            }

    # --- Goal 2: CTX vs baseline NDCG comparison ---
    ctx_ndcg_values = []
    baseline_ndcg_values = []
    for key, data in goal2_metrics.items():
        if "ctx" in key.lower() or "adaptive" in key.lower():
            ndcg = data.get("ndcg_at_10", data.get("ndcg_at_5", 0))
            if ndcg > 0:
                ctx_ndcg_values.append(ndcg)
        elif "bm25" in key.lower() or "tfidf" in key.lower():
            ndcg = data.get("ndcg_at_10", data.get("ndcg_at_5", 0))
            if ndcg > 0:
                baseline_ndcg_values.append(ndcg)

    if ctx_ndcg_values and baseline_ndcg_values:
        ctx_mean = float(np.mean(ctx_ndcg_values))
        base_mean = float(np.mean(baseline_ndcg_values))
        if len(ctx_ndcg_values) >= 2 and len(baseline_ndcg_values) >= 2:
            d = cohens_d(ctx_ndcg_values, baseline_ndcg_values)
            t_stat, p_val = sp_stats.ttest_ind(ctx_ndcg_values, baseline_ndcg_values)
        else:
            d = 0.0
            t_stat, p_val = 0.0, 1.0
        tests["goal2_ctx_vs_baseline"] = {
            "ctx_mean_ndcg": round(ctx_mean, 4),
            "baseline_mean_ndcg": round(base_mean, 4),
            "diff": round(ctx_mean - base_mean, 4),
            "cohens_d": round(d, 4),
            "t_stat": round(float(t_stat), 4),
            "p_value": round(float(p_val), 4),
            "significant": float(p_val) < 0.05,
        }

    # --- Confidence interval summary from real stat tests ---
    if real_stat_tests:
        ci_table = {}
        for ds_name, st in real_stat_tests.items():
            ctx_ci = st.get("ctx_recall_at_5", {})
            bm25_ci = st.get("bm25_recall_at_5", {})
            ci_table[ds_name] = {
                "ctx_mean": round(ctx_ci.get("mean", 0), 4),
                "ctx_ci_95": [round(ctx_ci.get("ci_95", [0, 0])[0], 4),
                              round(ctx_ci.get("ci_95", [0, 0])[1], 4)],
                "ctx_n": ctx_ci.get("n", 0),
                "bm25_mean": round(bm25_ci.get("mean", 0), 4),
                "bm25_ci_95": [round(bm25_ci.get("ci_95", [0, 0])[0], 4),
                               round(bm25_ci.get("ci_95", [0, 0])[1], 4)],
            }
        tests["confidence_intervals_real"] = ci_table

    return tests


def _generate_markdown_report(
    all_results: Dict[str, dict],
    goal1: dict,
    goal2: dict,
    significance: dict,
    per_dataset: dict,
    real_stat_tests: dict,
) -> str:
    """Generate comprehensive markdown report."""
    ts = datetime.now().isoformat()
    lines = [
        "# CTX Aggregated Statistical Report (Real Data)",
        "",
        f"**Date**: {ts}",
        f"**Benchmarks loaded**: {len(all_results)}",
        f"**Real statistical test files**: {len(real_stat_tests)}",
        "",
        "---",
        "",
        "## Goal 1: Cross-Session Recall (Real Codebases)",
        "",
        "| Dataset | Files | Queries | Avg Recall@K | 95% CI | Source |",
        "|---------|-------|---------|-------------|--------|--------|",
    ]

    for ds_name, ds_data in goal1.items():
        ci = ds_data.get("ci_95")
        ci_str = f"[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else "N/A"
        n_files = ds_data.get("n_files", "N/A")
        n_queries = ds_data.get("n_queries", "N/A")
        source = ds_data.get("source", "N/A")[:30]
        lines.append(
            f"| {ds_name} | {n_files} | {n_queries} "
            f"| {ds_data.get('avg_recall_at_k', 0):.3f} | {ci_str} | {source} |"
        )

    # Per-scenario breakdown
    lines.extend([
        "",
        "### Per-Scenario Breakdown",
        "",
        "| Dataset | Head | Torso | Tail | All |",
        "|---------|------|-------|------|-----|",
    ])
    for ds_name, ds_data in goal1.items():
        ps = ds_data.get("per_scenario", {})
        lines.append(
            f"| {ds_name} "
            f"| {ps.get('head', ps.get('head_files', 0)):.3f} "
            f"| {ps.get('torso', ps.get('torso_files', 0)):.3f} "
            f"| {ps.get('tail', 0):.3f} "
            f"| {ps.get('all', ps.get('mixed_10', 0)):.3f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## CTX vs BM25: Real Statistical Tests",
        "",
    ])

    # Show per-dataset CTX vs BM25 comparison from real stat tests
    if real_stat_tests:
        lines.extend([
            "| Dataset | CTX R@5 | CTX 95% CI | BM25 R@5 | BM25 95% CI | Wilcoxon p | Sig? |",
            "|---------|---------|------------|----------|-------------|-----------|------|",
        ])
        for ds_name, st in real_stat_tests.items():
            ctx = st.get("ctx_recall_at_5", {})
            bm25 = st.get("bm25_recall_at_5", {})
            pw = st.get("ctx_vs_bm25", {})
            ctx_ci = ctx.get("ci_95", [0, 0])
            bm25_ci = bm25.get("ci_95", [0, 0])
            p = pw.get("wilcoxon_p_value", 1.0)
            sig = "YES" if pw.get("wilcoxon_significant") else "no"
            lines.append(
                f"| {ds_name} "
                f"| {ctx.get('mean', 0):.4f} "
                f"| [{ctx_ci[0]:.4f}, {ctx_ci[1]:.4f}] "
                f"| {bm25.get('mean', 0):.4f} "
                f"| [{bm25_ci[0]:.4f}, {bm25_ci[1]:.4f}] "
                f"| {p:.6f} "
                f"| {sig} |"
            )
        lines.append("")

    lines.extend([
        "---",
        "",
        "## Goal 2: Instruction Grounding / Code Retrieval",
        "",
        "| Benchmark-Strategy | R@5 | NDCG@5 | NDCG@10 |",
        "|-------------------|-----|--------|---------|",
    ])

    for key, data in goal2.items():
        lines.append(
            f"| {key} "
            f"| {data.get('recall_at_5', 0):.4f} "
            f"| {data.get('ndcg_at_5', 0):.4f} "
            f"| {data.get('ndcg_at_10', 0):.4f} |"
        )

    # Per-dataset benchmark results
    if per_dataset:
        lines.extend([
            "",
            "---",
            "",
            "## Per-Dataset Benchmark Results",
            "",
            "| Dataset | CTX R@5 | CTX R@10 | BM25 R@5 |",
            "|---------|---------|---------|----------|",
        ])
        for ds_name, ds_data in per_dataset.items():
            lines.append(
                f"| {ds_name} "
                f"| {ds_data.get('ctx_recall_at_5', 0):.4f} "
                f"| {ds_data.get('ctx_recall_at_10', 0):.4f} "
                f"| {ds_data.get('bm25_recall_at_5', 0):.4f} |"
            )

    # Significance tests
    lines.extend([
        "",
        "---",
        "",
        "## Statistical Significance Tests",
        "",
    ])

    for test_name, test_data in significance.items():
        if test_name == "confidence_intervals_real":
            continue  # Already shown above
        lines.append(f"### {test_name}")
        lines.append("")

        if "p_value" in test_data or "paired_t_p_value" in test_data:
            p = test_data.get("p_value", test_data.get("paired_t_p_value", "N/A"))
            sig = test_data.get("significant", test_data.get("paired_t_significant", False))
            sig_str = "SIGNIFICANT (p < 0.05)" if sig else "not significant"
            lines.append(f"- **p-value**: {p} ({sig_str})")

            if "t_stat" in test_data:
                lines.append(f"- **t-statistic**: {test_data['t_stat']:.4f}")
            if "paired_t_stat" in test_data:
                lines.append(f"- **Paired t-stat**: {test_data['paired_t_stat']:.4f}")
            if "cohens_d" in test_data:
                d = test_data["cohens_d"]
                magnitude = "large" if abs(d) >= 0.8 else "medium" if abs(d) >= 0.5 else "small"
                lines.append(f"- **Cohen's d**: {d:.4f} ({magnitude} effect)")

        if "n_datasets" in test_data:
            lines.append(f"- **Datasets tested**: {test_data['n_datasets']}")
        if "n_significant_wilcoxon" in test_data:
            lines.append(f"- **Significant (Wilcoxon)**: {test_data['n_significant_wilcoxon']}/{test_data.get('n_datasets', '?')}")
        if "significant_datasets" in test_data:
            lines.append(f"- **Significant datasets**: {test_data['significant_datasets']}")
        if "mean" in test_data:
            lines.append(f"- **Mean**: {test_data['mean']:.3f}")
        if "std" in test_data:
            lines.append(f"- **Std**: {test_data['std']:.3f}")
        if "values" in test_data:
            lines.append(f"- **Values**: {test_data['values']}")
        if "datasets" in test_data:
            lines.append(f"- **Datasets**: {test_data['datasets']}")
        if "interpretation" in test_data:
            lines.append(f"- **Interpretation**: {test_data['interpretation']}")
        if "consistent" in test_data:
            lines.append(f"- **Consistent**: {test_data['consistent']}")

        # Per-dataset detail for CTX vs BM25
        if "per_dataset" in test_data and test_name == "ctx_vs_bm25_real_data":
            lines.append("")
            lines.append("| Dataset | CTX R@5 | BM25 R@5 | Diff | Wilcoxon p | Sig? |")
            lines.append("|---------|---------|----------|------|-----------|------|")
            for ds, comp in test_data["per_dataset"].items():
                sig_str = "YES" if comp.get("significant") else "no"
                lines.append(
                    f"| {ds} "
                    f"| {comp.get('ctx_recall_at_5', 0):.4f} "
                    f"| {comp.get('bm25_recall_at_5', 0):.4f} "
                    f"| {comp.get('diff', 0):+.4f} "
                    f"| {comp.get('wilcoxon_p', 1.0):.6f} "
                    f"| {sig_str} |"
                )
        lines.append("")

    # Final verdict
    lines.extend([
        "---",
        "",
        "## Verdict",
        "",
    ])

    goal1_pass = all(
        d.get("avg_recall_at_k", 0) > 0
        for d in goal1.values()
    ) if goal1 else False

    g1_sig = significance.get("goal1_recall_above_zero", {})
    g1_significant = g1_sig.get("significant", False)

    ctx_bm25 = significance.get("ctx_vs_bm25_real_data", {})
    n_sig = ctx_bm25.get("n_significant_wilcoxon", 0)
    n_total = ctx_bm25.get("n_datasets", 0)

    lines.append(f"- **Goal 1 (Cross-Session Recall > 0 on all datasets)**: {'PASS' if goal1_pass else 'FAIL'}")
    lines.append(f"  - Statistical significance: {'YES (p < 0.05)' if g1_significant else 'NO'}")
    lines.append(f"  - Datasets with real data: {len(goal1)}")

    lines.append(f"- **CTX vs BM25 (Wilcoxon signed-rank on real codebases)**:")
    lines.append(f"  - Significant on {n_sig}/{n_total} datasets (p < 0.05)")
    lines.append(f"  - Cohen's d: {ctx_bm25.get('cohens_d', 'N/A')}")
    lines.append(f"  - Paper requirement (p < 0.05 on 2+ datasets): {'MET' if n_sig >= 2 else 'NOT MET'}")

    g2_sig = significance.get("goal2_ctx_vs_baseline", {})
    g2_d = g2_sig.get("cohens_d", 0)
    lines.append(f"- **Goal 2 (CTX vs Baseline NDCG)**: Cohen's d = {g2_d:.4f}")
    lines.append(f"  - Statistical significance: {'YES (p < 0.05)' if g2_sig.get('significant') else 'NO'}")

    overall = "PASS" if goal1_pass and n_sig >= 2 else "PARTIAL"
    lines.append(f"- **Overall**: {overall}")

    lines.extend([
        "",
        "---",
        "",
        f"*Generated by CTX Aggregated Stat Report — Real Data ({ts})*",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Aggregated statistical report across all CTX benchmarks (real data)"
    )
    parser.add_argument("--stat-test", action="store_true", help="Include significance test details")
    args = parser.parse_args()

    print("=" * 70)
    print("CTX AGGREGATED STATISTICAL REPORT (REAL DATA)")
    print("=" * 70)

    # Load all results
    print("\n[1/5] Loading benchmark results...")
    all_results = load_all_results()
    print(f"  Loaded {len(all_results)} result files:")
    for name in sorted(all_results.keys()):
        print(f"    - {name}")

    # Extract Goal 1 metrics
    print("\n[2/5] Extracting Goal 1 (Cross-Session Recall) metrics...")
    goal1 = extract_goal1_metrics(all_results)
    for ds_name, ds_data in goal1.items():
        ci = ds_data.get("ci_95")
        ci_str = f"CI=[{ci[0]:.3f}, {ci[1]:.3f}]" if ci else ""
        print(f"  {ds_name:20s}: Recall@{ds_data.get('k', 10)}={ds_data['avg_recall_at_k']:.3f} {ci_str}")

    # Extract Goal 2 metrics
    print("\n[3/5] Extracting Goal 2 (Code Retrieval / NDCG) metrics...")
    goal2 = extract_goal2_metrics(all_results)
    for key, data in goal2.items():
        ndcg10 = data.get("ndcg_at_10", data.get("ndcg_at_5", 0))
        print(f"  {key:40s}: NDCG@10={ndcg10:.4f}")

    # Extract real statistical tests
    print("\n[4/5] Loading real statistical test results...")
    real_stat_tests = extract_real_statistical_tests(all_results)
    for ds_name, st in real_stat_tests.items():
        ctx_m = st.get("ctx_recall_at_5", {}).get("mean", 0)
        bm25_m = st.get("bm25_recall_at_5", {}).get("mean", 0)
        pw = st.get("ctx_vs_bm25", {})
        p = pw.get("wilcoxon_p_value", 1.0)
        sig_str = "***" if pw.get("wilcoxon_significant") else ""
        print(f"  {ds_name:25s}: CTX={ctx_m:.4f} vs BM25={bm25_m:.4f}  p={p:.6f} {sig_str}")

    # Per-dataset benchmarks
    per_dataset = extract_per_dataset_benchmark_metrics(all_results)

    # Run significance tests
    print("\n[5/5] Running cross-dataset significance tests...")
    significance = run_cross_dataset_significance_tests(goal1, goal2, real_stat_tests, per_dataset)

    for test_name, test_data in significance.items():
        if test_name == "confidence_intervals_real":
            continue
        p = test_data.get("p_value", test_data.get("paired_t_p_value", "N/A"))
        sig = test_data.get("significant", test_data.get("paired_t_significant", False))
        d = test_data.get("cohens_d", "N/A")
        mean = test_data.get("mean", test_data.get("ctx_mean_recall_at_5", "N/A"))
        n_sig = test_data.get("n_significant_wilcoxon", "")
        print(f"  {test_name}: p={p}, significant={sig}, d={d}, mean={mean} {f'({n_sig} sig)' if n_sig else ''}")

    # Summary
    print(f"\n{'=' * 70}")
    print("VERDICT")
    goal1_pass = all(d.get("avg_recall_at_k", 0) > 0 for d in goal1.values()) if goal1 else False
    g1_sig = significance.get("goal1_recall_above_zero", {})
    print(f"  Goal 1 (Recall > 0): {'PASS' if goal1_pass else 'FAIL'} | p={g1_sig.get('p_value', 'N/A')}")

    ctx_bm25 = significance.get("ctx_vs_bm25_real_data", {})
    n_sig = ctx_bm25.get("n_significant_wilcoxon", 0)
    n_total = ctx_bm25.get("n_datasets", 0)
    print(f"  CTX vs BM25: {n_sig}/{n_total} datasets significant | d={ctx_bm25.get('cohens_d', 'N/A')}")
    print(f"  Paper requirement (p<0.05 on 2+ datasets): {'MET' if n_sig >= 2 else 'NOT MET'}")

    g2_sig = significance.get("goal2_ctx_vs_baseline", {})
    print(f"  Goal 2 (CTX vs Baseline): d={g2_sig.get('cohens_d', 'N/A')} | p={g2_sig.get('p_value', 'N/A')}")

    # Save
    os.makedirs(RESULTS_DIR, exist_ok=True)

    output = {
        "timestamp": datetime.now().isoformat(),
        "data_source": "real_codebases_only",
        "n_result_files_loaded": len(all_results),
        "result_files": sorted(all_results.keys()),
        "goal1_cross_session_recall": goal1,
        "goal2_code_retrieval": goal2,
        "real_statistical_tests": real_stat_tests,
        "per_dataset_benchmarks": per_dataset,
        "significance_tests": significance,
    }

    json_path = RESULTS_DIR / "aggregated_stat_report.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nJSON saved -> {json_path}")

    md_report = _generate_markdown_report(all_results, goal1, goal2, significance, per_dataset, real_stat_tests)
    md_path = RESULTS_DIR / "aggregated_stat_report.md"
    with open(md_path, "w") as f:
        f.write(md_report)
    print(f"Report saved -> {md_path}")


if __name__ == "__main__":
    main()
