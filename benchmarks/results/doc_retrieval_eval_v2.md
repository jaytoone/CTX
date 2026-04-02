# CTX Document Retrieval Evaluation v2

**Date**: 2026-04-02 16:43
**Corpus**: 58 .md files from docs/
**Queries**: 100 (heading_exact + heading_paraphrase + keyword)
**Metrics**: Recall@3, Recall@5, NDCG@5, MRR

## Summary Table

| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |
|----------|----------|----------|--------|-----|
| CTX-doc (heading+BM25) | **0.870** | **0.940** | 0.834 | 0.806 |
| BM25 | **0.630** | **0.780** | 0.602 | 0.561 |
| Dense TF-IDF | **0.610** | **0.690** | 0.561 | 0.548 |

## Per-Strategy Analysis

### CTX-doc (heading+BM25)
- Hits@3: 87/100 (87.0%)
- Hits@5: 94/100 (94.0%)
- NDCG@5: 0.834
- MRR: 0.806

**Misses (top 5)**:
- [keyword] `find docs related to benchmark retrieval` → expected `research/20260330-ctx-academic-critique-web-grounded.md`
- [keyword] `show information about minimax without` → expected `research/20260328-ctx-downstream-eval-complete.md`
- [keyword] `which document covers trigger retrieval` → expected `paper_draft_outline.md`
- [keyword] `find docs related to memory cross` → expected `research/20260325-long-session-context-management.md`
- [heading_exact] `original question` → expected `research/20260326-ctx-vs-industry-comparison.md`

### BM25
- Hits@3: 63/100 (63.0%)
- Hits@5: 78/100 (78.0%)
- NDCG@5: 0.602
- MRR: 0.561

**Misses (top 5)**:
- [keyword] `find docs related to benchmark retrieval` → expected `research/20260330-ctx-academic-critique-web-grounded.md`
- [heading_exact] `실험 설계` → expected `research/20260327-ctx-downstream-eval.md`
- [heading_exact] `[expert-research-v2] ctx 약점 보완 대안 기술 분석` → expected `research/20260327-ctx-alternatives-research.md`
- [heading_exact] `사용자 최초 목표 (재확인)` → expected `research/20260326-ctx-goal1-goal2-final.md`
- [heading_exact] `ctx 프로젝트 루트에서 직접 실행` → expected `research/20260327-ctx-real-project-self-eval.md`

### Dense TF-IDF
- Hits@3: 61/100 (61.0%)
- Hits@5: 69/100 (69.0%)
- NDCG@5: 0.561
- MRR: 0.548

**Misses (top 5)**:
- [keyword] `find docs related to benchmark retrieval` → expected `research/20260330-ctx-academic-critique-web-grounded.md`
- [heading_exact] `실험 설계` → expected `research/20260327-ctx-downstream-eval.md`
- [heading_exact] `[expert-research-v2] ctx 약점 보완 대안 기술 분석` → expected `research/20260327-ctx-alternatives-research.md`
- [heading_paraphrase] `find documentation about [expert-research-v2] ctx goal 1&2 v` → expected `research/20260326-ctx-vs-sota-comparison.md`
- [heading_exact] `사용자 최초 목표 (재확인)` → expected `research/20260326-ctx-goal1-goal2-final.md`

## Per-Query-Type Breakdown

| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |
|------|---|---------|----------|-----------|
| heading_exact | 35 | 0.943 | 0.543 | 0.514 |
| heading_paraphrase | 33 | 1.000 | 0.697 | 0.606 |
| keyword | 32 | 0.656 | 0.656 | 0.719 |

## Method Description

- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match
- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content
- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)

## Corpus Summary

| Stat | Value |
|------|-------|
| Total docs | 58 |
| Average headings/doc | 13.6 |
| Average keywords/doc | 14.8 |
