"""
Statistical significance tests for CTX experiment.

Implements:
1. Bootstrap 95% confidence intervals (n=1000)
2. McNemar test (binary success/failure comparison)
3. Wilcoxon signed-rank test (nonparametric Recall@K distribution comparison)
"""

import numpy as np
from typing import Dict, List, Tuple

from scipy import stats


def bootstrap_ci(
    scores: List[float],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Compute bootstrap confidence interval.

    Args:
        scores: List of per-query metric scores
        n_bootstrap: Number of bootstrap resamples
        ci: Confidence level (default 0.95 for 95% CI)
        seed: Random seed for reproducibility

    Returns:
        (mean, lower_bound, upper_bound)
    """
    if not scores:
        return (0.0, 0.0, 0.0)

    rng = np.random.RandomState(seed)
    arr = np.array(scores)
    n = len(arr)

    bootstrap_means = np.array([
        np.mean(rng.choice(arr, size=n, replace=True))
        for _ in range(n_bootstrap)
    ])

    alpha = (1 - ci) / 2
    lower = float(np.percentile(bootstrap_means, alpha * 100))
    upper = float(np.percentile(bootstrap_means, (1 - alpha) * 100))
    mean = float(np.mean(arr))

    return (mean, lower, upper)


def mcnemar_test(
    results_a: List[bool],
    results_b: List[bool],
) -> Tuple[float, float]:
    """McNemar test for paired binary outcomes.

    Compares two strategies on the same set of queries.
    Each entry is True (success) or False (failure).

    Args:
        results_a: Binary outcomes for strategy A (per query)
        results_b: Binary outcomes for strategy B (per query)

    Returns:
        (statistic, p_value)
    """
    if len(results_a) != len(results_b):
        raise ValueError("Both result lists must have the same length")

    # Build contingency table
    # b = A correct, B wrong
    # c = A wrong, B correct
    b = sum(1 for a, bv in zip(results_a, results_b) if a and not bv)
    c = sum(1 for a, bv in zip(results_a, results_b) if not a and bv)

    # McNemar test with continuity correction
    if b + c == 0:
        return (0.0, 1.0)

    statistic = (abs(b - c) - 1) ** 2 / (b + c)
    p_value = float(1.0 - stats.chi2.cdf(statistic, df=1))

    return (float(statistic), p_value)


def wilcoxon_test(
    scores_a: List[float],
    scores_b: List[float],
) -> Tuple[float, float]:
    """Wilcoxon signed-rank test for paired continuous outcomes.

    Nonparametric test comparing two related samples.

    Args:
        scores_a: Per-query scores for strategy A
        scores_b: Per-query scores for strategy B

    Returns:
        (statistic, p_value)
    """
    if len(scores_a) != len(scores_b):
        raise ValueError("Both score lists must have the same length")

    arr_a = np.array(scores_a)
    arr_b = np.array(scores_b)
    diff = arr_a - arr_b

    # Remove zero differences (ties)
    nonzero = diff != 0
    if not np.any(nonzero):
        return (0.0, 1.0)

    try:
        stat, p_val = stats.wilcoxon(arr_a[nonzero], arr_b[nonzero])
        return (float(stat), float(p_val))
    except ValueError:
        # Too few samples
        return (0.0, 1.0)


def compute_statistical_summary(
    strategy_query_scores: Dict[str, List[float]],
    reference_strategy: str = "adaptive_trigger",
    metric_name: str = "recall@5",
    threshold: float = 0.0,
) -> Dict:
    """Compute full statistical summary for all strategies.

    Args:
        strategy_query_scores: Dict mapping strategy name -> list of per-query scores
        reference_strategy: Strategy to compare others against
        metric_name: Name of the metric being compared
        threshold: Threshold for binary success (score > threshold)

    Returns:
        Dict with CI, McNemar, Wilcoxon results for each strategy pair
    """
    summary = {
        "metric": metric_name,
        "reference": reference_strategy,
        "confidence_intervals": {},
        "pairwise_tests": {},
    }

    # Bootstrap CI for each strategy
    for strat_name, scores in strategy_query_scores.items():
        mean, lower, upper = bootstrap_ci(scores)
        summary["confidence_intervals"][strat_name] = {
            "mean": round(mean, 4),
            "ci_lower": round(lower, 4),
            "ci_upper": round(upper, 4),
            "n": len(scores),
        }

    # Pairwise tests against reference
    ref_scores = strategy_query_scores.get(reference_strategy)
    if ref_scores is None:
        return summary

    for strat_name, scores in strategy_query_scores.items():
        if strat_name == reference_strategy:
            continue
        if len(scores) != len(ref_scores):
            continue

        # McNemar (binary: score > threshold)
        ref_binary = [s > threshold for s in ref_scores]
        other_binary = [s > threshold for s in scores]
        mcnemar_stat, mcnemar_p = mcnemar_test(ref_binary, other_binary)

        # Wilcoxon
        wilcoxon_stat, wilcoxon_p = wilcoxon_test(ref_scores, scores)

        summary["pairwise_tests"][strat_name] = {
            "mcnemar_statistic": round(mcnemar_stat, 4),
            "mcnemar_p_value": round(mcnemar_p, 6),
            "mcnemar_significant": mcnemar_p < 0.05,
            "wilcoxon_statistic": round(wilcoxon_stat, 4),
            "wilcoxon_p_value": round(wilcoxon_p, 6),
            "wilcoxon_significant": wilcoxon_p < 0.05,
        }

    return summary
