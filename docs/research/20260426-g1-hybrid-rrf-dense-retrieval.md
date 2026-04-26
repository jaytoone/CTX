# [live iter 34/∞] G1 Hybrid BM25+Dense RRF — Dense First-Stage Retrieval
**Date**: 2026-04-26  **Iteration**: 34

## Goal
Implement SOTA hybrid retrieval (BM25+dense RRF) for CTX G1, per MAB/LongMemEval finding
that hybrid outperforms either alone. Eval on same 59-query G1 corpus to validate.

## Implementation

### New functions in `~/.claude/hooks/bm25-memory.py`

| Function | Purpose |
|---|---|
| `embed_corpus_items(corpus)` | Pre-embed corpus subjects via vec-daemon; adds `emb` field to each item |
| `dense_rank_decisions(corpus, query, top_k=20)` | Cosine similarity ranking using pre-computed embeddings |
| `rrf_merge(list_a, list_b, k_rrf=60)` | Reciprocal Rank Fusion (k=60 per BEIR paper arXiv:2104.08663) |
| `hybrid_rank_decisions(corpus, query, top_k=7)` | Full pipeline: BM25+dense→RRF→rerank |

### Extended cache
`get_decision_corpus()` now pre-embeds corpus items and caches with `emb_head` sentinel.
172 commit subjects × vec-daemon calls = ~1-2s one-time cost (amortized via cache).

### Production wiring
G1 hook changed from `bm25_rank_decisions()` → `hybrid_rank_decisions()` at line 1142.

## Results

| Method | Recall@7 | Delta | Latency/query |
|---|---|---|---|
| A: BM25-only | 0.966 | baseline | ~12ms |
| B: BM25+rerank | 0.966 | +0.000 | ~54ms |
| **C: Hybrid BM25+dense RRF** | **0.983** | **+0.017 ✅** | ~175ms |

**Corpus**: 172 CTX commits, 59 labeled QA pairs  
**Embeddings**: 172/172 items embedded (multilingual-e5-small via vec-daemon)

### Key query recovered by dense

> "When did we implement inject_decisions.py?"  
> Gold: `e06a15f` — "inject_decisions.py: git-only mode (no world-model dependency)"

- BM25: `e06a15f` NOT in candidates — `8a3f0ac` (different commit, same file) dominated by keyword overlap
- Hybrid-RRF: dense retrieved `e06a15f` at rank 3 via semantic similarity → HIT

**Mechanism**: Two commits both mention "inject_decisions.py" but with different vocabulary.
BM25 selected the one with higher IDF token overlap. Dense embeddings captured both as
semantically similar to the query and ranked the gold commit through the RRF merge.

## Architecture Analysis

```
BM25-only path (before):
  query → BM25 tokenize → score 172 commits → MMR dedup → [0-14 cands] → BGE rerank → top-7

Hybrid path (after):
  query → BM25 tokenize → score 172 → MMR dedup → [0-14 BM25 cands]
        ↗                                                                       ↘
  query → _vec_embed → cosine(q, pre-emb[172]) → sort → [0-14 dense cands]  → RRF merge
                                                                                    ↓
                                                                        [0-28 union] → BGE rerank → top-7
```

**Why dense helps**: BM25 operates on token overlap → misses semantically related commits
with different vocabulary. Pre-computed embeddings (multilingual-e5-small) capture semantic
proximity at query time with only 1 vec-daemon call (query embedding only; corpus pre-embedded).

## Fail-safe Behavior

| Condition | Behavior |
|---|---|
| vec-daemon up + corpus embedded | Full hybrid (BM25+dense→RRF→BGE rerank) |
| vec-daemon down | Falls back to BM25+BGE rerank (existing behavior) |
| corpus not embedded | Same fallback |
| dense candidates empty | Falls back to BM25+rerank |

## Eval Script
`benchmarks/eval/g1_hybrid_rrf_eval.py` — runs all 3 conditions (A/B/C) and produces:
- Quantitative comparison table
- `--human-loop` flag: per-node relevance rating sheet (Markdown)

## Notes
- `bm25_rank_decisions()` gains `skip_rerank=False` param for clean A/B comparison
- Embedding cache extended: `{head, corpus, emb_head}` in `.omc/decision_corpus.json`
- Latency: ~175ms/query for hybrid in eval mode; ~113ms expected in production (BGE dominates)
