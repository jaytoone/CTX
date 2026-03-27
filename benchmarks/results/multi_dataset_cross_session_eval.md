# Multi-Dataset Cross-Session Recall Evaluation (Real Data)

**Date**: 2026-03-27T00:18:12.536998
**K**: 10
**Datasets**: 7 real codebases
**Data Source**: All metrics from real codebase evaluations (no synthetic data)

---

## Per-Dataset Results

### small
- Source: cross_session_recall.json (real evaluation)
- Files: 50, Queries: 166
- Tiers: {'head': 10, 'torso': 15, 'tail': 25}
- Avg Recall@10: **0.917**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head_files | 10 | 10 | 0.500 | 1.000 |
| torso_files | 15 | 10 | 0.333 | 0.667 |
| mixed_5 | 5 | 5 | 1.000 | 1.000 |
| mixed_10 | 10 | 10 | 0.500 | 1.000 |

### AgentNode
- Source: benchmark_real + statistical_tests (real codebase evaluation)
- Files: 215, Queries: 89
- Tiers: {'head': 43, 'torso': 64, 'tail': 108}
- Avg Recall@10: **0.556**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head | 43 | 31 | 0.663 | 0.716 |
| torso | 64 | 29 | 0.454 | 0.454 |
| tail | 108 | 54 | 0.454 | 0.496 |
| all | 215 | 120 | 0.522 | 0.558 |

**95% CI (adaptive_trigger)**: [0.4213, 0.6105] (n=89)

**CTX vs BM25**: Wilcoxon p=1.000000 (not significant)

### GraphPrompt
- Source: benchmark_real + statistical_tests (real codebase evaluation)
- Files: 73, Queries: 80
- Tiers: {'head': 14, 'torso': 22, 'tail': 37}
- Avg Recall@10: **0.674**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head | 14 | 7 | 0.497 | 0.530 |
| torso | 22 | 18 | 0.734 | 0.828 |
| tail | 37 | 25 | 0.639 | 0.674 |
| all | 73 | 49 | 0.619 | 0.665 |

**95% CI (adaptive_trigger)**: [0.5246, 0.7172] (n=80)

**CTX vs BM25**: Wilcoxon p=1.000000 (not significant)

### OneViral
- Source: benchmark_real + statistical_tests (real codebase evaluation)
- Files: 299, Queries: 84
- Tiers: {'head': 59, 'torso': 90, 'tail': 150}
- Avg Recall@10: **0.483**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head | 59 | 34 | 0.551 | 0.580 |
| torso | 90 | 49 | 0.537 | 0.546 |
| tail | 150 | 50 | 0.244 | 0.333 |
| all | 299 | 142 | 0.424 | 0.474 |

**95% CI (adaptive_trigger)**: [0.3266, 0.5139] (n=84)

**CTX vs BM25**: Wilcoxon p=1.000000 (not significant)

### Flask
- Source: benchmark_real + statistical_tests (real codebase evaluation)
- Files: 79, Queries: 90
- Tiers: {'head': 15, 'torso': 24, 'tail': 40}
- Avg Recall@10: **0.496**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head | 15 | 7 | 0.414 | 0.461 |
| torso | 24 | 12 | 0.500 | 0.500 |
| tail | 40 | 21 | 0.427 | 0.525 |
| all | 79 | 39 | 0.440 | 0.499 |

**95% CI (adaptive_trigger)**: [0.3446, 0.5384] (n=90)

**CTX vs BM25**: Wilcoxon p=1.000000 (not significant)

### FastAPI
- Source: benchmark_real + statistical_tests (real codebase evaluation)
- Files: 928, Queries: 88
- Tiers: {'head': 185, 'torso': 279, 'tail': 464}
- Avg Recall@10: **0.350**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head | 185 | 37 | 0.177 | 0.201 |
| torso | 279 | 130 | 0.331 | 0.465 |
| tail | 464 | 184 | 0.330 | 0.397 |
| all | 928 | 313 | 0.271 | 0.337 |

**95% CI (adaptive_trigger)**: [0.1841, 0.3553] (n=88)

**CTX vs BM25**: Wilcoxon p=1.000000 (not significant)

### Requests
- Source: benchmark_real + statistical_tests (real codebase evaluation)
- Files: 35, Queries: 85
- Tiers: {'head': 7, 'torso': 10, 'tail': 18}
- Avg Recall@10: **0.580**

| Scenario | GT Size | Restored | Recall@5 | Recall@10 |
|----------|---------|----------|----------|-----------|
| head | 7 | 3 | 0.348 | 0.394 |
| torso | 10 | 6 | 0.508 | 0.558 |
| tail | 18 | 14 | 0.683 | 0.758 |
| all | 35 | 21 | 0.549 | 0.610 |

**95% CI (adaptive_trigger)**: [0.4503, 0.6445] (n=85)

**CTX vs BM25**: Wilcoxon p=1.000000 (not significant)

---

## Cross-Dataset Summary

| Dataset | Files | Queries | Avg Recall@K | 95% CI | Source |
|---------|-------|---------|-------------|--------|--------|
| small | 50 | 166 | 0.917 | N/A | cross-session eval |
| AgentNode | 215 | 89 | 0.556 | [0.421, 0.611] | real benchmark |
| GraphPrompt | 73 | 80 | 0.674 | [0.525, 0.717] | real benchmark |
| OneViral | 299 | 84 | 0.483 | [0.327, 0.514] | real benchmark |
| Flask | 79 | 90 | 0.496 | [0.345, 0.538] | real benchmark |
| FastAPI | 928 | 88 | 0.350 | [0.184, 0.355] | real benchmark |
| Requests | 35 | 85 | 0.580 | [0.450, 0.644] | real benchmark |

---

## Statistical Significance Tests

### CTX vs BM25 (per-dataset Wilcoxon signed-rank)

- Datasets tested: 6
- Significant (p < 0.05): 0/6

| Dataset | p-value | Significant |
|---------|---------|-------------|
| AgentNode | 1.000000 | no |
| GraphPrompt | 1.000000 | no |
| OneViral | 1.000000 | no |
| Flask | 1.000000 | no |
| FastAPI | 1.000000 | no |
| Requests | 1.000000 | no |

### Cross-Dataset Consistency

- Mean Recall: 0.579
- Std: 0.179
- CV: 0.309
- Low variance across datasets (CV < 0.5)

### 95% Confidence Intervals (adaptive_trigger Recall@5)

| Dataset | Mean | 95% CI | n |
|---------|------|--------|---|
| AgentNode | 0.5221 | [0.4213, 0.6105] | 89 |
| GraphPrompt | 0.6192 | [0.5246, 0.7172] | 80 |
| OneViral | 0.4240 | [0.3266, 0.5139] | 84 |
| Flask | 0.4400 | [0.3446, 0.5384] | 90 |
| FastAPI | 0.2710 | [0.1841, 0.3553] | 88 |
| Requests | 0.5492 | [0.4503, 0.6445] | 85 |

- **head**: mean=0.480, std=0.160 [VARIABLE]
- **torso**: mean=0.558, std=0.126 [CONSISTENT]
- **tail**: mean=0.530, std=0.147 [CONSISTENT]
- **all**: mean=0.524, std=0.105 [CONSISTENT]

---

*Generated by CTX Multi-Dataset Cross-Session Eval — Real Data (2026-03-27T00:18:12.537082)*