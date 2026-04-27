# [expert-research-v2] CTX Semantic Search Upgrade to SOTA Tier
**Date**: 2026-04-17  **Skill**: expert-research-v2

## Original Question
How can we upgrade CTX's semantic search ability to SOTA tier while preserving <1ms deterministic hook latency?

## Current State Snapshot
- **G1** (decisions): BM25 + optional multilingual-e5-small via vec-daemon. Recall@7 = 0.746.
- **G2** (file prefetch): SQL `LIKE %keyword%` substring match. External R@5 mean = 0.602 (Flask 0.66, FastAPI 0.40).
- **CM** (chat memory): BM25 only.
- **_SYNONYM_MAP**: ~20 hardcoded pairs.
- **Known regression**: Dense embedding on Code→Code degraded Flask R@5 by -0.106 vs BM25 alone.

## Web Facts
[FACT-1] Hybrid BM25+dense is SOTA for small corpora (<10k docs). FAISS Flat + BM25 exact search is fast enough. Sparse retrieval completes in milliseconds. (blog.gopenai.com, mljourney.com)

[FACT-2] SPLADE at query time adds 100-300ms. Mitigation: pre-compute document SPLADE vectors; run SPLADE only on query. (blog.premai.io)

[FACT-3] ColBERT produces per-token vector matrices for late interaction reranking. (infiniflow.org)

[FACT-4] "Blended RAG" (full-text + dense + sparse) + ColBERT reranker is optimal at scale. (infiniflow.org)

[FACT-5] **BM25 is MORE valuable on small corpora — IDF statistics are maximally distinctive.** Directly explains CTX's Flask regression. (mljourney.com)

[FACT-6] **Sourcegraph Cody DEPRECATED embeddings for context retrieval.** Reasons: required external embedding service, management complexity, didn't scale. Replaced with adapted BM25 + learned signals. (sourcegraph.com/blog/how-cody-understands-your-codebase)

[FACT-7] Cody latency architecture: autocomplete = local only (no remote); chat = remote over ≤10 repos. Template for CTX hot/cold path split. (sourcegraph.com)

[FACT-8] Code embedding models:
  - jina-v2-base-code: 137M params, 768d, 8192 tokens
  - CodeRankEmbed: 137M/356M/1.3B
  - voyage-code-3: 256/512/1024/2048d, 32K tokens, +16.3% over OpenAI-v3-large
  - nomic-embed-code: 7B params
(modal.com, jina.ai, voyageai.com)

[FACT-9] HyDE pitfalls: without grounded corpus knowledge only marginal improvement + hallucination risk. (arxiv.org/2509.07794)

[FACT-10] LLM query expansion causes query drift, degrades retrieval accuracy. (arxiv.org, mdpi.com)

[FACT-11] Cache key must include model version to avoid stale cache. (dataquest.io)

[FACT-12] Cursor = dynamic on-demand loading; Cody = pre-indexed embeddings+RAG. (augmentcode.com)

## Multi-Lens Analysis

### Domain Expert (Lens 1) — 6 Insights

1. **SPLADE query-only highest-ROI semantic upgrade** [GROUNDED via FACT-2] — Pre-compute doc vectors at index time, daemon handles query encoding. 30-80ms daemon cost acceptable with async timeout pattern.
2. **G2 SQL LIKE replacement is largest addressable gap** [REASONED + GROUNDED via FACT-5] — Zero IDF, zero TF. Binary match/no-match. Replace with in-process BM25 (rank_bm25 already installed).
3. **Code embedding ROI depends on query type, not benchmark averages** [UNCERTAIN] — voyage-code-3's +16.3% was measured at large scale. CTX's 30-200 doc corpora are IDF-advantaged regime (FACT-5).
4. **_SYNONYM_MAP → corpus co-occurrence mining** [REASONED] — Avoids FACT-10 LLM drift; static pre-computation. Trade-off: n=170 commits has high co-occurrence variance.
5. **RRF with query-type-aware weighting** [REASONED from FACT-1] — Keyword queries: BM25 0.85 / semantic 0.15. NL queries: 0.50 / 0.50. Prevents Flask-style semantic drag-down.
6. **G1 ceiling ≈0.80 is structural, not model** [GROUNDED via FACT-5] — 170 decisions with distinctive IDF. Semantic upgrade likely <5pp. 0-7d bucket (0.711) may still benefit from fresher-term semantic fallback.

### Self-Critique (Lens 2) — 4 Findings

1. **[OVERCONFIDENT + CONFLICT]** SPLADE/dense recommendations conflict with FACT-5 and FACT-6. Sourcegraph has vastly more resources and deprecated embeddings. SPLADE was trained to fix BM25's weakness on large corpora — CTX doesn't have that weakness.
2. **[MISSING]** <1ms is about hook process, not daemon. SPLADE's 30-80ms CPU encoding means frequent timeout fallback. Semantic contributes "sometimes" — rarely enough to shift recall metrics.
3. **[MISSING]** G2 LIKE→BM25 has highest verified impact, zero latency cost, zero new deps, already-installed lib. Tier 1 priority inverted in Lens 1.
4. **[CONFLICT]** "Semantic upgrade is right priority" challenged by eval: G1 ceiling ~0.80, FastAPI "50% structurally ambiguous" per MEMORY.md. Any semantic gain may fall within noise band, untestable.

### Synthesis (Lens 3) — 3-Tier Roadmap

**Tier 1 (1-day wins, high confidence):**
- **T1-A: G2 SQL LIKE → in-process BM25** — `git-memory.py` G2 section + `auto-index.py`. <0.5ms, expected +0.10-0.20 FastAPI R@5.
- **T1-B: Corpus-derived co-occurrence synonyms** — `auto-index.py` scans git log, top-20 co-occurring pairs (>30%) written to `synonym_extensions.json`. +2-5pp G1 recall on 0-7d bucket.
- **T1-C: Query-type-aware RRF weights** — `git-memory.py` fusion. Detect keyword vs NL, weight accordingly. +2-4pp on keyword queries.

**Tier 2 (1-week, moderate confidence):**
- **T2-A: SPLADE doc pre-computation + query-only** — `naver/splade-cocondenser-ensemble-distil`, 110M, ~40-80ms daemon query. [UNCERTAIN] domain transfer from MS-MARCO to git commits. Ablate first.
- **T2-B: Persistent BM25 index in daemon** — eliminate rebuild latency. G1 hot path 5-15ms → <1ms.

**Tier 3 (2-4 weeks, SOTA tier, conditional):**
- **T3-A: voyage-code-3 or jina-v2-base-code for G2 NL→Code ONLY** — gated by query classifier. ~50-200ms daemon. [CONFLICT with FACT-6] Cody deprecated this; use narrowly.
- **T3-B: ColBERT-lite late interaction rerank top-20** — ~20-50ms. ~12MB storage for 200-doc corpus. [UNCERTAIN] small-corpus benefit.

**Deprioritized:**
| Technique | Reason |
|-----------|--------|
| HyDE (cached) | FACT-9: marginal gain + hallucination risk |
| LLM query expansion | FACT-10: query drift |
| Uniform dense embedding replacement | FACT-5 + FACT-6 |
| nomic-embed-code 7B | 1-5s CPU inference |
| G1 model upgrade before G2 LIKE fix | Lower ROI, higher risk |

## Final Conclusion

**Do Tier 1 first. Period.** The highest-impact, lowest-risk upgrade is replacing G2's SQL `LIKE %keyword%` with in-process BM25 — this uses already-installed tooling, adds zero latency, and directly addresses the FastAPI R@5=0.40 failure through FACT-5's IDF mechanism. Corpus-derived synonyms (T1-B) and query-type-aware RRF (T1-C) are zero-cost additions.

**Tier 2/3 require ablation before rollout.** Both FACT-5 (BM25 advantage on small corpora) and FACT-6 (Cody's embedding deprecation) are warnings that CTX's known Flask -0.106 regression is structural, not a model-capacity problem. Upgrading from multilingual-e5-small to voyage-code-3 may not reverse it — the IDF advantage on small corpora is a statistical phenomenon independent of model quality.

**The Cody architecture (FACT-7) validates CTX's hot/cold split.** Cody uses local-only for latency-critical paths, remote for chat. CTX's <1ms hook constraint places G1/G2/CM squarely in the "local-only" regime. The vec-daemon should provide asynchronous enrichment, never block the hot path.

**Confidence: MEDIUM-HIGH.** Tier 1 is high confidence. Tier 2/3 has uncertain small-corpus transfer; require ablation before commit.

## Sources
- [Hybrid Search in RAG: Dense + Sparse (BM25/SPLADE)](https://blog.gopenai.com/hybrid-search-in-rag-dense-sparse-bm25-splade-reciprocal-rank-fusion-and-when-to-use-which-fafe4fd6156e)
- [Hybrid Search for RAG: BM25, SPLADE, and Vector Search Combined](https://blog.premai.io/hybrid-search-for-rag-bm25-splade-and-vector-search-combined/)
- [Sparse vs Dense Retrieval for RAG](https://mljourney.com/sparse-vs-dense-retrieval-for-rag-bm25-embeddings-and-hybrid-search/)
- [How Cody Understands Your Codebase](https://sourcegraph.com/blog/how-cody-understands-your-codebase)
- [6 Best Code Embedding Models Compared](https://modal.com/blog/6-best-code-embedding-models-compared)
- [voyage-code-3: more accurate code retrieval](https://blog.voyageai.com/2024/12/04/voyage-code-3/)
- [Query Expansion in the Age of LLMs (arxiv)](https://arxiv.org/pdf/2509.07794)
- [jina-embeddings-v2-base-code](https://huggingface.co/jinaai/jina-embeddings-v2-base-code)
- [Infinity: Blended RAG + ColBERT Reranker](https://infiniflow.org/blog/best-hybrid-search-solution)
- [Cursor vs Sourcegraph Cody](https://www.augmentcode.com/guides/cursor-vs-sourcegraph-cody-embeddings-and-monorepo-scale)

## Remaining Uncertainties
- SPLADE transfer from MS-MARCO to git commit corpus — ablate on 59-query G1 bench
- voyage-code-3 on <200 doc corpora — Flask -0.106 is direct warning
- G2 BM25 integration with codebase-memory-mcp schema — need schema read
- Daemon cold-start fallback behavior — ensure BM25-only floor is preserved
- Query-type classifier reliability in hook hot path — currently exists in eval, may not run in hook

---

## Empirical Update 2026-04-17 — T1-A Implemented, Reverted, Diagnosis Incomplete

**T1-A (G2 SQL LIKE → BM25) was implemented, failed an A/B on the critical test
case, and REVERTED. Initial root-cause diagnosis was overreaching and is now
marked as unproven — see Honest Correction below.**

### A/B Harness (iteration 2 — with fixed code-identifier tokenizer)
6 queries tested against the actual codebase-memory-mcp SQLite DB for CTX itself.
Tokenizer: `r'[가-힣]+|[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+'` — splits
snake_case and CamelCase (first run's tokenizer was buggy; see Honest Correction).

| Query | OLD top-5 | NEW top-5 | overlap |
|-------|-----------|-----------|---------|
| "BM25 retriever lookup" | `rank_bm25`, `bm25_score`, `bm25_retrieve`, `bm25_retriever.py` | `DenseRetriever`, `LlamaIndexRetriever`, `ChromaDenseRetriever`, `chroma_retrieve…` | **0/5** |
| "search graph prompt" | `load_codesearchnet_corpus`, `mcp_code_search_headtohead.md` | `mcp_code_search_headtohead.md`, `benchmarks/results/…` | 3/5 |
| "semantic rerank" | `_detect_semantic_concepts`, `test_related_to_snake_case_stays_semantic` | `_detect_semantic_concepts`, `test_function_keyword_no_underscore…` | 3/5 |
| "fair eval" | `evaluate`, `run_eval`, `eval_repo` | `EvalResult`, `eval_surfacing`, `RealEvalResult` | 0/5 |
| Korean mapping | — | — | 0/5 |
| "synonym expansion" | `bfs_expand`, `_graph_expand`, `_expand_identifiers` | `_expand_identifiers`, `bfs_expand`, `_graph_expand` | 3/5 |

- Avg overlap: **0.30** (fixed-tokenizer; original buggy run reported 0.23)
- Latency: 1.6ms → **14.1ms (10×)**
- Canonical failure: "BM25 retriever lookup" — OLD surfaces direct matches
  (`rank_bm25`, `bm25_score`, `bm25_retrieve`, `bm25_retriever.py`); NEW surfaces
  generic retriever class names. `BM25Retriever` / `bm25_retriever.py` are in
  the candidate pool but not ranked top by BM25 despite matching both key tokens.

### Honest Correction on Root Cause
An earlier revision of this section claimed "FACT-5 applies to symbol surfaces:
BM25 IDF flattens on small symbol corpora" and cited Flask Code→Code R@5 -0.106
as supporting evidence. **That diagnosis was premature.**

What actually happened in the two A/B runs:
1. First run: tokenizer kept `_` inside tokens, so `rank_bm25` → one token,
   query `bm25` → zero TF match on the correct candidates. Failure was a
   harness bug, not a scoring-theory issue.
2. Second run (fixed tokenizer): T1-A still fails the canonical case, but
   the mechanism is **not yet proven to be IDF flattening**. It could also
   be multi-token query scoring spreading weight across candidates that
   match only one token, length-normalization penalising short names
   (`rank_bm25`) vs longer paths, or an interaction with
   `bm25_retriever.py` being in a different label set. No BM25 score
   distribution was inspected per candidate.

The accurate statement is:
- **T1-A as implemented regresses on the canonical symbol-lookup query.**
- **The mechanism is not proven.** It is plausibly related to BM25's token-
  level scoring behaviour on multi-token queries against short symbol names,
  but this has not been measured.
- FACT-5 as cited in the SOTA research does warn against this class of
  upgrade on small corpora, but the Flask -0.106 result is a different
  surface (document embeddings, not symbol-name BM25) and cannot be used
  as direct evidence for the symbol-corpus case without separate measurement.

### Revised Recommendations
| Item | Status |
|------|--------|
| **T1-A (G2 BM25 replace LIKE)** as implemented | ❌ **REVERTED** — regresses on canonical test, +10× latency |
| T1-A redesign (all-terms-must-match, or exact-substring boost before BM25) | ⏸ worth trying — not yet tested |
| T1-B (co-occurrence synonyms) | ⏸ pending — own A/B required before commit |
| T1-C (query-type RRF alpha) | ⏸ pending — own A/B required; affects G1 decisions, not G2 symbols |
| Tier 2 (SPLADE docs / daemon persistent BM25) | Remains low priority; no new evidence for or against |
| Tier 3 (voyage-code-3 / ColBERT) | Remains deprioritized; not confirmed by this test |

### What this run actually showed (bounded claim)
- A naive BM25 replacement of `search_graph_for_prompt` as written in this session
  loses to the existing LIKE + length-ASC ordering on queries where a specific
  token like `bm25` uniquely identifies the target. This is reproducible on the
  current CTX `codebase-memory-mcp` DB.
- It did NOT show that BM25 is fundamentally wrong for symbol corpora, nor that
  FACT-5 applies to this surface. Both remain open questions.

### Generalizable lesson (weak form)
- Validate each surface-level change with its own A/B before committing to a
  general theory.
- A harness bug (tokenizer) can produce results that look like a principled
  failure mode. Always print a few per-candidate scores and tokens before
  generalising from the ranking output.

## Related
- [[projects/CTX/research/20260426-ctx-retrieval-benchmark-synthesis|20260426-ctx-retrieval-benchmark-synthesis]]
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|20260426-g1-hybrid-rrf-dense-retrieval]]
- [[projects/CTX/research/20260426-g2-docs-eval-corpus-drift-fix|20260426-g2-docs-eval-corpus-drift-fix]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260408-g1-longterm-eval-initial-results|20260408-g1-longterm-eval-initial-results]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
