# G1 External Repo Open-Set Benchmark

**Date**: 2026-04-09
**Method**: CHANGELOG-based ground truth, open-set retrieval (full git history)

## Results

### Per-Repo Recall@7

| Baseline | Flask | Requests | Django | Mean | Closed-Set | Delta |
|----------|-------|----------|--------|------|------------|-------|
| no_ctx | 0.000 | 0.000 | 0.000 | **0.000** | 0.000 | +0.000 |
| full_dump | 0.333 | 0.500 | 1.000 | **0.611** | 0.712 | -0.101 |
| git_memory_real | 0.000 | 0.000 | 0.000 | **0.000** | 0.169 | -0.169 |
| bm25_retrieval | 0.167 | 0.000 | 0.000 | **0.056** | 0.881 | -0.825 |
| dense_embedding | 0.333 | 0.000 | 0.000 | **0.111** | 0.644 | -0.533 |

## Key Findings

### Open-Set vs Closed-Set Gap

| Metric | Closed-Set (59 CTX commits) | Open-Set (full git history) |
|--------|----------------------------|----------------------------|
| bm25_retrieval | 0.881 | 0.111 |
| dense_embedding | 0.644 | 0.222 |
| git_memory_real | 0.169 | 0.000 |

## Methodology

- **Ground truth**: CHANGELOG.md / HISTORY.md entries (curator-labeled decisions)
- **Corpus size**: up to 2000 commits per repo (open-set)
- **QA pairs**: up to 20 per repo (Type 1: timestamp queries)
- **Scoring**: Recall@7 — correct date/version in LLM response
- **LLM**: MiniMax M2.5 (same as closed-set eval)