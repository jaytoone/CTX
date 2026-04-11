# G1 Long-Term Memory Evaluation — Implementation Design
**Date**: 2026-04-08  **Type**: Implementation Specification

Based on: `docs/research/20260408-g1-longterm-memory-evaluation-framework.md`

---

## Design Overview

**Goal**: Measure CTX G1's ability to retain and recall important decision history over time, with focus on temporal reasoning and conflict resolution beyond simple keyword recall.

**Architecture**: Semi-automated benchmark generation from git history + hybrid scoring (deterministic + LLM judge)

---

## 1. Query Type Taxonomy

| Type | Example | Difficulty | Capability Measured | Auto-Generable? |
|------|---------|------------|---------------------|-----------------|
| **Type 1: Single-hop fact** | "When did we switch to BM25?" | LOW | Information extraction | YES (from commit timestamp) |
| **Type 2: Rationale recall** | "Why did we switch to BM25?" | MEDIUM | Decision reasoning | SEMI (commit message → extract rationale) |
| **Type 3: Multi-hop chain** | "Why was external R@5 low and what decision addressed it?" | HIGH | Causal reasoning | NO (requires manual annotation) |
| **Type 4: Conflict resolution** | "What's the latest decision on external retrieval approach?" (after multiple direction changes) | HIGH | Knowledge update | SEMI (detect conflicts automatically, judge manually) |

**Phase 1 scope**: Type 1 + Type 2 (auto + semi-auto)
**Phase 2 scope**: Type 3 + Type 4 (manual annotation required)

---

## 2. Ground Truth Construction Pipeline

### Step 1: Decision Commit Extraction (Automated)

```python
def extract_decision_commits(repo_path, cutoff_date=None):
    """
    Extract decision commits from git log using CTX's existing patterns.

    Args:
        repo_path: Path to git repository
        cutoff_date: Evaluation cutoff (SWE-bench style temporal isolation)

    Returns:
        List[DecisionCommit] with fields:
            - hash: commit hash
            - date: commit datetime
            - subject: commit message first line
            - body: commit message body
            - files_changed: list of file paths
            - decision_type: feat/fix/refactor/... (from commit pattern)
    """
    # Use git-memory.py's decision detection patterns
    DECISION_PATTERNS = [
        r"^feat:",
        r"^fix:",
        r"^refactor:",
        r"^v\d+\.\d+\.\d+ - (feat|fix|refactor)",
    ]

    # Filter commits after cutoff_date if specified
    # Parse git log --format="%H|%aI|%s|%b" --name-only
    pass
```

**Output**: `benchmarks/results/g1_decision_commits.json`

### Step 2: QA Pair Generation (Semi-Automated)

```python
def generate_qa_pairs(decision_commits, query_types=["type1", "type2"]):
    """
    Generate QA pairs from decision commits.

    Type 1 (automated): timestamp/hash queries
    Type 2 (LLM-assisted): rationale extraction from commit message

    Returns:
        List[QAPair] with fields:
            - query: question text
            - query_type: "type1" | "type2" | "type3" | "type4"
            - ground_truth: {
                "commit_hash": str,
                "timestamp": datetime,
                "rationale": str (for type2),
                "decision_chain": List[str] (for type3),
                "conflict_resolution": str (for type4)
              }
            - age_bucket: "0-7d" | "7-30d" | "30-90d" | "90d+"
    """
    qa_pairs = []

    for commit in decision_commits:
        # Type 1: Simple fact query
        qa_pairs.append({
            "query": f"When did we implement {extract_topic(commit)}?",
            "query_type": "type1",
            "ground_truth": {
                "commit_hash": commit.hash,
                "timestamp": commit.date,
            },
            "age_bucket": compute_age_bucket(commit.date),
        })

        # Type 2: Rationale query (LLM-assisted extraction)
        if has_meaningful_message(commit):
            rationale = extract_rationale_llm(commit.body)
            qa_pairs.append({
                "query": f"Why did we {extract_action(commit)}?",
                "query_type": "type2",
                "ground_truth": {
                    "commit_hash": commit.hash,
                    "rationale": rationale,
                },
                "age_bucket": compute_age_bucket(commit.date),
            })

    return qa_pairs
```

**Output**: `benchmarks/results/g1_qa_pairs.json`

**Manual review**: Sample 30-50 QA pairs for quality validation

---

## 3. Evaluation Metrics

### 3.1 Decision Recall@K (Deterministic)

```python
def compute_decision_recall(ctx_output, ground_truth, k=5):
    """
    Metric: (GT decisions in CTX top-K) / (total GT decisions for this query)

    Args:
        ctx_output: List of commit hashes returned by CTX
        ground_truth: List of expected commit hashes
        k: top-K to consider

    Returns:
        float: recall@K score
    """
    ctx_top_k = set(ctx_output[:k])
    gt_set = set(ground_truth)

    if len(gt_set) == 0:
        return 0.0

    return len(ctx_top_k & gt_set) / len(gt_set)
```

### 3.2 Rationale F1 (Hybrid: Deterministic + LLM)

```python
def compute_rationale_f1(ctx_rationale, gt_rationale, llm_judge_fn):
    """
    Hybrid scoring: 0.5 × keyword_overlap + 0.5 × llm_semantic_score

    Args:
        ctx_rationale: CTX's extracted rationale text
        gt_rationale: Ground truth rationale
        llm_judge_fn: LLM judge function (ctx, gt) -> score [0, 1]

    Returns:
        float: hybrid F1 score
    """
    # Deterministic component: keyword overlap
    ctx_keywords = extract_keywords(ctx_rationale)
    gt_keywords = extract_keywords(gt_rationale)

    if len(ctx_keywords) + len(gt_keywords) == 0:
        keyword_f1 = 0.0
    else:
        precision = len(ctx_keywords & gt_keywords) / len(ctx_keywords) if ctx_keywords else 0
        recall = len(ctx_keywords & gt_keywords) / len(gt_keywords) if gt_keywords else 0
        keyword_f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # LLM component: semantic equivalence
    llm_score = llm_judge_fn(ctx_rationale, gt_rationale)

    # Hybrid
    return 0.5 * keyword_f1 + 0.5 * llm_score
```

### 3.3 Temporal Order Accuracy (Deterministic)

```python
def compute_temporal_order_accuracy(ctx_output, decision_pairs):
    """
    For pairs of decisions with temporal ordering, check if CTX returns them in correct order.

    Args:
        ctx_output: List of (commit_hash, timestamp) tuples from CTX
        decision_pairs: List of (older_hash, newer_hash) pairs with ground truth ordering

    Returns:
        float: fraction of pairs with correct ordering
    """
    correct = 0
    total = len(decision_pairs)

    ctx_order = {commit: idx for idx, (commit, _) in enumerate(ctx_output)}

    for older, newer in decision_pairs:
        if older in ctx_order and newer in ctx_order:
            if ctx_order[older] < ctx_order[newer]:  # older appears before newer
                correct += 1

    return correct / total if total > 0 else 0.0
```

### 3.4 Conflict Resolution Accuracy (LLM Judge)

```python
def compute_conflict_resolution_accuracy(ctx_output, conflict_groups, llm_judge_fn):
    """
    For groups of conflicting decisions, check if CTX selects the latest one.

    Args:
        ctx_output: CTX's decision output
        conflict_groups: List of conflict groups, each is List[(commit_hash, timestamp)]
        llm_judge_fn: LLM judge to verify selection correctness

    Returns:
        float: fraction of conflict groups resolved correctly
    """
    correct = 0
    total = len(conflict_groups)

    for group in conflict_groups:
        latest_decision = max(group, key=lambda x: x[1])  # latest by timestamp

        # Check if CTX output contains the latest decision
        if latest_decision[0] in [c[0] for c in ctx_output]:
            # Use LLM judge to verify it's prioritized over older conflicting ones
            if llm_judge_fn(ctx_output, group, latest_decision):
                correct += 1

    return correct / total if total > 0 else 0.0
```

### 3.5 Recall by Age Bucket (Deterministic)

```python
def compute_recall_by_age(ctx_output, qa_pairs_by_age):
    """
    Compute recall@K separately for each age bucket.

    Args:
        ctx_output: CTX decisions
        qa_pairs_by_age: Dict[age_bucket -> List[QAPair]]

    Returns:
        Dict[age_bucket -> recall_score]
    """
    results = {}

    for age_bucket, pairs in qa_pairs_by_age.items():
        total_recall = 0.0
        for pair in pairs:
            recall = compute_decision_recall(ctx_output, pair["ground_truth"]["commit_hash"])
            total_recall += recall

        results[age_bucket] = total_recall / len(pairs) if pairs else 0.0

    return results
```

---

## 4. Baseline Implementations

### 4.1 No CTX

```python
def evaluate_no_ctx(qa_pair):
    """
    Baseline: No context injection. LLM answers from its own knowledge.
    """
    prompt = f"Question: {qa_pair['query']}\nAnswer based on your knowledge of the CTX project."
    response = llm_call(prompt)
    return response
```

### 4.2 Full Git Log Dump

```python
def evaluate_full_git_log(qa_pair, repo_path):
    """
    Baseline: Dump all git log without filtering.
    """
    full_log = subprocess.run(
        ["git", "log", "--format=%H|%aI|%s", "-n", "100"],
        cwd=repo_path,
        capture_output=True,
        text=True
    ).stdout

    prompt = f"Git history:\n{full_log}\n\nQuestion: {qa_pair['query']}\nAnswer:"
    response = llm_call(prompt)
    return response
```

### 4.3 CTX Variants

```python
def evaluate_ctx_variant(qa_pair, variant="g1_filtered"):
    """
    Variants: g1_raw, g1_filtered, random_noise, g1_g2_hybrid
    """
    # Use git-memory.py with specified format
    ctx_decisions = call_git_memory(format=variant, n=30)

    prompt = f"Context:\n{ctx_decisions}\n\nQuestion: {qa_pair['query']}\nAnswer:"
    response = llm_call(prompt)
    return response
```

### 4.4 SOTA Baselines (if available)

```python
def evaluate_mem0(qa_pair):
    """
    If Mem0 API available, compare against it.
    """
    # Requires Mem0 integration
    pass
```

---

## 5. Experiment Script Structure

**File**: `benchmarks/eval/g1_longterm_eval.py`

```python
#!/usr/bin/env python3
"""
G1 Long-Term Memory Evaluation Framework

Usage:
    python g1_longterm_eval.py --repo-path /path/to/CTX --output results.json
"""

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--output", default="benchmarks/results/g1_longterm_eval.json")
    parser.add_argument("--cutoff-days", type=int, default=None, help="Temporal cutoff (days before today)")
    parser.add_argument("--query-types", nargs="+", default=["type1", "type2"])
    parser.add_argument("--baselines", nargs="+", default=["no_ctx", "full_dump", "g1_raw", "g1_filtered"])
    args = parser.parse_args()

    # Step 1: Extract decision commits
    print("[1/5] Extracting decision commits...")
    cutoff_date = datetime.now() - timedelta(days=args.cutoff_days) if args.cutoff_days else None
    decision_commits = extract_decision_commits(args.repo_path, cutoff_date)
    print(f"  Found {len(decision_commits)} decision commits")

    # Step 2: Generate QA pairs
    print("[2/5] Generating QA pairs...")
    qa_pairs = generate_qa_pairs(decision_commits, query_types=args.query_types)
    print(f"  Generated {len(qa_pairs)} QA pairs")

    # Save QA pairs for manual review
    with open("benchmarks/results/g1_qa_pairs.json", "w") as f:
        json.dump(qa_pairs, f, indent=2, default=str)

    # Step 3: Run evaluation on all baselines
    print("[3/5] Running evaluation...")
    results = {}

    for baseline in args.baselines:
        print(f"  Evaluating baseline: {baseline}")
        baseline_results = evaluate_baseline(baseline, qa_pairs, args.repo_path)
        results[baseline] = baseline_results

    # Step 4: Compute metrics
    print("[4/5] Computing metrics...")
    metrics = {}

    for baseline, baseline_results in results.items():
        metrics[baseline] = {
            "decision_recall@5": compute_mean_recall(baseline_results, k=5),
            "rationale_f1": compute_mean_rationale_f1(baseline_results),
            "temporal_order_accuracy": compute_temporal_order_accuracy_all(baseline_results),
            "recall_by_age": compute_recall_by_age_all(baseline_results),
        }

    # Step 5: Save results
    print("[5/5] Saving results...")
    output_data = {
        "metadata": {
            "repo_path": args.repo_path,
            "cutoff_date": str(cutoff_date) if cutoff_date else None,
            "query_types": args.query_types,
            "baselines": args.baselines,
            "num_qa_pairs": len(qa_pairs),
            "timestamp": datetime.now().isoformat(),
        },
        "qa_pairs": qa_pairs,
        "results": results,
        "metrics": metrics,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\nResults saved to {args.output}")
    print_summary(metrics)

if __name__ == "__main__":
    main()
```

---

## 6. Expected Output Format

**File**: `benchmarks/results/g1_longterm_eval.json`

```json
{
  "metadata": {
    "repo_path": "/home/jayone/Project/CTX",
    "cutoff_date": null,
    "query_types": ["type1", "type2"],
    "baselines": ["no_ctx", "full_dump", "g1_raw", "g1_filtered"],
    "num_qa_pairs": 28,
    "timestamp": "2026-04-08T15:30:00"
  },
  "metrics": {
    "no_ctx": {
      "decision_recall@5": 0.000,
      "rationale_f1": 0.123,
      "temporal_order_accuracy": 0.000,
      "recall_by_age": {
        "0-7d": 0.000,
        "7-30d": 0.000,
        "30-90d": 0.000,
        "90d+": 0.000
      }
    },
    "g1_filtered": {
      "decision_recall@5": 0.857,
      "rationale_f1": 0.712,
      "temporal_order_accuracy": 0.923,
      "recall_by_age": {
        "0-7d": 1.000,
        "7-30d": 0.875,
        "30-90d": 0.667,
        "90d+": 0.333
      }
    }
  }
}
```

---

## 7. Implementation Checklist

- [ ] **Phase 1A**: Implement `extract_decision_commits()` using git-memory.py patterns
- [ ] **Phase 1B**: Implement Type 1 QA pair generation (automated)
- [ ] **Phase 1C**: Implement Type 2 QA pair generation with LLM-assisted rationale extraction
- [ ] **Phase 1D**: Manual review of 30 generated QA pairs
- [ ] **Phase 2A**: Implement Decision Recall@K metric
- [ ] **Phase 2B**: Implement Rationale F1 (hybrid) metric with LLM judge
- [ ] **Phase 2C**: Implement Temporal Order Accuracy metric
- [ ] **Phase 2D**: Implement Recall by Age Bucket metric
- [ ] **Phase 3A**: Implement No CTX baseline
- [ ] **Phase 3B**: Implement Full Git Log baseline
- [ ] **Phase 3C**: Implement CTX variants (g1_raw, g1_filtered, random_noise)
- [ ] **Phase 4**: Run full evaluation on CTX repo
- [ ] **Phase 5**: Generate comparison report and visualizations
- [ ] **Phase 6** (optional): Integrate Mem0/SOTA baseline if API available

---

## 8. Success Criteria

| Criterion | Target | Rationale |
|-----------|--------|-----------|
| **QA Pair Quality** | 80% valid after manual review | Ensures ground truth reliability |
| **CTX vs No CTX delta** | ≥ +0.30 on Decision Recall@5 | Current G1 delta baseline |
| **CTX vs Full Dump delta** | ≥ +0.20 on Rationale F1 | Demonstrates filtering value |
| **Temporal Order Accuracy** | ≥ 0.85 on CTX variants | Shows temporal reasoning capability |
| **Age-bucket degradation** | Recall drop < 50% at 90d+ | Acceptable long-term retention |

---

## Related Documents

- [G1 Long-Term Memory Evaluation Framework (Research)](../research/20260408-g1-longterm-memory-evaluation-framework.md)
- [G1 Final Eval Benchmark](../research/20260407-g1-final-eval-benchmark.md)
- [G1 Temporal Retention Eval](../research/20260408-g1-temporal-retention-eval.md)

## Related
- [[projects/CTX/research/20260408-g1-longterm-memory-evaluation-framework|20260408-g1-longterm-memory-evaluation-framework]]
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260407-g1-temporal-evaluation-framework|20260407-g1-temporal-evaluation-framework]]
- [[projects/CTX/research/20260408-g1-temporal-retention-eval|20260408-g1-temporal-retention-eval]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260326-ctx-vs-sota-comparison|20260326-ctx-vs-sota-comparison]]
- [[projects/CTX/research/20260326-ctx-final-sota-comparison|20260326-ctx-final-sota-comparison]]
- [[projects/CTX/research/20260326-ctx-results-review|20260326-ctx-results-review]]
