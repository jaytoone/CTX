"""
Console-based result visualization for CTX experiment.

Produces ASCII tables comparing strategies across metrics
and tiers. No matplotlib dependency.
"""

from typing import Dict, List, Optional

from src.evaluator.benchmark_runner import BenchmarkResult


def _format_float(val: float, width: int = 8) -> str:
    """Format a float to fixed width."""
    return f"{val:.4f}".rjust(width)


def _print_table(title: str, headers: List[str], rows: List[List[str]],
                  col_width: int = 14) -> str:
    """Render an ASCII table."""
    lines = []
    lines.append("")
    lines.append(f"{'=' * (col_width * len(headers) + len(headers) + 1)}")
    lines.append(f"  {title}")
    lines.append(f"{'=' * (col_width * len(headers) + len(headers) + 1)}")

    # Header
    header_line = "|" + "|".join(h.center(col_width) for h in headers) + "|"
    lines.append(header_line)
    lines.append("|" + "|".join("-" * col_width for _ in headers) + "|")

    # Rows
    for row in rows:
        row_line = "|" + "|".join(str(cell).center(col_width) for cell in row) + "|"
        lines.append(row_line)

    lines.append(f"{'=' * (col_width * len(headers) + len(headers) + 1)}")

    text = "\n".join(lines)
    print(text)
    return text


def generate_report(benchmark: BenchmarkResult) -> str:
    """Generate a full console report from benchmark results.

    Args:
        benchmark: The complete benchmark result

    Returns:
        Full report as a string
    """
    all_output = []

    all_output.append("\n" + "=" * 70)
    all_output.append("  CTX Experiment Results Report")
    all_output.append("=" * 70)
    all_output.append(f"  Dataset size: {benchmark.dataset_size}")
    all_output.append(f"  Files: {benchmark.metadata.get('file_count', 'N/A')}")
    all_output.append(f"  Queries: {benchmark.metadata.get('query_count', 'N/A')}")
    all_output.append(f"  Tiers: {benchmark.metadata.get('tier_distribution', {})}")

    if benchmark.metadata.get("project_name"):
        all_output.append(f"  Project: {benchmark.metadata['project_name']}")

    strategies = list(benchmark.strategy_results.keys())

    # Table 1: Overall Recall@K comparison
    headers = ["Strategy"] + [f"Recall@{k}" for k in [1, 3, 5, 10]]
    rows = []
    for strat in strategies:
        sr = benchmark.strategy_results[strat]
        row = [strat]
        for k in [1, 3, 5, 10]:
            key = f"mean_recall@{k}"
            val = sr.aggregate_metrics.get(key, 0.0)
            row.append(_format_float(val))
        rows.append(row)

    text = _print_table("Overall Recall@K by Strategy", headers, rows)
    all_output.append(text)

    # Table 2: Token Efficiency comparison
    headers = ["Strategy", "Token Eff.", "TES", "Time(s)"]
    rows = []
    for strat in strategies:
        sr = benchmark.strategy_results[strat]
        tok_eff = sr.aggregate_metrics.get("mean_token_efficiency", 0.0)
        tes_val = sr.aggregate_metrics.get("mean_tes", 0.0)
        row = [strat, _format_float(tok_eff), _format_float(tes_val),
               f"{sr.elapsed_seconds:.2f}"]
        rows.append(row)

    text = _print_table("Token Efficiency & TES by Strategy", headers, rows)
    all_output.append(text)

    # Table 3: Recall@5 by Tier (Head / Torso / Tail)
    headers = ["Strategy", "Head R@5", "Torso R@5", "Tail R@5"]
    rows = []
    for strat in strategies:
        sr = benchmark.strategy_results[strat]
        tier_metrics = sr.compute_tier_aggregates(benchmark.file_tiers)
        row = [strat]
        for tier in ["head", "torso", "tail"]:
            val = tier_metrics.get(tier, {}).get("recall@5", 0.0)
            row.append(_format_float(val))
        rows.append(row)

    text = _print_table("Recall@5 by Tier (Head/Torso/Tail)", headers, rows)
    all_output.append(text)

    # Table 4: Performance by Trigger Type
    trigger_types = ["EXPLICIT_SYMBOL", "SEMANTIC_CONCEPT", "TEMPORAL_HISTORY", "IMPLICIT_CONTEXT"]
    headers = ["Strategy"] + [tt.split("_")[0][:4] + "_" + tt.split("_")[1][:4]
                               for tt in trigger_types]
    rows = []
    for strat in strategies:
        sr = benchmark.strategy_results[strat]
        row = [strat]
        for tt in trigger_types:
            key = f"mean_recall@5_{tt}"
            val = sr.aggregate_metrics.get(key, 0.0)
            row.append(_format_float(val))
        rows.append(row)

    text = _print_table("Recall@5 by Trigger Type", headers, rows)
    all_output.append(text)

    # Table 5: Downstream Quality (CCS, ASS)
    if benchmark.downstream_metrics:
        headers = ["Strategy", "CCS", "ASS"]
        rows = []
        for strat in strategies:
            dm = benchmark.downstream_metrics.get(strat, {})
            ccs = dm.get("mean_ccs", 0.0)
            ass = dm.get("mean_ass", 0.0)
            rows.append([strat, _format_float(ccs), _format_float(ass)])

        text = _print_table("Downstream Quality (CCS / ASS)", headers, rows)
        all_output.append(text)

    # Summary: Token efficiency gains of adaptive_trigger vs full_context
    full_sr = benchmark.strategy_results.get("full_context")
    adaptive_sr = benchmark.strategy_results.get("adaptive_trigger")

    if full_sr and adaptive_sr:
        full_tok = full_sr.aggregate_metrics.get("mean_token_efficiency", 1.0)
        adaptive_tok = adaptive_sr.aggregate_metrics.get("mean_token_efficiency", 1.0)
        full_recall = full_sr.aggregate_metrics.get("mean_recall@5", 0.0)
        adaptive_recall = adaptive_sr.aggregate_metrics.get("mean_recall@5", 0.0)

        all_output.append("\n" + "-" * 70)
        all_output.append("  KEY FINDINGS")
        all_output.append("-" * 70)

        if full_tok > 0:
            reduction = (1 - adaptive_tok / full_tok) * 100
            all_output.append(
                f"  Token Usage: Adaptive Trigger uses {adaptive_tok:.4f} vs "
                f"Full Context {full_tok:.4f}"
            )
            all_output.append(
                f"  Token Reduction: {reduction:.1f}% fewer tokens with Adaptive Trigger"
            )

        all_output.append(
            f"  Recall@5:   Adaptive Trigger {adaptive_recall:.4f} vs "
            f"Full Context {full_recall:.4f}"
        )

        if full_recall > 0:
            preservation = (adaptive_recall / full_recall) * 100
            all_output.append(
                f"  Accuracy Preservation: {preservation:.1f}% of Full Context recall maintained"
            )

        full_tes = full_sr.aggregate_metrics.get("mean_tes", 0.0)
        adaptive_tes = adaptive_sr.aggregate_metrics.get("mean_tes", 0.0)
        all_output.append(
            f"  TES:        Adaptive Trigger {adaptive_tes:.4f} vs "
            f"Full Context {full_tes:.4f}"
        )
        if adaptive_tes > full_tes:
            all_output.append(
                f"  --> Adaptive Trigger achieves {adaptive_tes/full_tes:.1f}x better TES"
            )

        # Downstream quality comparison
        full_dm = benchmark.downstream_metrics.get("full_context", {})
        adaptive_dm = benchmark.downstream_metrics.get("adaptive_trigger", {})
        if full_dm and adaptive_dm:
            all_output.append(
                f"  CCS:        Adaptive Trigger {adaptive_dm.get('mean_ccs', 0):.4f} vs "
                f"Full Context {full_dm.get('mean_ccs', 0):.4f}"
            )
            all_output.append(
                f"  ASS:        Adaptive Trigger {adaptive_dm.get('mean_ass', 0):.4f} vs "
                f"Full Context {full_dm.get('mean_ass', 0):.4f}"
            )

    # BM25 vs Adaptive TES comparison
    bm25_sr = benchmark.strategy_results.get("bm25")
    if bm25_sr and adaptive_sr:
        bm25_tes = bm25_sr.aggregate_metrics.get("mean_tes", 0.0)
        adaptive_tes = adaptive_sr.aggregate_metrics.get("mean_tes", 0.0)
        if bm25_tes > 0:
            all_output.append(
                f"  TES vs BM25: Adaptive {adaptive_tes:.4f} vs BM25 {bm25_tes:.4f} "
                f"({'BETTER' if adaptive_tes > bm25_tes else 'WORSE'})"
            )

    all_output.append("\n" + "=" * 70)

    report = "\n".join(all_output)
    print(report)
    return report


def save_report(benchmark: BenchmarkResult, output_path: str) -> None:
    """Generate and save report to a text file."""
    report = generate_report(benchmark)
    with open(output_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to {output_path}")
