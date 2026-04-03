# CTX Document Retrieval Evaluation v2

**Date**: 2026-04-03 09:58
**Corpus**: 62 .md files from docs/
**Queries**: 100 (heading_exact + heading_paraphrase + keyword)
**Metrics**: Recall@3, Recall@5, NDCG@5, MRR

## Summary Table

| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |
|----------|----------|----------|--------|-----|
| CTX-doc (heading+BM25) | **0.870** | **0.940** | 0.815 | 0.782 |
| BM25 | **0.590** | **0.760** | 0.594 | 0.562 |
| Dense TF-IDF | **0.560** | **0.670** | 0.546 | 0.537 |

## Per-Strategy Analysis

### CTX-doc (heading+BM25)
- Hits@3: 87/100 (87.0%)
- Hits@5: 94/100 (94.0%)
- NDCG@5: 0.815
- MRR: 0.782

**Misses (top 5)**:
- [keyword] `show information about minimax without` → expected `research/20260328-ctx-downstream-eval-complete.md`
- [keyword] `find docs related to memory cross` → expected `research/20260325-long-session-context-management.md`
- [keyword] `which document covers trigger retrieval` → expected `paper_draft_outline.md`
- [keyword] `nemotron research documentation` → expected `research/20260329-ctx-paper-gap-analysis.md`
- [keyword] `find docs related to locagent source` → expected `research/20260327-ctx-alternatives-research.md`

### BM25
- Hits@3: 59/100 (59.0%)
- Hits@5: 76/100 (76.0%)
- NDCG@5: 0.594
- MRR: 0.562

**Misses (top 5)**:
- [heading_paraphrase] `where is ctx — document index documented` → expected `DOC_INDEX.md`
- [heading_exact] `즉시 실행 순서` → expected `marketing/active_outreach_playbook.md`
- [heading_exact] `실험 설계` → expected `research/20260327-ctx-downstream-eval.md`
- [heading_exact] `[expert-research-v2] ctx 약점 보완 대안 기술 분석` → expected `research/20260327-ctx-alternatives-research.md`
- [heading_exact] `ctx architecture` → expected `ARCHITECTURE.md`

### Dense TF-IDF
- Hits@3: 56/100 (56.0%)
- Hits@5: 67/100 (67.0%)
- NDCG@5: 0.546
- MRR: 0.537

**Misses (top 5)**:
- [heading_paraphrase] `where is ctx — document index documented` → expected `DOC_INDEX.md`
- [keyword] `which document covers memory codebase` → expected `research/20260402-production-context-retrieval-research.md`
- [heading_exact] `즉시 실행 순서` → expected `marketing/active_outreach_playbook.md`
- [heading_exact] `실험 설계` → expected `research/20260327-ctx-downstream-eval.md`
- [heading_exact] `[expert-research-v2] ctx 약점 보완 대안 기술 분석` → expected `research/20260327-ctx-alternatives-research.md`

## Per-Query-Type Breakdown

| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |
|------|---|---------|----------|-----------|
| heading_exact | 37 | 0.973 | 0.595 | 0.514 |
| heading_paraphrase | 31 | 1.000 | 0.548 | 0.613 |
| keyword | 32 | 0.625 | 0.625 | 0.562 |

## Method Description

- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match
- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content
- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)

## Corpus Summary

| Stat | Value |
|------|-------|
| Total docs | 62 |
| Average headings/doc | 14.5 |
| Average keywords/doc | 14.8 |
