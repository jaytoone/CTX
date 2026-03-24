"""
Compute NDCG@5 for all strategies across all datasets and calculate
TES-NDCG Pearson correlation to show TES is a cost-adjusted NDCG variant.

Uses existing per-query benchmark data from benchmarks/results/*.json.
"""

import json
import math
import os
from pathlib import Path

# Reuse project metrics
import sys
sys.path.insert(0, str(Path(__file__).parent))
from src.evaluator.metrics import ndcg_at_k, tes


RESULTS_DIR = Path(__file__).parent / "benchmarks" / "results"

BENCHMARK_FILES = {
    "Synthetic": "benchmark_small.json",
    "GraphPrompt": "benchmark_real_GraphPrompt.json",
    "OneViral": "benchmark_real_OneViral.json",
    "AgentNode": "benchmark_real_AgentNode.json",
}

STRATEGIES = [
    "full_context", "bm25", "dense_tfidf",
    "graph_rag", "adaptive_trigger", "llamaindex", "chroma_dense",
]


def compute_strategy_ndcg(per_query_results, k=5):
    """Compute mean NDCG@K from per-query results."""
    ndcg_scores = []
    for q in per_query_results:
        retrieved = q["retrieved_files"]
        relevant = q["relevant_files"]
        ndcg_scores.append(ndcg_at_k(retrieved, relevant, k))
    return sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0


def compute_strategy_tes(per_query_results):
    """Compute mean TES from per-query results."""
    tes_scores = []
    for q in per_query_results:
        retrieved = q["retrieved_files"]
        relevant = q["relevant_files"]
        recall5 = len(set(retrieved[:5]) & set(relevant)) / len(relevant) if relevant else 1.0
        t = tes(recall5, len(retrieved))
        tes_scores.append(t)
    return sum(tes_scores) / len(tes_scores) if tes_scores else 0.0


def pearson_correlation(x, y):
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return float('nan')
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    std_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
    std_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
    if std_x == 0 or std_y == 0:
        return float('nan')
    return cov / (std_x * std_y)


def t_test_correlation(r, n):
    """Compute t-statistic and approximate p-value for correlation."""
    if abs(r) >= 1.0 or n <= 2:
        return float('inf'), 0.0
    t_stat = r * math.sqrt((n - 2) / (1 - r ** 2))
    # Approximate two-tailed p-value using normal distribution for large n
    # For small n, this is a rough approximation
    df = n - 2
    # Use beta incomplete function approximation
    # For simplicity, report t-statistic and degrees of freedom
    return t_stat, df


def main():
    all_ndcg = []
    all_tes = []

    print("=" * 80)
    print("NDCG@5 and TES by Strategy and Dataset")
    print("=" * 80)

    # Header
    print(f"\n{'Dataset':<15} {'Strategy':<20} {'NDCG@5':>8} {'TES':>8} {'Recall@5':>10} {'Token%':>8}")
    print("-" * 72)

    dataset_results = {}

    for dataset_name, filename in BENCHMARK_FILES.items():
        filepath = RESULTS_DIR / filename
        if not filepath.exists():
            print(f"WARNING: {filepath} not found, skipping")
            continue

        with open(filepath) as f:
            data = json.load(f)

        per_query = data.get("_query_results", {})
        dataset_results[dataset_name] = {}

        for strategy in STRATEGIES:
            if strategy not in per_query:
                continue

            queries = per_query[strategy]
            ndcg5 = compute_strategy_ndcg(queries, k=5)
            tes5 = compute_strategy_tes(queries)

            # Also get recall@5 and token% from aggregate
            agg = data["strategies"].get(strategy, {}).get("aggregate_metrics", {})
            recall5 = agg.get("mean_recall@5", 0.0)
            token_pct = agg.get("mean_token_efficiency", 0.0)

            dataset_results[dataset_name][strategy] = {
                "ndcg5": ndcg5,
                "tes": tes5,
                "recall5": recall5,
                "token_pct": token_pct,
            }

            all_ndcg.append(ndcg5)
            all_tes.append(tes5)

            print(f"{dataset_name:<15} {strategy:<20} {ndcg5:>8.4f} {tes5:>8.4f} {recall5:>10.4f} {token_pct:>8.4f}")

    # Correlation analysis
    print("\n" + "=" * 80)
    print("TES-NDCG Pearson Correlation Analysis")
    print("=" * 80)

    r = pearson_correlation(all_ndcg, all_tes)
    t_stat, df = t_test_correlation(r, len(all_ndcg))

    print(f"\nOverall (across all datasets and strategies):")
    print(f"  N = {len(all_ndcg)} (strategy x dataset pairs)")
    print(f"  Pearson r = {r:.4f}")
    print(f"  t-statistic = {t_stat:.4f} (df={df})")

    # Per-dataset correlation
    print(f"\nPer-dataset correlation:")
    for dataset_name, strategies in dataset_results.items():
        ndcg_vals = [v["ndcg5"] for v in strategies.values()]
        tes_vals = [v["tes"] for v in strategies.values()]
        r_ds = pearson_correlation(ndcg_vals, tes_vals)
        print(f"  {dataset_name}: r = {r_ds:.4f} (n={len(ndcg_vals)})")

    # Summary table for paper
    print("\n" + "=" * 80)
    print("Summary Table: Mean NDCG@5 by Strategy (for paper)")
    print("=" * 80)
    print(f"\n{'Strategy':<20}", end="")
    for ds in BENCHMARK_FILES:
        print(f" {ds:>12}", end="")
    print(f" {'Avg':>8}")
    print("-" * 80)

    for strategy in STRATEGIES:
        print(f"{strategy:<20}", end="")
        vals = []
        for ds in BENCHMARK_FILES:
            if ds in dataset_results and strategy in dataset_results[ds]:
                v = dataset_results[ds][strategy]["ndcg5"]
                vals.append(v)
                print(f" {v:>12.4f}", end="")
            else:
                print(f" {'N/A':>12}", end="")
        avg = sum(vals) / len(vals) if vals else 0
        print(f" {avg:>8.4f}")

    # Save results as JSON for reference
    output = {
        "ndcg_by_dataset_strategy": dataset_results,
        "correlation": {
            "overall_pearson_r": r,
            "overall_t_statistic": t_stat,
            "overall_df": df,
            "overall_n": len(all_ndcg),
        },
        "per_dataset_correlation": {},
    }
    for dataset_name, strategies in dataset_results.items():
        ndcg_vals = [v["ndcg5"] for v in strategies.values()]
        tes_vals = [v["tes"] for v in strategies.values()]
        r_ds = pearson_correlation(ndcg_vals, tes_vals)
        output["per_dataset_correlation"][dataset_name] = r_ds

    output_path = RESULTS_DIR / "ndcg_tes_correlation.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
