# Trigger Classifier Accuracy Analysis

## Overview

- **Total queries**: 166
- **Correct predictions**: 166
- **Overall accuracy**: 1.0000 (100.0%)

## Confusion Matrix

Rows = ground truth, Columns = classifier prediction

| True \\ Pred | EXPLICIT | SEMANTIC | TEMPORAL | IMPLICIT | Total |
|---|---|---|---|---|---|
| **EXPLICIT** | 79 | 0 | 0 | 0 | 79 |
| **SEMANTIC** | 0 | 72 | 0 | 0 | 72 |
| **TEMPORAL** | 0 | 0 | 10 | 0 | 10 |
| **IMPLICIT** | 0 | 0 | 0 | 5 | 5 |

## Per-Class Metrics

| Trigger Type | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| EXPLICIT_SYMBOL | 1.0000 | 1.0000 | 1.0000 | 79 |
| SEMANTIC_CONCEPT | 1.0000 | 1.0000 | 1.0000 | 72 |
| TEMPORAL_HISTORY | 1.0000 | 1.0000 | 1.0000 | 10 |
| IMPLICIT_CONTEXT | 1.0000 | 1.0000 | 1.0000 | 5 |
| **Macro Avg** | 1.0000 | 1.0000 | 1.0000 | 166 |

## Misclassification Analysis

No misclassified cases found (perfect accuracy).

## Methodology

Ground truth labels are assigned using rule-based proxy labeling:
1. **EXPLICIT_SYMBOL**: Queries containing function/class names, backtick-quoted identifiers, or explicit lookup keywords (find, show, locate)
2. **TEMPORAL_HISTORY**: Queries with temporal keywords (recent, last, changed, previously, discussed)
3. **IMPLICIT_CONTEXT**: Queries about imports, dependencies, module relationships
4. **SEMANTIC_CONCEPT**: Default category for conceptual queries (how, why, overview, explain, related to)

Priority order: EXPLICIT > TEMPORAL > IMPLICIT > SEMANTIC (more specific rules take precedence)
