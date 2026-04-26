# [live-inf iter 36/∞] G2-DOCS Hybrid BM25+Dense RRF — Doc Search Upgrade
**Date**: 2026-04-26  **Iteration**: 36

## Goal
Apply the same hybrid BM25+dense RRF pattern from G1 (iter 34) to G2-DOCS (doc/research file
search), completing the retrieval upgrade for all three CTX memory surfaces.

## Implementation

### New functions in `~/.claude/hooks/bm25-memory.py`

| Function | Purpose |
|---|---|
| `_docs_cache_key(units)` | Stable cache fingerprint from sorted doc filenames |
| `embed_docs_units(units, cache_path)` | Pre-embed 86 docs via vec-daemon; cache to `.omc/docs_corpus_emb.json` |
| `dense_rank_docs(units_emb, query, top_k=10)` | Cosine ranking over pre-embedded doc units |
| `hybrid_search_docs(project_dir, query, top_k=5)` | Full pipeline: BM25+dense→RRF→semantic rerank |

### Production wiring
G2-DOCS hook changed at line 1306: `bm25_search_docs(...)` → `hybrid_search_docs(...)`.
G2-DOCS header updated to reflect method: "BM25+dense RRF relevant research docs".

### Architecture
```
Before:
  query → BM25 tokenize → score 86 docs → threshold filter → BGE rerank → top-5

After:
  query → BM25 tokenize → score 86 docs → threshold filter → [BM25 cands]
        ↗                                                              ↘
  query → _vec_embed → cosine(q, pre-emb[86]) → sort → [dense cands] → RRF merge
                                                                              ↓
                                                              [union] → BGE rerank → top-5
```

### Cache
86/86 docs embedded on first call (4s one-time, amortized). Cache key = fingerprint of
sorted filenames — auto-invalidates when docs are added/removed.

## Live Comparison (3 queries)

### Query 1: "why did we switch from TF-IDF to BM25"
| | Results |
|---|---|
| BM25 | `semantic-gap-keyword-vs-contextual.md`, `g1-temporal-evaluation-framework.md`, `ctx-downstream-eval-complete.md` |
| **Hybrid** | **`ctx-alternatives-research.md`**, `semantic-gap-keyword-vs-contextual.md`, **`g1-hybrid-rrf-dense-retrieval.md`** |

Dense added `ctx-alternatives-research.md` — THE document recording the TF-IDF→BM25 decision
(2026-03-27 CTX alternatives research). BM25 missed it because the switch decision is described
with different vocabulary than the query ("rank_bm25", "BM25Okapi", "performance comparison"
vs "switched", "TF-IDF to BM25").

### Query 2: "vec-daemon socket stale connection fix"
| | Results |
|---|---|
| BM25 | `CLAUDE.md`, `vault-vector-migration.md`, `common-port-fanout-tailscale-vs-ssh.md` |
| **Hybrid** | `vault-vector-migration.md`, **`MEMORY.md`**, `CLAUDE.md` |

Dense added `MEMORY.md` — which has the 2026-04-17 note about "stale socket fix" for vec-daemon.
BM25 retrieved `common-port-fanout-tailscale-vs-ssh.md` (SSH/tailscale, irrelevant).

### Query 3: "retrieval node relevance verification methods"
Same 3 docs, better order: hybrid correctly ranks `retrieval-node-relevance-verification.md`
at #1 (vs BM25's #2).

## Architecture notes

### Why docs benefit less than G1
- Docs corpus (86 docs) is smaller than G1 corpus (174 commits)
- Docs have stronger keyword signals (research docs use consistent technical vocabulary)
- BM25 already achieves >0.95 Hit@3 on keyword-identical queries
- Dense primarily helps on paraphrase queries where the user uses different terminology

### Fail-safe behavior (same as G1)
| Condition | Behavior |
|---|---|
| vec-daemon up + docs embedded | Full hybrid (BM25+dense→RRF→BGE rerank) |
| vec-daemon down | Falls back to BM25+BGE rerank (existing behavior) |
| Dense candidates empty | Falls back to BM25+rerank |

## Impact on CTX retrieval surfaces

| Surface | Method (before) | Method (after) | Notes |
|---|---|---|---|
| CM (chat memory) | BM25+vec-daemon cosine (hybrid α=0.5) | unchanged | Already hybrid |
| G1 (decisions) | BM25+BGE rerank | **BM25+dense RRF+BGE** | iter 34, +1.7pp |
| **G2-DOCS (docs)** | BM25+BGE rerank | **BM25+dense RRF+BGE** | **this iter** |
| G2-CODE (codebase) | BM25 keyword | unchanged | no valid proxy benchmark |

All three retrieval surfaces now use hybrid BM25+dense where semantically meaningful.

## Related
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|iter 34 G1 hybrid RRF]]
- [[projects/CTX/research/20260426-retrieval-node-relevance-verification|retrieval node relevance]]
- [[projects/CTX/research/20260417-ctx-semantic-search-upgrade-sota|semantic upgrade SOTA roadmap]]
