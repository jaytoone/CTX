"""
Error analysis for CTX experiment.

Classifies failure cases into patterns:
- FALSE_NEGATIVE: relevant file not retrieved
- FALSE_POSITIVE: irrelevant file retrieved in top-k
- TRIGGER_MISS: trigger type misclassification
- GRAPH_MISS: import graph traversal failure

Produces per-strategy failure breakdowns and cross-strategy comparisons.
"""

import json
import os
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class FailureCase:
    """A single failure instance."""
    query_id: str
    query_text: str
    trigger_type: str
    failure_type: str  # FALSE_NEGATIVE, FALSE_POSITIVE, TRIGGER_MISS, GRAPH_MISS
    missed_files: List[str] = field(default_factory=list)
    spurious_files: List[str] = field(default_factory=list)
    expected_trigger: str = ""
    actual_trigger: str = ""
    detail: str = ""


@dataclass
class FailureAnalysis:
    """Aggregated failure analysis for one strategy."""
    strategy: str
    total_queries: int = 0
    total_failures: int = 0
    failure_cases: List[FailureCase] = field(default_factory=list)
    pattern_counts: Dict[str, int] = field(default_factory=dict)
    per_trigger_failures: Dict[str, int] = field(default_factory=dict)
    per_trigger_totals: Dict[str, int] = field(default_factory=dict)

    def failure_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return self.total_failures / self.total_queries

    def top_failures(self, n: int = 10) -> List[FailureCase]:
        """Return top-n failure cases by severity (most missed files first)."""
        return sorted(
            self.failure_cases,
            key=lambda fc: len(fc.missed_files),
            reverse=True,
        )[:n]


@dataclass
class ComparisonReport:
    """Cross-strategy comparison of failures."""
    ctx_only_wins: List[Dict] = field(default_factory=list)
    baseline_only_wins: List[Dict] = field(default_factory=list)
    both_fail: List[Dict] = field(default_factory=list)
    both_succeed: int = 0
    summary: str = ""


def analyze_failures(
    benchmark_data: Dict,
    strategy_name: str,
    k: int = 5,
) -> FailureAnalysis:
    """Analyze failure cases for a single strategy from benchmark JSON data.

    Args:
        benchmark_data: Loaded benchmark JSON (with per-query results)
        strategy_name: Which strategy to analyze
        k: Cutoff for Recall@K evaluation

    Returns:
        FailureAnalysis with classified failure cases
    """
    analysis = FailureAnalysis(strategy=strategy_name)

    strat_data = benchmark_data.get("strategies", {}).get(strategy_name)
    if not strat_data:
        return analysis

    # We need per-query results -- check if they exist in the data
    # The benchmark_runner saves aggregate metrics, so we reconstruct from
    # the runner's query_results if available, or from the aggregate data
    queries = benchmark_data.get("_query_results", {}).get(strategy_name, [])

    if not queries:
        # Fallback: use aggregate metrics only
        agg = strat_data.get("aggregate_metrics", {})
        recall_5 = agg.get("mean_recall@5", 0.0)
        analysis.total_queries = strat_data.get("query_count", 0)
        analysis.total_failures = int(analysis.total_queries * (1 - recall_5))
        return analysis

    analysis.total_queries = len(queries)

    for qr in queries:
        q_id = qr.get("query_id", "")
        q_text = qr.get("query_text", "")
        q_type = qr.get("trigger_type", "")
        retrieved = set(qr.get("retrieved_files", [])[:k])
        relevant = set(qr.get("relevant_files", []))

        analysis.per_trigger_totals[q_type] = analysis.per_trigger_totals.get(q_type, 0) + 1

        # Check for failures
        missed = relevant - retrieved
        spurious = retrieved - relevant

        if missed:
            analysis.total_failures += 1
            analysis.per_trigger_failures[q_type] = analysis.per_trigger_failures.get(q_type, 0) + 1

            # Classify failure type
            if q_type == "IMPLICIT_CONTEXT" and missed:
                failure_type = "GRAPH_MISS"
            elif len(spurious) > len(retrieved) * 0.5:
                failure_type = "FALSE_POSITIVE"
            else:
                failure_type = "FALSE_NEGATIVE"

            analysis.pattern_counts[failure_type] = analysis.pattern_counts.get(failure_type, 0) + 1

            analysis.failure_cases.append(FailureCase(
                query_id=q_id,
                query_text=q_text,
                trigger_type=q_type,
                failure_type=failure_type,
                missed_files=list(missed),
                spurious_files=list(spurious),
                detail=f"Retrieved {len(retrieved)}/{len(relevant)} relevant files",
            ))

    return analysis


def compare_strategies(
    benchmark_data: Dict,
    strategy_a: str,
    strategy_b: str,
    k: int = 5,
) -> ComparisonReport:
    """Compare failure patterns between two strategies.

    Args:
        benchmark_data: Loaded benchmark JSON with _query_results
        strategy_a: First strategy (typically CTX/adaptive_trigger)
        strategy_b: Second strategy (typically a baseline)
        k: Cutoff for evaluation

    Returns:
        ComparisonReport showing where each strategy wins/loses
    """
    report = ComparisonReport()

    queries_a = benchmark_data.get("_query_results", {}).get(strategy_a, [])
    queries_b = benchmark_data.get("_query_results", {}).get(strategy_b, [])

    if not queries_a or not queries_b:
        report.summary = f"Insufficient per-query data for {strategy_a} vs {strategy_b}"
        return report

    # Build query_id -> result mapping
    map_a = {qr["query_id"]: qr for qr in queries_a}
    map_b = {qr["query_id"]: qr for qr in queries_b}

    common_ids = set(map_a.keys()) & set(map_b.keys())

    for q_id in sorted(common_ids):
        qr_a = map_a[q_id]
        qr_b = map_b[q_id]

        relevant = set(qr_a.get("relevant_files", []))
        ret_a = set(qr_a.get("retrieved_files", [])[:k])
        ret_b = set(qr_b.get("retrieved_files", [])[:k])

        hit_a = len(ret_a & relevant)
        hit_b = len(ret_b & relevant)
        total_rel = len(relevant) if relevant else 1

        success_a = hit_a / total_rel >= 0.5
        success_b = hit_b / total_rel >= 0.5

        entry = {
            "query_id": q_id,
            "query_text": qr_a.get("query_text", ""),
            "trigger_type": qr_a.get("trigger_type", ""),
            f"{strategy_a}_recall": round(hit_a / total_rel, 4),
            f"{strategy_b}_recall": round(hit_b / total_rel, 4),
        }

        if success_a and not success_b:
            report.ctx_only_wins.append(entry)
        elif success_b and not success_a:
            report.baseline_only_wins.append(entry)
        elif not success_a and not success_b:
            report.both_fail.append(entry)
        else:
            report.both_succeed += 1

    total = len(common_ids)
    report.summary = (
        f"{strategy_a} vs {strategy_b} (n={total}): "
        f"{strategy_a}-only wins={len(report.ctx_only_wins)}, "
        f"{strategy_b}-only wins={len(report.baseline_only_wins)}, "
        f"both succeed={report.both_succeed}, "
        f"both fail={len(report.both_fail)}"
    )

    return report


def run_full_error_analysis(results_dir: str, dataset_label: str, k: int = 5) -> str:
    """Run full error analysis and produce markdown report.

    Args:
        results_dir: Path to benchmarks/results/
        dataset_label: e.g. "small", "real_GraphPrompt"
        k: Cutoff for evaluation

    Returns:
        Markdown report string
    """
    # Load benchmark data
    benchmark_path = os.path.join(results_dir, f"benchmark_{dataset_label}.json")
    if not os.path.exists(benchmark_path):
        return f"No benchmark data found at {benchmark_path}"

    with open(benchmark_path) as f:
        data = json.load(f)

    strategies = list(data.get("strategies", {}).keys())

    lines = [
        f"# Error Analysis: {dataset_label}",
        "",
        f"Dataset: {dataset_label}",
        f"Strategies analyzed: {', '.join(strategies)}",
        f"Evaluation cutoff: Recall@{k}",
        "",
    ]

    # Per-strategy failure analysis
    analyses = {}
    for strat in strategies:
        fa = analyze_failures(data, strat, k=k)
        analyses[strat] = fa

        lines.append(f"## {strat}")
        lines.append(f"- Total queries: {fa.total_queries}")
        lines.append(f"- Failures (Recall@{k} < 1.0): {fa.total_failures}")
        lines.append(f"- Failure rate: {fa.failure_rate():.1%}")
        lines.append("")

        if fa.pattern_counts:
            lines.append("### Failure Pattern Distribution")
            lines.append("| Pattern | Count |")
            lines.append("|---------|-------|")
            for pattern, count in sorted(fa.pattern_counts.items(), key=lambda x: -x[1]):
                lines.append(f"| {pattern} | {count} |")
            lines.append("")

        if fa.per_trigger_failures:
            lines.append("### Failures by Trigger Type")
            lines.append("| Trigger Type | Failures | Total | Failure Rate |")
            lines.append("|-------------|----------|-------|-------------|")
            for tt in sorted(fa.per_trigger_totals.keys()):
                total_tt = fa.per_trigger_totals[tt]
                fail_tt = fa.per_trigger_failures.get(tt, 0)
                rate = fail_tt / total_tt if total_tt > 0 else 0.0
                lines.append(f"| {tt} | {fail_tt} | {total_tt} | {rate:.1%} |")
            lines.append("")

        # Top failures
        top_fails = fa.top_failures(5)
        if top_fails:
            lines.append(f"### Top-5 Failure Cases")
            for fc in top_fails:
                lines.append(f"- **{fc.query_id}** ({fc.failure_type}): \"{fc.query_text[:80]}\"")
                lines.append(f"  - Missed: {', '.join(fc.missed_files[:3])}")
                lines.append(f"  - {fc.detail}")
            lines.append("")

    # Cross-strategy comparisons
    ref = "adaptive_trigger"
    if ref in strategies:
        lines.append("## Cross-Strategy Comparison")
        lines.append("")

        for baseline in ["bm25", "llamaindex", "dense_tfidf", "chroma_dense"]:
            if baseline not in strategies:
                continue

            comp = compare_strategies(data, ref, baseline, k=k)
            lines.append(f"### {ref} vs {baseline}")
            lines.append(f"- {comp.summary}")

            if comp.ctx_only_wins:
                lines.append(f"- CTX-only wins by trigger type: "
                           f"{Counter(w['trigger_type'] for w in comp.ctx_only_wins)}")
            if comp.baseline_only_wins:
                lines.append(f"- {baseline}-only wins by trigger type: "
                           f"{Counter(w['trigger_type'] for w in comp.baseline_only_wins)}")

            # Show examples of CTX-only wins (IMPLICIT_CONTEXT)
            implicit_wins = [w for w in comp.ctx_only_wins if w["trigger_type"] == "IMPLICIT_CONTEXT"]
            if implicit_wins:
                lines.append(f"- IMPLICIT_CONTEXT CTX-only win examples:")
                for w in implicit_wins[:3]:
                    lines.append(f"  - {w['query_id']}: \"{w['query_text'][:60]}\" "
                               f"(CTX={w.get(f'{ref}_recall', 0):.2f}, "
                               f"{baseline}={w.get(f'{baseline}_recall', 0):.2f})")

            lines.append("")

    report_text = "\n".join(lines)

    # Save report
    output_path = os.path.join(results_dir, "error_analysis.md")
    with open(output_path, "w") as f:
        f.write(report_text)

    return report_text
