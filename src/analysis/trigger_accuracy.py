"""
Trigger Classifier Accuracy Analysis

- Ground truth: query의 실제 의도를 trigger type으로 수동 레이블링 (규칙 기반 대리 레이블)
- Confusion matrix 4x4 계산
- Per-class precision/recall/F1
- Misclassification analysis (어떤 케이스가 오분류되는가)
"""

import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.trigger.trigger_classifier import TriggerClassifier, TriggerType


# Ground truth labeling rules (proxy labels based on query surface patterns)
GROUND_TRUTH_RULES = {
    "EXPLICIT_SYMBOL": [
        # Function/class names in backticks or quotes
        re.compile(r'`[a-zA-Z_][a-zA-Z0-9_.]+`'),
        # "Find the function X", "Show the class X"
        re.compile(r'\b(find|show|locate|where\s+is)\s+(the\s+)?(function|method|class|variable)\b', re.IGNORECASE),
        # Direct function/class name references with underscores (e.g., authenticate_user)
        re.compile(r'\b(function|class|method|definition|implementation|signature)\s+\w+', re.IGNORECASE),
    ],
    "IMPLICIT_CONTEXT": [
        re.compile(r'\b(import|depend|module|related\s+modules|needed\s+to\s+fully\s+understand|dependencies|required\s+by)\b', re.IGNORECASE),
        re.compile(r'\bwhat\s+modules\s+are\s+needed\b', re.IGNORECASE),
        re.compile(r'\b(imports|calls|uses|affects|impact|connected)\b', re.IGNORECASE),
    ],
    "TEMPORAL_HISTORY": [
        re.compile(r'\b(recent|last|changed|previously|before|last\s+time|earlier|remember|discussed|mentioned|we\s+talked|history|past|ago|lately|prior)\b', re.IGNORECASE),
    ],
    "SEMANTIC_CONCEPT": [
        re.compile(r'\b(how|why|overview|explain|related\s+to|about|concept|all\s+code|everything\s+about|functionality|feature|handles|responsible\s+for|deals\s+with)\b', re.IGNORECASE),
    ],
}

# Priority order for ground truth assignment (more specific first)
GROUND_TRUTH_PRIORITY = [
    "EXPLICIT_SYMBOL",
    "TEMPORAL_HISTORY",
    "IMPLICIT_CONTEXT",
    "SEMANTIC_CONCEPT",
]


@dataclass
class MisclassifiedCase:
    """A single misclassification instance."""
    query_text: str
    ground_truth: str
    predicted: str
    confidence: float
    detail: str = ""


@dataclass
class TriggerAccuracyResult:
    """Complete trigger accuracy analysis result."""
    total_queries: int = 0
    correct: int = 0
    accuracy: float = 0.0
    confusion_matrix: Dict[str, Dict[str, int]] = field(default_factory=dict)
    per_class_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    misclassified_examples: List[MisclassifiedCase] = field(default_factory=list)


def assign_ground_truth(query_text: str, labeled_trigger_type: str = None) -> str:
    """Assign ground truth trigger type using rule-based proxy labeling.

    Uses a priority-based matching system:
    1. EXPLICIT_SYMBOL: queries containing function/class names, backticks, etc.
    2. TEMPORAL_HISTORY: queries with temporal keywords (recent, last, changed, etc.)
    3. IMPLICIT_CONTEXT: queries about imports, dependencies, modules
    4. SEMANTIC_CONCEPT: everything else (how, why, overview, explain)

    Args:
        query_text: The query text to classify
        labeled_trigger_type: Optional pre-existing label (used as hint)

    Returns:
        Ground truth trigger type string
    """
    query_lower = query_text.lower()

    # Check each category in priority order
    for trigger_type in GROUND_TRUTH_PRIORITY:
        patterns = GROUND_TRUTH_RULES[trigger_type]
        for pattern in patterns:
            if pattern.search(query_text):
                return trigger_type

    # Default fallback
    return "SEMANTIC_CONCEPT"


def compute_confusion_matrix(
    ground_truths: List[str],
    predictions: List[str],
    labels: List[str],
) -> Dict[str, Dict[str, int]]:
    """Compute confusion matrix.

    Args:
        ground_truths: List of ground truth labels
        predictions: List of predicted labels
        labels: All possible label values

    Returns:
        Nested dict: matrix[true_label][predicted_label] = count
    """
    matrix = {true_l: {pred_l: 0 for pred_l in labels} for true_l in labels}
    for gt, pred in zip(ground_truths, predictions):
        if gt in matrix and pred in matrix[gt]:
            matrix[gt][pred] += 1
    return matrix


def compute_per_class_metrics(
    confusion_matrix: Dict[str, Dict[str, int]],
    labels: List[str],
) -> Dict[str, Dict[str, float]]:
    """Compute precision, recall, F1 for each class.

    Args:
        confusion_matrix: matrix[true_label][predicted_label] = count
        labels: All possible label values

    Returns:
        Dict of label -> {precision, recall, f1, support}
    """
    metrics = {}
    for label in labels:
        # True positives: correctly predicted as this class
        tp = confusion_matrix[label][label]

        # False positives: other classes predicted as this class
        fp = sum(confusion_matrix[other][label] for other in labels if other != label)

        # False negatives: this class predicted as other classes
        fn = sum(confusion_matrix[label][other] for other in labels if other != label)

        # Support: total instances of this class
        support = sum(confusion_matrix[label].values())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    return metrics


def run_trigger_accuracy_analysis(
    metadata_path: str = None,
    queries: List[Dict] = None,
    seed: int = 42,
) -> TriggerAccuracyResult:
    """Run the full trigger accuracy analysis.

    Args:
        metadata_path: Path to metadata.json with queries
        queries: Alternatively, pass queries directly
        seed: Random seed for sampling misclassified examples

    Returns:
        TriggerAccuracyResult with confusion matrix and metrics
    """
    random.seed(seed)
    classifier = TriggerClassifier()
    labels = ["EXPLICIT_SYMBOL", "SEMANTIC_CONCEPT", "TEMPORAL_HISTORY", "IMPLICIT_CONTEXT"]

    # Load queries
    if queries is None and metadata_path is not None:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        queries = metadata["queries"]
    elif queries is None:
        raise ValueError("Either metadata_path or queries must be provided")

    ground_truths = []
    predictions = []
    confidences = []
    misclassified = []

    for query_data in queries:
        q_text = query_data["text"]
        labeled_type = query_data.get("trigger_type", None)

        # Assign ground truth using rule-based proxy
        gt = assign_ground_truth(q_text, labeled_type)

        # Get classifier prediction
        triggers = classifier.classify(q_text)
        pred = triggers[0].trigger_type.value if triggers else "SEMANTIC_CONCEPT"
        conf = triggers[0].confidence if triggers else 0.0

        ground_truths.append(gt)
        predictions.append(pred)
        confidences.append(conf)

        if gt != pred:
            misclassified.append(MisclassifiedCase(
                query_text=q_text,
                ground_truth=gt,
                predicted=pred,
                confidence=conf,
                detail=f"Labeled as '{labeled_type}' in dataset" if labeled_type else "",
            ))

    # Compute confusion matrix
    cm = compute_confusion_matrix(ground_truths, predictions, labels)

    # Compute per-class metrics
    per_class = compute_per_class_metrics(cm, labels)

    # Sample misclassified examples
    if len(misclassified) > 5:
        sampled_misclassified = random.sample(misclassified, 5)
    else:
        sampled_misclassified = misclassified

    total = len(queries)
    correct = sum(1 for gt, pred in zip(ground_truths, predictions) if gt == pred)
    accuracy = correct / total if total > 0 else 0.0

    return TriggerAccuracyResult(
        total_queries=total,
        correct=correct,
        accuracy=accuracy,
        confusion_matrix=cm,
        per_class_metrics=per_class,
        misclassified_examples=sampled_misclassified,
    )


def format_confusion_matrix(cm: Dict[str, Dict[str, int]], labels: List[str]) -> str:
    """Format confusion matrix as a readable markdown table."""
    # Header
    short_labels = {
        "EXPLICIT_SYMBOL": "EXPLICIT",
        "SEMANTIC_CONCEPT": "SEMANTIC",
        "TEMPORAL_HISTORY": "TEMPORAL",
        "IMPLICIT_CONTEXT": "IMPLICIT",
    }

    header = "| True \\\\ Pred | " + " | ".join(short_labels.get(l, l) for l in labels) + " | Total |"
    separator = "|" + "|".join(["---"] * (len(labels) + 2)) + "|"

    rows = [header, separator]
    for true_label in labels:
        row_vals = [str(cm[true_label][pred_label]) for pred_label in labels]
        total = sum(cm[true_label].values())
        row = f"| **{short_labels.get(true_label, true_label)}** | " + " | ".join(row_vals) + f" | {total} |"
        rows.append(row)

    return "\n".join(rows)


def format_per_class_metrics(metrics: Dict[str, Dict[str, float]]) -> str:
    """Format per-class metrics as a markdown table."""
    header = "| Trigger Type | Precision | Recall | F1 | Support |"
    separator = "|---|---|---|---|---|"
    rows = [header, separator]

    short_labels = {
        "EXPLICIT_SYMBOL": "EXPLICIT_SYMBOL",
        "SEMANTIC_CONCEPT": "SEMANTIC_CONCEPT",
        "TEMPORAL_HISTORY": "TEMPORAL_HISTORY",
        "IMPLICIT_CONTEXT": "IMPLICIT_CONTEXT",
    }

    macro_p, macro_r, macro_f1 = 0.0, 0.0, 0.0
    n_classes = 0
    total_correct = 0
    total_support = 0

    for label, m in metrics.items():
        rows.append(
            f"| {short_labels.get(label, label)} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {int(m['support'])} |"
        )
        macro_p += m["precision"]
        macro_r += m["recall"]
        macro_f1 += m["f1"]
        n_classes += 1
        total_correct += int(m["precision"] * (m["support"] if m["recall"] > 0 else 0))
        total_support += int(m["support"])

    if n_classes > 0:
        rows.append(f"| **Macro Avg** | {macro_p / n_classes:.4f} | {macro_r / n_classes:.4f} | {macro_f1 / n_classes:.4f} | {total_support} |")

    return "\n".join(rows)


def generate_report(result: TriggerAccuracyResult) -> str:
    """Generate full markdown report."""
    labels = ["EXPLICIT_SYMBOL", "SEMANTIC_CONCEPT", "TEMPORAL_HISTORY", "IMPLICIT_CONTEXT"]

    lines = []
    lines.append("# Trigger Classifier Accuracy Analysis")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- **Total queries**: {result.total_queries}")
    lines.append(f"- **Correct predictions**: {result.correct}")
    lines.append(f"- **Overall accuracy**: {result.accuracy:.4f} ({result.accuracy * 100:.1f}%)")
    lines.append("")

    lines.append("## Confusion Matrix")
    lines.append("")
    lines.append("Rows = ground truth, Columns = classifier prediction")
    lines.append("")
    lines.append(format_confusion_matrix(result.confusion_matrix, labels))
    lines.append("")

    lines.append("## Per-Class Metrics")
    lines.append("")
    lines.append(format_per_class_metrics(result.per_class_metrics))
    lines.append("")

    lines.append("## Misclassification Analysis")
    lines.append("")
    if result.misclassified_examples:
        lines.append(f"Total misclassified: {result.total_queries - result.correct}")
        lines.append(f"Sample of {len(result.misclassified_examples)} misclassified cases:")
        lines.append("")
        for i, case in enumerate(result.misclassified_examples, 1):
            lines.append(f"### Case {i}")
            lines.append(f"- **Query**: \"{case.query_text}\"")
            lines.append(f"- **Ground truth**: {case.ground_truth}")
            lines.append(f"- **Predicted**: {case.predicted}")
            lines.append(f"- **Confidence**: {case.confidence:.3f}")
            if case.detail:
                lines.append(f"- **Note**: {case.detail}")
            lines.append("")
    else:
        lines.append("No misclassified cases found (perfect accuracy).")
        lines.append("")

    lines.append("## Methodology")
    lines.append("")
    lines.append("Ground truth labels are assigned using rule-based proxy labeling:")
    lines.append("1. **EXPLICIT_SYMBOL**: Queries containing function/class names, backtick-quoted identifiers, or explicit lookup keywords (find, show, locate)")
    lines.append("2. **TEMPORAL_HISTORY**: Queries with temporal keywords (recent, last, changed, previously, discussed)")
    lines.append("3. **IMPLICIT_CONTEXT**: Queries about imports, dependencies, module relationships")
    lines.append("4. **SEMANTIC_CONCEPT**: Default category for conceptual queries (how, why, overview, explain, related to)")
    lines.append("")
    lines.append("Priority order: EXPLICIT > TEMPORAL > IMPLICIT > SEMANTIC (more specific rules take precedence)")
    lines.append("")

    return "\n".join(lines)


def main():
    """Run trigger accuracy analysis on the synthetic small dataset."""
    metadata_path = os.path.join(PROJECT_ROOT, "benchmarks", "datasets", "small", "metadata.json")

    if not os.path.exists(metadata_path):
        print(f"Metadata not found at {metadata_path}")
        print("Generating synthetic dataset first...")
        from src.data.dataset_generator import DatasetGenerator
        dataset_dir = os.path.join(PROJECT_ROOT, "benchmarks", "datasets", "small")
        generator = DatasetGenerator(seed=42)
        generator.generate("small", dataset_dir)

    print("Running trigger classifier accuracy analysis...")
    result = run_trigger_accuracy_analysis(metadata_path=metadata_path, seed=42)

    # Generate report
    report = generate_report(result)

    # Save report
    output_path = os.path.join(PROJECT_ROOT, "benchmarks", "results", "trigger_accuracy.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)

    print(f"\nResults saved to {output_path}")
    print(f"\nOverall accuracy: {result.accuracy:.4f} ({result.accuracy * 100:.1f}%)")
    print(f"Correct: {result.correct}/{result.total_queries}")

    # Print summary
    print("\nPer-class F1 scores:")
    for label, m in result.per_class_metrics.items():
        print(f"  {label}: P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} (n={int(m['support'])})")

    return result


if __name__ == "__main__":
    main()
