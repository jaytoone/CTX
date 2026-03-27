# CTX Document Retrieval Evaluation v2

**Date**: 2026-03-27 14:32
**Corpus**: 29 .md files from docs/
**Queries**: 87 (heading_exact + heading_paraphrase + keyword)
**Metrics**: Recall@3, Recall@5, NDCG@5, MRR

## Summary Table

| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |
|----------|----------|----------|--------|-----|
| CTX-doc (heading+BM25) | **0.839** | **0.931** | 0.787 | 0.748 |
| BM25 | **0.667** | **0.839** | 0.655 | 0.611 |
| Dense TF-IDF | **0.690** | **0.805** | 0.607 | 0.563 |

## Per-Strategy Analysis

### CTX-doc (heading+BM25)
- Hits@3: 73/87 (83.9%)
- Hits@5: 81/87 (93.1%)
- NDCG@5: 0.787
- MRR: 0.748

**Misses (top 5)**:
- [heading_exact] `original question` → expected `research/20260326-ctx-vs-claudecode-tools.md`
- [keyword] `notes about goal memory` → expected `research/20260326-ctx-vs-claudecode-tools.md`
- [keyword] `notes about coir benchmark` → expected `research/20260326-ctx-vs-sota-comparison.md`
- [keyword] `find docs related to repobench cosqa` → expected `research/20260327-ctx-paper-numbers-critique.md`
- [heading_exact] `original question` → expected `research/20260326-ctx-benchmark-validation-roadmap.md`

### BM25
- Hits@3: 58/87 (66.7%)
- Hits@5: 73/87 (83.9%)
- NDCG@5: 0.655
- MRR: 0.611

**Misses (top 5)**:
- [heading_exact] `3개 mcp의 현재 상태` → expected `research/QUICK_REFERENCE.md`
- [heading_paraphrase] `I need info on [expert-research-v2] ctx 실험 논문 가치 평론` → expected `research/20260324-ctx-paper-worthiness.md`
- [heading_exact] `original question` → expected `research/20260326-ctx-vs-claudecode-tools.md`
- [heading_paraphrase] `explain [expert-research-v2] ctx 현재 성과 vs 사용자 요구 평론` → expected `research/20260326-ctx-achievement-review.md`
- [heading_exact] `2. related work` → expected `paper/CTX_paper_draft.md`

### Dense TF-IDF
- Hits@3: 60/87 (69.0%)
- Hits@5: 70/87 (80.5%)
- NDCG@5: 0.607
- MRR: 0.563

**Misses (top 5)**:
- [heading_exact] `3개 mcp의 현재 상태` → expected `research/QUICK_REFERENCE.md`
- [heading_exact] `original question` → expected `research/20260325-ctx-paper-tier-evaluation.md`
- [heading_paraphrase] `I need info on [expert-research-v2] ctx 실험 논문 가치 평론` → expected `research/20260324-ctx-paper-worthiness.md`
- [keyword] `show information about retrieval cross` → expected `research/20260325-long-session-context-management.md`
- [keyword] `show information about full context` → expected `CTX_SPEC_v1.0.md`

## Per-Query-Type Breakdown

| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |
|------|---|---------|----------|-----------|
| heading_exact | 29 | 0.862 | 0.621 | 0.690 |
| heading_paraphrase | 29 | 1.000 | 0.655 | 0.655 |
| keyword | 29 | 0.655 | 0.724 | 0.724 |

## Method Description

- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match
- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content
- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)

## Corpus Summary

| Stat | Value |
|------|-------|
| Total docs | 29 |
| Average headings/doc | 13.7 |
| Average keywords/doc | 15.0 |
