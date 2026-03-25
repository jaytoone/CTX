# Trigger Classifier Accuracy Analysis

## Overview

- **Total queries**: 166
- **Correct predictions**: 100
- **Overall accuracy**: 0.6024 (60.2%)

## Confusion Matrix

Rows = ground truth, Columns = classifier prediction

| True \\ Pred | EXPLICIT | SEMANTIC | TEMPORAL | IMPLICIT | Total |
|---|---|---|---|---|---|
| **EXPLICIT** | 79 | 0 | 0 | 0 | 79 |
| **SEMANTIC** | 66 | 6 | 0 | 0 | 72 |
| **TEMPORAL** | 0 | 0 | 10 | 0 | 10 |
| **IMPLICIT** | 0 | 0 | 0 | 5 | 5 |

## Per-Class Metrics

| Trigger Type | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| EXPLICIT_SYMBOL | 0.5448 | 1.0000 | 0.7054 | 79 |
| SEMANTIC_CONCEPT | 1.0000 | 0.0833 | 0.1538 | 72 |
| TEMPORAL_HISTORY | 1.0000 | 1.0000 | 1.0000 | 10 |
| IMPLICIT_CONTEXT | 1.0000 | 1.0000 | 1.0000 | 5 |
| **Macro Avg** | 0.8862 | 0.7708 | 0.7148 | 166 |

## Misclassification Analysis

Total misclassified: 66
Sample of 5 misclassified cases:

### Case 1
- **Query**: "Find all code related to json_parse"
- **Ground truth**: SEMANTIC_CONCEPT
- **Predicted**: EXPLICIT_SYMBOL
- **Confidence**: 0.700
- **Note**: Labeled as 'SEMANTIC_CONCEPT' in dataset

### Case 2
- **Query**: "Find all code related to query"
- **Ground truth**: SEMANTIC_CONCEPT
- **Predicted**: EXPLICIT_SYMBOL
- **Confidence**: 0.700
- **Note**: Labeled as 'SEMANTIC_CONCEPT' in dataset

### Case 3
- **Query**: "Find all code related to alert"
- **Ground truth**: SEMANTIC_CONCEPT
- **Predicted**: EXPLICIT_SYMBOL
- **Confidence**: 0.700
- **Note**: Labeled as 'SEMANTIC_CONCEPT' in dataset

### Case 4
- **Query**: "Find all code related to request"
- **Ground truth**: SEMANTIC_CONCEPT
- **Predicted**: EXPLICIT_SYMBOL
- **Confidence**: 0.700
- **Note**: Labeled as 'SEMANTIC_CONCEPT' in dataset

### Case 5
- **Query**: "Find all code related to oauth"
- **Ground truth**: SEMANTIC_CONCEPT
- **Predicted**: EXPLICIT_SYMBOL
- **Confidence**: 0.700
- **Note**: Labeled as 'SEMANTIC_CONCEPT' in dataset

## Methodology

Ground truth labels are assigned using rule-based proxy labeling:
1. **EXPLICIT_SYMBOL**: Queries containing function/class names, backtick-quoted identifiers, or explicit lookup keywords (find, show, locate)
2. **TEMPORAL_HISTORY**: Queries with temporal keywords (recent, last, changed, previously, discussed)
3. **IMPLICIT_CONTEXT**: Queries about imports, dependencies, module relationships
4. **SEMANTIC_CONCEPT**: Default category for conceptual queries (how, why, overview, explain, related to)

Priority order: EXPLICIT > TEMPORAL > IMPLICIT > SEMANTIC (more specific rules take precedence)
