"""
Evaluation metrics for CTX experiment.

Implements:
- Trigger Recall@K
- Precision@K
- Token Efficiency Ratio
- TES (Trade-off Efficiency Score)
"""

import math
from typing import Dict, List


def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Compute Recall@K: fraction of relevant items found in top-k retrieved.

    Args:
        retrieved: Ordered list of retrieved file paths
        relevant: List of ground-truth relevant file paths
        k: Cutoff

    Returns:
        Recall score in [0.0, 1.0]
    """
    if not relevant:
        return 1.0  # No relevant items means perfect recall by convention
    top_k = set(retrieved[:k])
    relevant_set = set(relevant)
    return len(top_k & relevant_set) / len(relevant_set)


def precision_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Compute Precision@K: fraction of top-k retrieved items that are relevant.

    Args:
        retrieved: Ordered list of retrieved file paths
        relevant: List of ground-truth relevant file paths
        k: Cutoff

    Returns:
        Precision score in [0.0, 1.0]
    """
    if k == 0:
        return 0.0
    top_k = set(retrieved[:k])
    relevant_set = set(relevant)
    return len(top_k & relevant_set) / min(k, len(retrieved)) if retrieved else 0.0


def token_efficiency(tokens_used: int, total_tokens: int) -> float:
    """Compute Token Efficiency Ratio.

    Lower is better -- represents fraction of total tokens used.

    Args:
        tokens_used: Number of tokens loaded
        total_tokens: Total tokens in codebase

    Returns:
        Ratio in [0.0, 1.0]
    """
    if total_tokens == 0:
        return 0.0
    return tokens_used / total_tokens


def tes(accuracy: float, files_loaded: int) -> float:
    """Compute Trade-off Efficiency Score (TES).

    Higher is better -- accuracy divided by log of files loaded.
    Based on CAR paper's approach.

    Args:
        accuracy: Recall or precision score
        files_loaded: Number of files loaded

    Returns:
        TES score
    """
    if files_loaded <= 0:
        return 0.0
    return accuracy / math.log(1 + files_loaded)


def dcg_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Compute Discounted Cumulative Gain at K.

    Args:
        retrieved: Ordered list of retrieved file paths
        relevant: List of ground-truth relevant file paths
        k: Cutoff

    Returns:
        DCG score
    """
    relevant_set = set(relevant)
    dcg = 0.0
    for i, doc in enumerate(retrieved[:k]):
        if doc in relevant_set:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because rank starts at 1, log2(1)=0
    return dcg


def ndcg_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    """Compute Normalized Discounted Cumulative Gain at K.

    NDCG = DCG@K / IDCG@K, where IDCG is the DCG of a perfect ranking.
    Uses binary relevance (1 if relevant, 0 otherwise).

    Args:
        retrieved: Ordered list of retrieved file paths
        relevant: List of ground-truth relevant file paths
        k: Cutoff

    Returns:
        NDCG score in [0.0, 1.0]
    """
    if not relevant:
        return 1.0  # No relevant items means perfect ranking by convention

    dcg = dcg_at_k(retrieved, relevant, k)

    # Ideal DCG: all relevant items ranked first
    ideal_k = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_k))

    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def compute_all_metrics(
    retrieved: List[str],
    relevant: List[str],
    tokens_used: int,
    total_tokens: int,
    k_values: List[int] = None,
) -> Dict:
    """Compute all metrics for a single query result.

    Args:
        retrieved: Ordered list of retrieved file paths
        relevant: Ground-truth relevant file paths
        tokens_used: Tokens used by the retrieval
        total_tokens: Total tokens in codebase
        k_values: List of K values to evaluate

    Returns:
        Dictionary of all metric values
    """
    if k_values is None:
        k_values = [1, 3, 5, 10]

    results = {}

    for k in k_values:
        results[f"recall@{k}"] = recall_at_k(retrieved, relevant, k)
        results[f"precision@{k}"] = precision_at_k(retrieved, relevant, k)
        results[f"ndcg@{k}"] = ndcg_at_k(retrieved, relevant, k)

    results["token_efficiency"] = token_efficiency(tokens_used, total_tokens)
    results["tes"] = tes(
        results.get("recall@5", 0.0),
        len(retrieved),
    )

    return results
