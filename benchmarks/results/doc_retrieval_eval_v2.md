# CTX Document Retrieval Evaluation v2

**Date**: 2026-03-30 15:07
**Corpus**: 47 .md files from docs/
**Queries**: 100 (heading_exact + heading_paraphrase + keyword)
**Metrics**: Recall@3, Recall@5, NDCG@5, MRR

## Summary Table

| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |
|----------|----------|----------|--------|-----|
| CTX-doc (heading+BM25) | **0.890** | **0.960** | 0.816 | 0.773 |
| BM25 | **0.670** | **0.790** | 0.633 | 0.601 |
| Dense TF-IDF | **0.640** | **0.720** | 0.560 | 0.535 |

## Per-Strategy Analysis

### CTX-doc (heading+BM25)
- Hits@3: 89/100 (89.0%)
- Hits@5: 96/100 (96.0%)
- NDCG@5: 0.816
- MRR: 0.773

**Misses (top 5)**:
- [keyword] `find docs related to retrieval recall` → expected `research/20260326-ctx-goal1-goal2-final.md`
- [keyword] `find docs related to downstream coir` → expected `research/20260326-ctx-benchmark-validation-roadmap.md`
- [keyword] `find docs related to prefix dotted` → expected `decisions/20260326-path-derived-module-to-file.md`
- [keyword] `which document covers trigger retrieval` → expected `paper_draft_outline.md`

### BM25
- Hits@3: 67/100 (67.0%)
- Hits@5: 79/100 (79.0%)
- NDCG@5: 0.633
- MRR: 0.601

**Misses (top 5)**:
- [heading_paraphrase] `ctx vs sota — 최종 성능 비교 테이블 v2 reference` → expected `research/20260326-ctx-sota-final-v2.md`
- [heading_paraphrase] `where is ctx — document index documented` → expected `DOC_INDEX.md`
- [heading_exact] `ctx 수정된 실험 결과 종합 요약 (논문 기준)` → expected `research/20260329-ctx-corrected-results-summary.md`
- [heading_paraphrase] `adaptivetriggerretriever 외부 코드베이스 일반화 개선 reference` → expected `research/20260328-adaptive-trigger-generalization-fix.md`
- [heading_exact] `실험 조건` → expected `research/20260328-ctx-downstream-minimax-eval.md`

### Dense TF-IDF
- Hits@3: 64/100 (64.0%)
- Hits@5: 72/100 (72.0%)
- NDCG@5: 0.560
- MRR: 0.535

**Misses (top 5)**:
- [keyword] `show information about full context` → expected `CTX_SPEC_v1.0.md`
- [heading_paraphrase] `ctx vs sota — 최종 성능 비교 테이블 v2 reference` → expected `research/20260326-ctx-sota-final-v2.md`
- [heading_paraphrase] `where is ctx — document index documented` → expected `DOC_INDEX.md`
- [keyword] `context memory documentation` → expected `research/20260325-long-session-context-management.md`
- [heading_exact] `ctx 수정된 실험 결과 종합 요약 (논문 기준)` → expected `research/20260329-ctx-corrected-results-summary.md`

## Per-Query-Type Breakdown

| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |
|------|---|---------|----------|-----------|
| heading_exact | 29 | 0.897 | 0.690 | 0.655 |
| heading_paraphrase | 32 | 1.000 | 0.500 | 0.625 |
| keyword | 39 | 0.795 | 0.795 | 0.641 |

## Method Description

- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match
- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content
- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)

## Corpus Summary

| Stat | Value |
|------|-------|
| Total docs | 47 |
| Average headings/doc | 15.4 |
| Average keywords/doc | 15.0 |
