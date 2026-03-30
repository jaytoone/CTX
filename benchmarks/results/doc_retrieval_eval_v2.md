# CTX Document Retrieval Evaluation v2

**Date**: 2026-03-30 14:23
**Corpus**: 46 .md files from docs/
**Queries**: 100 (heading_exact + heading_paraphrase + keyword)
**Metrics**: Recall@3, Recall@5, NDCG@5, MRR

## Summary Table

| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |
|----------|----------|----------|--------|-----|
| CTX-doc (heading+BM25) | **0.860** | **0.930** | 0.813 | 0.784 |
| BM25 | **0.610** | **0.740** | 0.596 | 0.572 |
| Dense TF-IDF | **0.610** | **0.650** | 0.525 | 0.518 |

## Per-Strategy Analysis

### CTX-doc (heading+BM25)
- Hits@3: 86/100 (86.0%)
- Hits@5: 93/100 (93.0%)
- NDCG@5: 0.813
- MRR: 0.784

**Misses (top 5)**:
- [keyword] `find docs related to goal high` → expected `research/20260326-ctx-goal1-goal2-final.md`
- [keyword] `find docs related to goal downstream` → expected `research/20260326-ctx-benchmark-validation-roadmap.md`
- [heading_exact] `web facts` → expected `research/20260326-ctx-benchmark-validation-roadmap.md`
- [heading_exact] `original question` → expected `research/20260326-ctx-vs-sota-comparison.md`
- [keyword] `show information about without minimax` → expected `research/20260328-ctx-downstream-nemotron-eval-v2.md`

### BM25
- Hits@3: 61/100 (61.0%)
- Hits@5: 74/100 (74.0%)
- NDCG@5: 0.596
- MRR: 0.572

**Misses (top 5)**:
- [heading_paraphrase] `[expert-research-v2] ctx 약점 보완 대안 기술 분석 reference` → expected `research/20260327-ctx-alternatives-research.md`
- [heading_exact] `실험 설정` → expected `research/20260327-ctx-real-project-self-eval.md`
- [heading_paraphrase] `where is ctx — document index documented` → expected `DOC_INDEX.md`
- [keyword] `find docs related to goal high` → expected `research/20260326-ctx-goal1-goal2-final.md`
- [keyword] `find docs related to goal downstream` → expected `research/20260326-ctx-benchmark-validation-roadmap.md`

### Dense TF-IDF
- Hits@3: 61/100 (61.0%)
- Hits@5: 65/100 (65.0%)
- NDCG@5: 0.525
- MRR: 0.518

**Misses (top 5)**:
- [keyword] `show information about full context` → expected `CTX_SPEC_v1.0.md`
- [heading_paraphrase] `[expert-research-v2] ctx 약점 보완 대안 기술 분석 reference` → expected `research/20260327-ctx-alternatives-research.md`
- [heading_exact] `실험 설정` → expected `research/20260327-ctx-real-project-self-eval.md`
- [heading_paraphrase] `where is ctx — document index documented` → expected `DOC_INDEX.md`
- [heading_paraphrase] `I need info on ctx vs nemotron-cascade-2: code retrieval per` → expected `research/20260327-ctx-nemotron-comparison.md`

## Per-Query-Type Breakdown

| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |
|------|---|---------|----------|-----------|
| heading_exact | 29 | 0.793 | 0.483 | 0.448 |
| heading_paraphrase | 34 | 1.000 | 0.529 | 0.647 |
| keyword | 37 | 0.784 | 0.784 | 0.703 |

## Method Description

- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match
- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content
- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)

## Corpus Summary

| Stat | Value |
|------|-------|
| Total docs | 46 |
| Average headings/doc | 15.3 |
| Average keywords/doc | 15.0 |
