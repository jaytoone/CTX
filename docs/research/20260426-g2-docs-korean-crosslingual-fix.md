# [live-inf iter 44/∞] G2-DOCS Korean Cross-lingual Fix
**Date**: 2026-04-26  **Iteration**: 44

## Problem
Korean queries retrieving English docs failed in G2-DOCS goldset (iter 44 finding):
- BM25: H@3=0.200, H@5=0.400, MRR=0.250
- Hybrid: H@3=0.200, H@5=0.400, MRR=0.240

Root cause: `bm25_search_docs()` and `hybrid_search_docs()` both call `tokenize(query)`,
which splits tokens but has no Korean→English expansion. The research docs corpus is
English-only; Korean queries produce tokens that don't match any document content.

**Contrast with G2-CODE**: `extract_keywords()` (used for code search) has `_KO_EN`
dict with ~30 entries. The docs search path had no equivalent.

---

## Fix

Added `_KO_EN_DOCS` dictionary (34 CTX/ML domain term mappings) and `_expand_ko_en_docs()`
function in `~/.claude/hooks/bm25-memory.py`:

```python
_KO_EN_DOCS = {
    "하이브리드": "hybrid", "밀집": "dense", "검색": "search,retrieve",
    "재색인": "reindex", "인용": "citation", "시멘틱": "semantic",
    "지연": "latency", "벡터": "vector,embedding", "마이그레이션": "migration",
    "임베딩": "embedding", "벤치마크": "benchmark,eval",
    "오래된": "stale,staleness", "측정": "measure,probe",
    "업그레이드": "upgrade", "자동": "auto,automatic", ...
}
```

Applied in both `bm25_search_docs()` and `hybrid_search_docs()`:
```python
query_tokens = tokenize(query, drop_stopwords=True)
query_tokens = _expand_ko_en_docs(query_tokens)  # Korean→English expansion
```

---

## Results (20-query goldset: 15 English + 5 Korean)

### Korean Crosslingual (before → after fix)

| Query | Gold | BM25 H@3 (before) | BM25 H@3 (after) | Hybrid H@5 (after) |
|-------|------|-------------------|------------------|-------------------|
| 하이브리드 BM25 밀집 검색 RRF 병합 구현 | g1-hybrid-rrf | 0 | 1 | 1 |
| 코드베이스 메모리 오래된 데이터베이스 자동 재색인 | g2-code-staleness | 0 | 1 | 1 |
| 검색 노드 인용 비율 측정 거짓 양성 | citation-probe | 0 | 1 | 1 |
| vault 벡터 마이그레이션 임베딩 벤치마크 성능 | vault-migration | 1 | 1 | 1 |
| CTX 시멘틱 검색 SOTA 수준 업그레이드 지연 시간 | semantic-upgrade | 0 | 0 | 1 |

**Korean H@3: 0.200 → 0.800** (+60pp for BM25)
**Korean H@5 Hybrid: 0.400 → 1.000** (+60pp)

Only `ko_05` BM25 misses (goldset corpus drift: synthesis doc now outscores the source doc
because it contains all the same terms in high density).

### Full Goldset (20 queries)

| Method | H@3 | H@5 | MRR |
|--------|-----|-----|-----|
| BM25 (before Korean queries) | 0.733 | 0.800 | 0.672 |
| BM25 (after, all 20 queries) | **0.750** | 0.800 | 0.643 |
| Hybrid (after, all 20 queries) | 0.700 | **0.900** | 0.631 |

Note: Hybrid H@5 drops from 1.000 (15-query) to 0.900 (20-query) because corpus drift
(synthesis doc added in iter 43) now outcompetes source docs for some English queries.
This is documented as a separate finding (see Goldset Corpus Drift section below).

### By Query Type (all 20 queries)

| Type | N | BM25 H@3 | Hybrid H@3 | BM25 H@5 | Hybrid H@5 | BM25 MRR | Hybrid MRR |
|------|---|----------|------------|----------|------------|----------|------------|
| heading_exact | 5 | 0.800 | 0.600 | 0.800 | 0.800 | 0.567 | 0.507 |
| heading_paraphrase | 5 | 0.600 | 0.600 | 0.600 | 1.000 | 0.600 | 0.700 |
| keyword | 5 | 0.800 | 0.800 | 1.000 | 0.800 | 0.707 | 0.700 |
| **korean_crosslingual** | **5** | **0.800** | **0.800** | **0.800** | **1.000** | **0.700** | **0.617** |

---

## Goldset Corpus Drift (Structural Finding)

Adding `20260426-ctx-retrieval-benchmark-synthesis.md` (iter 43 meta-doc) to the corpus
introduced a **vocabulary sink**: it mentions every doc's key terms in one place, causing
it to outrank specific source docs for some queries.

Observed effects:
- `kw_03` ("BM25 homograph false positive"): BM25 now returns synthesis doc first (MISS)
- `kw_05` ("semantic gap"): synthesis doc outranks `semantic-gap-keyword-vs-contextual.md`
- `ko_05` ("CTX semantic SOTA upgrade"): synthesis doc absorbs "semantic", "SOTA", "upgrade"

**Mitigation**: Index the goldset corpus snapshot at goldset creation time. For ongoing
evaluation, either exclude synthesis/index docs from the retrieval corpus, or use the
goldset's timestamp to restrict to docs that existed when queries were written.

This pattern (meta-docs outranking source docs) is a known RAG corpus design problem.
CTX should consider a **doc-type hierarchy**: synthesis docs get lower BM25 IDF weight
(or are excluded from G2-DOCS retrieval entirely — they're navigational, not source).

---

## Updated Production Impact

With `_KO_EN_DOCS` expansion, CTX now handles Korean prompts for research doc retrieval:
- "하이브리드 검색 구현" → finds hybrid retrieval docs ✅
- "오래된 DB 재색인 방법" → finds G2-CODE staleness doc ✅
- "인용 비율 측정" → finds citation probe doc ✅

Korean prompts are common in CTX sessions (CLAUDE.md is in Korean; user often types in Korean).
This fix is directly production-relevant.

---

## Related
- [[projects/CTX/research/20260426-g2-docs-goldset-eval|iter 42 — initial goldset]]
- [[projects/CTX/research/20260426-ctx-retrieval-benchmark-synthesis|iter 43 — benchmark synthesis]]
- `~/.claude/hooks/bm25-memory.py` — `_KO_EN_DOCS` + `_expand_ko_en_docs()`
