"""
ranker.py — G1 BM25/dense/hybrid ranker for bm25-memory.

Provides:
  dense_rank_decisions(corpus, query, top_k=20) -> list[dict]
  rrf_merge(list_a, list_b, k_rrf=60) -> list[dict]
  bm25_rank_decisions(corpus, query, top_k=7, ...) -> list[dict]
  hybrid_rank_decisions(corpus, query, top_k=7) -> list[dict]

Module-level mutable:
  last_retrieval_scores: dict  — bm25_top / dense_top captured per call,
                                 read by orchestrator for telemetry.
"""
import re

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

from .tokenizer import tokenize, expand_query_tokens
from .rerank import vec_embed as _vec_embed, cosine as _cosine, semantic_rerank_filter

# Module-level score capture — read by orchestrator via last_retrieval_scores
last_retrieval_scores: dict = {}


def dense_rank_decisions(corpus, query, top_k=20):
    """Dense first-stage retrieval: cosine similarity between query embedding
    and pre-computed corpus embeddings (from embed_corpus_items).

    Returns top-k items by cosine, or [] if vec-daemon unavailable or corpus
    has no embeddings (BM25-only fallback).
    """
    q_emb = _vec_embed(query)
    if not q_emb:
        return []
    scored = []
    for item in corpus:
        emb = item.get("emb")
        if not emb:
            continue
        cos = _cosine(q_emb, emb)
        if cos > 0.0:
            scored.append((cos, item))
    if not scored:
        return []
    scored.sort(key=lambda x: -x[0])
    last_retrieval_scores["dense_top"] = float(scored[0][0])
    return [item for _, item in scored[:top_k]]


def rrf_merge(list_a, list_b, k_rrf=60):
    """Reciprocal Rank Fusion of two ranked lists.

    k_rrf=60: optimal constant per BEIR paper (arXiv:2104.08663) — controls
    score distribution across rank positions.

    Uses commit 'hash' as dedup key; falls back to first-20-chars of 'text'.
    Returns merged list ordered by RRF score (descending).
    """
    scores = {}
    hash_to_item = {}

    def _key(item):
        return item.get("hash") or (item.get("text") or "")[:20]

    for rank, item in enumerate(list_a, 1):
        k = _key(item)
        scores[k] = scores.get(k, 0.0) + 1.0 / (k_rrf + rank)
        hash_to_item[k] = item

    for rank, item in enumerate(list_b, 1):
        k = _key(item)
        scores[k] = scores.get(k, 0.0) + 1.0 / (k_rrf + rank)
        hash_to_item[k] = item

    merged_keys = sorted(scores.keys(), key=lambda h: -scores[h])
    return [hash_to_item[h] for h in merged_keys]


def bm25_rank_decisions(corpus, query, top_k=7, min_score=0.5,
                        adaptive_floor_ratio=0.35, mmr_jaccard_threshold=0.70,
                        skip_rerank=False):
    """BM25-rank decision corpus against query, return top-k.

    Stopwords are dropped from the query (not the corpus) so conversational
    fillers like "i/to/how/would" don't dominate the ranking.

    `min_score`: if the best-matching decision scores below this, return [].
    Prevents the "no-topic-match → fallback to most-recent-7" anti-pattern
    where zero-score or near-zero queries got ranked purely by git-log order.

    `adaptive_floor_ratio` (NEW 2026-04-24): candidates below
        top_score * adaptive_floor_ratio are dropped. Eliminates the
        "surface-token match" noise where a hit scores just above min_score
        but is 3-5× worse than the actual best hit (e.g., 'iter 47/∞: token%'
        scoring 1.2 when the real match scores 4.0).

    `mmr_jaccard_threshold` (NEW 2026-04-24): if a candidate's token set has
        Jaccard similarity >= threshold with any already-selected item, skip it.
        Collapses clustered noise like multiple 'live-infinite iter N/∞' entries
        that are near-duplicates — keeps only the best of each cluster.
    """
    if not corpus:
        return []
    if not HAS_BM25 or not query.strip():
        return []

    query_tokens = tokenize(query, drop_stopwords=True)
    if not query_tokens:
        return []

    # Layer 2 (2026-04-24): synonym expansion to bridge KO↔EN + concept gaps
    query_tokens = expand_query_tokens(query_tokens)

    tokenized = [tokenize(c["text"]) for c in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query_tokens)
    if len(scores) == 0 or float(max(scores)) < min_score:
        return []

    top_score = float(max(scores))
    last_retrieval_scores["bm25_top"] = top_score
    adaptive_floor = max(min_score, top_score * adaptive_floor_ratio)

    ranked_idx = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)

    # Cluster signature: normalizes "live-infinite iter N/∞: goal_vM" boilerplate
    # so different iter-numbers don't escape MMR dedup.
    def _cluster_sig(subject: str) -> str:
        s = subject.lower()
        s = re.sub(r'\b\d{4,}\b|\b\d+/\d+\b|\b\d+/∞\b|goal_v\d+', '', s)
        s = re.sub(r'iter\s*\d+', 'iter', s)
        s = re.sub(r'[^a-z가-힣\s]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return ' '.join(s.split()[:4])

    selected = []
    selected_token_sets = []
    selected_cluster_sigs = set()
    for idx in ranked_idx:
        if scores[idx] < adaptive_floor:
            break
        cand_tokens = set(tokenized[idx])
        if not cand_tokens:
            continue
        cand_sig = _cluster_sig(corpus[idx].get("subject", corpus[idx].get("text", "")))
        if cand_sig and cand_sig in selected_cluster_sigs:
            continue
        is_near_dup = False
        for prev_tokens in selected_token_sets:
            union = cand_tokens | prev_tokens
            if not union:
                continue
            jaccard = len(cand_tokens & prev_tokens) / len(union)
            if jaccard >= mmr_jaccard_threshold:
                is_near_dup = True
                break
        if is_near_dup:
            continue
        selected.append(corpus[idx])
        selected_token_sets.append(cand_tokens)
        if cand_sig:
            selected_cluster_sigs.add(cand_sig)
        if len(selected) >= top_k * 2:
            break
    if not skip_rerank and len(selected) >= top_k + 2:
        selected = semantic_rerank_filter(selected, query, top_k=top_k)
    return selected[:top_k]


def hybrid_rank_decisions(corpus, query, top_k=7):
    """Hybrid BM25+dense retrieval with RRF merge — SOTA method per MAB/LongMemEval.

    Pipeline (2026-04-26):
      1. BM25 top-(top_k*2) with MMR/cluster dedup, NO semantic rerank yet
      2. Dense top-(top_k*2) using pre-embedded corpus via vec-daemon cosine
      3. RRF merge (k=60) — union of both candidate pools
      4. Semantic rerank (BGE cross-encoder → vec-daemon bi-encoder fallback)

    Fail-safe: if dense_rank_decisions() returns [] (vec-daemon down or no embeddings),
    falls back to BM25-only + semantic rerank (existing behavior).
    """
    bm25_cands = bm25_rank_decisions(corpus, query, top_k=top_k * 2, skip_rerank=True)
    if not bm25_cands:
        return []

    dense_cands = dense_rank_decisions(corpus, query, top_k=top_k * 2)

    if not dense_cands:
        if len(bm25_cands) >= top_k + 2:
            bm25_cands = semantic_rerank_filter(bm25_cands, query, top_k=top_k)
        return bm25_cands[:top_k]

    merged = rrf_merge(bm25_cands, dense_cands, k_rrf=60)

    if len(merged) >= top_k + 2:
        merged = semantic_rerank_filter(merged, query, top_k=top_k)

    return merged[:top_k]
