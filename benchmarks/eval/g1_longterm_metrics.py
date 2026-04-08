#!/usr/bin/env python3
"""
G1 Long-Term Memory Metrics Implementation

Implements 5 metrics for evaluating long-term decision history recall:
1. Decision Recall@K - Did LLM retrieve correct commit info?
2. Rationale F1 - Hybrid: 0.5 deterministic keyword + 0.5 LLM judge
3. Temporal Order Accuracy - Can LLM order events correctly?
4. Conflict Resolution Accuracy - Can LLM identify decision changes?
5. Recall by Age Bucket - Performance by commit age (0-7d, 7-30d, 30-90d, 90d+)
"""

import re
from typing import Dict, List, Set
from datetime import datetime


def extract_keywords(text: str) -> Set[str]:
    """Extract keywords from text for deterministic comparison"""
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and',
                  'or', 'but', 'is', 'are', 'was', 'were', 'been', 'be', 'have',
                  'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                  'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
                  'those', 'with', 'from', 'by', 'as', 'which', 'what', 'when',
                  'where', 'who', 'why', 'how'}
    words = re.findall(r'\b\w+\b', text.lower())
    return set(w for w in words if w not in stop_words and len(w) > 2)


def compute_decision_recall_at_k(response: str, ground_truth: Dict, k: int = 5) -> float:
    """
    Metric 1: Decision Recall@K

    Check if LLM response contains the correct commit information.
    For Type 1 queries (timestamp/hash queries), check for:
    - Commit hash (first 7 chars)
    - Date mentioned (YYYY-MM-DD or similar)
    - Subject keywords

    Args:
        response: LLM response text
        ground_truth: Dict with 'commit_hash', 'timestamp', 'subject'
        k: Not used for Type 1 (included for API consistency)

    Returns:
        Binary score: 1.0 if correct info found, 0.0 otherwise
    """
    response_lower = response.lower()

    # Check for commit hash (first 7 chars)
    commit_short = ground_truth['commit_hash'][:7]
    has_commit = commit_short in response_lower

    # Check for date
    timestamp = ground_truth['timestamp']
    date_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    date_str = date_obj.strftime('%Y-%m-%d')

    # Multiple date formats to check (include both zero-padded and non-padded)
    date_formats = [
        date_str,  # 2026-04-08
        date_obj.strftime('%B %d, %Y'),  # April 08, 2026
        date_obj.strftime('%B %-d, %Y') if '%' in date_obj.strftime('%B %-d, %Y') else date_obj.strftime('%B %d, %Y').replace(' 0', ' '),  # April 8, 2026 (no zero-padding)
        date_obj.strftime('%Y/%m/%d'),  # 2026/04/08
        date_obj.strftime('%m/%d/%Y'),  # 04/08/2026
        date_obj.strftime('%Y-%m-%d'),  # Redundant but explicit
        f"{date_obj.strftime('%B')} {date_obj.day}, {date_obj.year}",  # April 8, 2026 (explicit non-padded)
    ]
    has_date = any(fmt.lower() in response_lower for fmt in date_formats)

    # Check for subject keywords (at least 2 key terms)
    subject_keywords = extract_keywords(ground_truth['subject'])
    response_keywords = extract_keywords(response)
    keyword_overlap = len(subject_keywords & response_keywords)
    has_keywords = keyword_overlap >= min(2, len(subject_keywords))

    # Score: need at least date + (commit OR keywords)
    if has_date and (has_commit or has_keywords):
        return 1.0
    return 0.0


def compute_rationale_f1_deterministic(response: str, ground_truth_rationale: str) -> float:
    """
    Metric 2a: Rationale F1 - Deterministic Component (keyword overlap)

    For Type 2 queries (rationale recall), measure keyword overlap between
    LLM response and ground truth rationale from commit body.

    Args:
        response: LLM response text
        ground_truth_rationale: Commit body text

    Returns:
        F1 score based on keyword overlap
    """
    response_keywords = extract_keywords(response)
    gt_keywords = extract_keywords(ground_truth_rationale)

    if not response_keywords or not gt_keywords:
        return 0.0

    intersection = len(response_keywords & gt_keywords)

    if intersection == 0:
        return 0.0

    precision = intersection / len(response_keywords) if response_keywords else 0
    recall = intersection / len(gt_keywords) if gt_keywords else 0

    if precision + recall == 0:
        return 0.0

    return 2 * precision * recall / (precision + recall)


def compute_rationale_f1_llm_judge(llm_client, response: str, ground_truth_rationale: str) -> float:
    """
    Metric 2b: Rationale F1 - LLM Judge Component

    Use LLM to judge semantic similarity between response and ground truth.
    Returns score 0-1.

    Args:
        llm_client: LLM client (Anthropic or compatible)
        response: LLM response text
        ground_truth_rationale: Commit body text

    Returns:
        LLM-judged similarity score 0-1
    """
    if llm_client is None:
        return 0.0

    judge_prompt = f"""You are evaluating whether an LLM response captures the rationale from a git commit message.

Ground Truth Rationale (from commit body):
{ground_truth_rationale}

LLM Response:
{response}

Rate how well the response captures the key reasoning from the ground truth.
Score 0.0 = completely unrelated
Score 0.5 = partially captures main ideas
Score 1.0 = fully captures the rationale

Output ONLY a number between 0.0 and 1.0, nothing else."""

    try:
        import anthropic
        resp = llm_client.messages.create(
            model="MiniMax-M2.5",
            max_tokens=10,
            messages=[{"role": "user", "content": judge_prompt}],
        )

        # Extract score from response
        for block in resp.content:
            if hasattr(block, "text"):
                text = block.text.strip()
                # Extract first number
                match = re.search(r'([0-1]\.\d+|[0-1])', text)
                if match:
                    return float(match.group(1))
        return 0.0
    except Exception as e:
        print(f"  [WARN] LLM judge failed: {e}")
        return 0.0


def compute_rationale_f1_hybrid(
    llm_client,
    response: str,
    ground_truth_rationale: str,
    alpha: float = 0.5
) -> float:
    """
    Metric 2: Rationale F1 - Hybrid Score

    Combines deterministic keyword overlap + LLM judge:
    hybrid_score = alpha * deterministic + (1 - alpha) * llm_judge

    Default alpha=0.5 gives equal weight.

    Args:
        llm_client: LLM client
        response: LLM response text
        ground_truth_rationale: Commit body text
        alpha: Weight for deterministic component (0-1)

    Returns:
        Hybrid F1 score
    """
    det_score = compute_rationale_f1_deterministic(response, ground_truth_rationale)
    llm_score = compute_rationale_f1_llm_judge(llm_client, response, ground_truth_rationale)

    return alpha * det_score + (1 - alpha) * llm_score


def compute_temporal_order_accuracy(responses: List[Dict]) -> float:
    """
    Metric 3: Temporal Order Accuracy

    For multi-commit queries, check if LLM orders events correctly.
    (Not implemented in Phase 1 - requires Type 3 queries)

    Args:
        responses: List of evaluation results with temporal ordering

    Returns:
        Accuracy score (0-1)
    """
    # Placeholder - requires Type 3 query implementation
    return 0.0


def compute_conflict_resolution_accuracy(responses: List[Dict]) -> float:
    """
    Metric 4: Conflict Resolution Accuracy

    Check if LLM correctly identifies when decisions changed over time.
    (Not implemented in Phase 1 - requires Type 4 queries)

    Args:
        responses: List of evaluation results with conflicts

    Returns:
        Accuracy score (0-1)
    """
    # Placeholder - requires Type 4 query implementation
    return 0.0


def compute_recall_by_age_bucket(
    results: Dict[str, List[Dict]],
    age_buckets: List[str] = ["0-7d", "7-30d", "30-90d", "90d+"]
) -> Dict[str, Dict[str, float]]:
    """
    Metric 5: Recall by Age Bucket

    Break down Decision Recall@K by commit age to measure temporal decay.

    Args:
        results: Baseline results dict with lists of evaluation results
        age_buckets: List of age bucket labels

    Returns:
        Dict mapping baseline -> {age_bucket -> recall_score}
    """
    age_bucket_scores = {}

    for baseline_name, baseline_results in results.items():
        age_bucket_scores[baseline_name] = {}

        for bucket in age_buckets:
            bucket_results = [r for r in baseline_results if r.get('age_bucket') == bucket]

            if not bucket_results:
                age_bucket_scores[baseline_name][bucket] = None
                continue

            recalls = []
            for result in bucket_results:
                if 'ground_truth' in result:
                    recall = compute_decision_recall_at_k(
                        result['response'],
                        result['ground_truth']
                    )
                    recalls.append(recall)

            if recalls:
                age_bucket_scores[baseline_name][bucket] = sum(recalls) / len(recalls)
            else:
                age_bucket_scores[baseline_name][bucket] = None

    return age_bucket_scores


def evaluate_all_metrics(
    baseline_results: Dict[str, List[Dict]],
    llm_client=None
) -> Dict:
    """
    Compute all metrics across all baselines.

    Args:
        baseline_results: Dict mapping baseline name -> list of evaluation results
        llm_client: LLM client for hybrid Rationale F1

    Returns:
        Dict with metric scores for each baseline
    """
    metrics = {}

    for baseline_name, results in baseline_results.items():
        metrics[baseline_name] = {
            "decision_recall_at_5": [],
            "rationale_f1_deterministic": [],
            "rationale_f1_hybrid": [],
            "temporal_order_accuracy": 0.0,  # Placeholder
            "conflict_resolution_accuracy": 0.0,  # Placeholder
        }

        for result in results:
            query_type = result.get('query_type', 'type1')

            # Metric 1: Decision Recall@K (Type 1 queries)
            if query_type == 'type1' and 'ground_truth' in result:
                recall = compute_decision_recall_at_k(
                    result['response'],
                    result['ground_truth']
                )
                metrics[baseline_name]['decision_recall_at_5'].append(recall)

            # Metric 2: Rationale F1 (Type 2 queries)
            if query_type == 'type2' and 'ground_truth' in result:
                gt_rationale = result['ground_truth'].get('rationale', '')

                det_f1 = compute_rationale_f1_deterministic(
                    result['response'],
                    gt_rationale
                )
                metrics[baseline_name]['rationale_f1_deterministic'].append(det_f1)

                if llm_client:
                    hybrid_f1 = compute_rationale_f1_hybrid(
                        llm_client,
                        result['response'],
                        gt_rationale
                    )
                    metrics[baseline_name]['rationale_f1_hybrid'].append(hybrid_f1)

        # Compute averages
        if metrics[baseline_name]['decision_recall_at_5']:
            metrics[baseline_name]['decision_recall_at_5_mean'] = \
                sum(metrics[baseline_name]['decision_recall_at_5']) / \
                len(metrics[baseline_name]['decision_recall_at_5'])
        else:
            metrics[baseline_name]['decision_recall_at_5_mean'] = 0.0

        if metrics[baseline_name]['rationale_f1_deterministic']:
            metrics[baseline_name]['rationale_f1_deterministic_mean'] = \
                sum(metrics[baseline_name]['rationale_f1_deterministic']) / \
                len(metrics[baseline_name]['rationale_f1_deterministic'])
        else:
            metrics[baseline_name]['rationale_f1_deterministic_mean'] = 0.0

        if metrics[baseline_name]['rationale_f1_hybrid']:
            metrics[baseline_name]['rationale_f1_hybrid_mean'] = \
                sum(metrics[baseline_name]['rationale_f1_hybrid']) / \
                len(metrics[baseline_name]['rationale_f1_hybrid'])
        else:
            metrics[baseline_name]['rationale_f1_hybrid_mean'] = 0.0

    # Metric 5: Age bucket breakdown
    metrics['age_bucket_breakdown'] = compute_recall_by_age_bucket(baseline_results)

    return metrics


# Test
if __name__ == "__main__":
    # Test with sample data
    sample_response = "The feature was implemented on 2026-04-08 in commit b2a9bf3. " \
                      "This added temporal retention to track age-based recall decay."

    sample_gt = {
        "commit_hash": "b2a9bf34c4773832496e95d4057c966fed882f28",
        "timestamp": "2026-04-08T13:00:27+09:00",
        "subject": "G1 temporal retention: age-based recall decay curve"
    }

    recall = compute_decision_recall_at_k(sample_response, sample_gt)
    print(f"Decision Recall@K: {recall}")

    det_f1 = compute_rationale_f1_deterministic(
        sample_response,
        "Implemented age-based recall decay curve for temporal retention analysis"
    )
    print(f"Rationale F1 (deterministic): {det_f1:.3f}")
