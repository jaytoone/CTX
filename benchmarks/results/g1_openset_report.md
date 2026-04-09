# G1 External Repo Open-Set Benchmark

**Date**: 2026-04-09
**Method**: CHANGELOG-based ground truth, open-set retrieval (full git history)

## Results

### Per-Repo Recall@7

| Baseline | Flask | Requests | Django | Mean | Closed-Set | Delta |
|----------|-------|----------|--------|------|------------|-------|
| no_ctx | 0.000 | 0.000 | 0.000 | **0.000** | 0.000 | +0.000 |
| full_dump | 0.571 | 0.000 | 0.250 | **0.274** | 0.712 | -0.438 |
| git_memory_real | 0.000 | 0.000 | 0.000 | **0.000** | 0.169 | -0.169 |
| bm25_retrieval | 0.429 | 0.200 | 0.000 | **0.210** | 0.881 | -0.671 |
| dense_embedding | 0.429 | 0.200 | 0.500 | **0.376** | 0.644 | -0.268 |

## Key Findings

### Open-Set vs Closed-Set Gap

| Metric | Closed-Set (59 CTX commits) | Open-Set (full git history) |
|--------|----------------------------|----------------------------|
| bm25_retrieval | 0.881 | 0.250 |
| dense_embedding | 0.644 | 0.375 |
| git_memory_real | 0.169 | 0.000 |

## Methodology

- **Ground truth**: CHANGELOG.md / HISTORY.md entries (curator-labeled decisions)
- **Corpus size**: up to 2000 commits per repo (open-set)
- **QA pairs**: up to 20 per repo (Type 1: timestamp queries)
- **Scoring**: Recall@7 — correct date/version in LLM response
- **LLM**: MiniMax M2.5 (same as closed-set eval)