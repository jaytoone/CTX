# CTX Document Retrieval Evaluation v2

**Date**: 2026-05-05 05:15
**Corpus**: 119 .md files from docs/
**Queries**: 100 (heading_exact + heading_paraphrase + keyword)
**Metrics**: Recall@3, Recall@5, NDCG@5, MRR

## Summary Table

| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |
|----------|----------|----------|--------|-----|
| CTX-doc (heading+BM25) | **0.740** | **0.790** | 0.680 | 0.662 |
| BM25 | **0.490** | **0.590** | 0.443 | 0.424 |
| Dense TF-IDF | **0.490** | **0.610** | 0.472 | 0.452 |

## Per-Strategy Analysis

### CTX-doc (heading+BM25)
- Hits@3: 74/100 (74.0%)
- Hits@5: 79/100 (79.0%)
- NDCG@5: 0.680
- MRR: 0.662

**Misses (top 5)**:
- [keyword] `find docs related to dense import` → expected `research/20260326-ctx-methodology-comparison.md`
- [keyword] `which document covers graph retrieval` → expected `paper_draft_outline.md`
- [heading_exact] `original question` → expected `research/20260330-ctx-academic-critique-web-grounded.md`
- [keyword] `find docs related to beir locagent` → expected `research/20260327-ctx-alternatives-research.md`
- [keyword] `notes about evaluation quality` → expected `research/20260402-g2-evaluation-methods-research-summary.md`

### BM25
- Hits@3: 49/100 (49.0%)
- Hits@5: 59/100 (59.0%)
- NDCG@5: 0.443
- MRR: 0.424

**Misses (top 5)**:
- [heading_paraphrase] `I need info on [expert-research-v2] ctx 실험 방식 상위 티어 논문 기준 평론` → expected `research/20260324-ctx-methodology-critique-top-tier.md`
- [heading_exact] `5개 실제 시나리오` → expected `research/20260328-ctx-real-codebase-g2-eval.md`
- [heading_paraphrase] `find documentation about [expert-research-v2] ctx 성과 평론 — 상위` → expected `research/20260326-ctx-results-review.md`
- [heading_exact] `g1: cross-session memory recall` → expected `research/20260327-ctx-downstream-eval.md`
- [keyword] `find docs related to dense import` → expected `research/20260326-ctx-methodology-comparison.md`

### Dense TF-IDF
- Hits@3: 49/100 (49.0%)
- Hits@5: 61/100 (61.0%)
- NDCG@5: 0.472
- MRR: 0.452

**Misses (top 5)**:
- [heading_paraphrase] `documentation for ctx: trigger-driven dynamic context loadin` → expected `paper/CTX_paper_draft.md`
- [heading_paraphrase] `I need info on [expert-research-v2] ctx 실험 방식 상위 티어 논문 기준 평론` → expected `research/20260324-ctx-methodology-critique-top-tier.md`
- [heading_exact] `5개 실제 시나리오` → expected `research/20260328-ctx-real-codebase-g2-eval.md`
- [heading_paraphrase] `find documentation about [expert-research-v2] ctx 성과 평론 — 상위` → expected `research/20260326-ctx-results-review.md`
- [heading_exact] `g1: cross-session memory recall` → expected `research/20260327-ctx-downstream-eval.md`

## Per-Query-Type Breakdown

| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |
|------|---|---------|----------|-----------|
| heading_exact | 32 | 0.812 | 0.531 | 0.469 |
| heading_paraphrase | 34 | 1.000 | 0.529 | 0.588 |
| keyword | 34 | 0.412 | 0.412 | 0.412 |

## Method Description

- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match
- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content
- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)

## Corpus Summary

| Stat | Value |
|------|-------|
| Total docs | 119 |
| Average headings/doc | 19.0 |
| Average keywords/doc | 15.0 |
