"""
retrieve_ctx_v3.py — Hybrid cascade: stemmed BM25 + dense fallback.

P3 remediation for the paraphrase/cross-vocab gap.

Architecture:
  1. Run stemmed BM25 (ctx_v2) top-k
  2. If BM25 returns fewer than fallback_threshold hits with score > 0 → supplement
     with Chroma top-k (all-MiniLM-L6-v2 embeddings)
  3. De-duplicate; preserve BM25 order for items where both agreed
  4. Rerank union via recency boost (same as ctx_v2)

Design rationale:
  BM25 alone fails when query vocabulary does not overlap reversal content
  (e.g. 'reranker' vs 'BGE cross-encoder'). Chroma alone loses exact-match
  signal. The cascade: BM25 first (fast, exact-match priority); Chroma
  rescues when BM25 set is sparse or misses the reversal session.

Falls back to pure ctx_v2 if chromadb is not installed.
"""
from __future__ import annotations
import math
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from retrieve_ctx_v2 import retrieve_ctx_v2, _stem_tokens

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


def _chroma_retrieve(query: str, haystack: List[Dict], top_k: int = 5) -> List[tuple]:
    """Returns list of (content, session_index, score).

    Note: uses UUID collection names — id(haystack) is not unique (Python
    recycles IDs after GC) and chromadb.Client() singleton persists
    collections in-memory. Observed 2026-04-25: id()-based names caused a
    0.88→0.12 MAB N=50 regression when ctx_v3 ran after claudemem_faithful
    in the same process. Delete after use so the singleton doesn't OOM.
    """
    if not HAS_CHROMA:
        return []
    import uuid as _uuid
    client = chromadb.Client()
    coll_name = f"ctx-v3-{_uuid.uuid4().hex[:12]}"
    coll = client.get_or_create_collection(
        coll_name,
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
    )
    docs, ids, metadatas = [], [], []
    for s_idx, sess in enumerate(haystack):
        sid = sess.get("session_id", f"s{s_idx}")
        for t_idx, turn in enumerate(sess.get("turns", [])):
            txt = turn.get("content", "")[:400]
            if not txt.strip():
                continue
            docs.append(txt)
            ids.append(f"s{s_idx}-t{t_idx}")
            metadatas.append({"session_index": s_idx, "subject": f"[{sid}/t{t_idx}] {txt}"})
    if not docs:
        return []
    try:
        coll.upsert(documents=docs, ids=ids, metadatas=metadatas)
        res = coll.query(query_texts=[query], n_results=top_k, include=["documents", "metadatas"])
        out = []
        for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
            out.append((meta["subject"], meta["session_index"]))
        # Clean up collection so the singleton client doesn't retain it
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass
        return out
    except Exception:
        return []


def retrieve_ctx_v3(query: str, haystack: List[Dict], top_k: int = 7,
                    fallback_threshold: int = 2, beta: float = 0.5) -> List[str]:
    """Hybrid BM25 + Chroma cascade.

    Step 1: ctx_v2 (stemmed BM25 + recency)
    Step 2: if fewer than fallback_threshold hits → union with Chroma top-k
    Step 3: dedupe; preserve hybrid order
    """
    bm25_hits = retrieve_ctx_v2(query, haystack, top_k=top_k, beta=beta)

    # If BM25 got enough strong hits, return as-is
    if len(bm25_hits) >= fallback_threshold:
        return bm25_hits

    # Otherwise supplement with Chroma
    if not HAS_CHROMA:
        return bm25_hits   # no fallback available, return what we have

    chroma_hits = _chroma_retrieve(query, haystack, top_k=top_k)
    chroma_subjects = [s for s, idx in chroma_hits]

    # Merge: BM25 first (higher trust for exact match), then Chroma dedup'd
    seen = set(bm25_hits)
    merged = list(bm25_hits)
    for s in chroma_subjects:
        if s not in seen:
            merged.append(s)
            seen.add(s)
        if len(merged) >= top_k:
            break
    return merged[:top_k]


if __name__ == "__main__":
    # Smoke test: the failure cases where ctx_v2 struck out
    haystack = [
        {"session_id": "initial", "turns": [{"role": "user",
            "content": "Using cosine similarity for reranking."}]},
        {"session_id": "d1", "turns": [{"role": "user", "content": "discussing schedule"}]},
        {"session_id": "d2", "turns": [{"role": "user", "content": "ordering lunch"}]},
        {"session_id": "d3", "turns": [{"role": "user", "content": "weather chat"}]},
        {"session_id": "d4", "turns": [{"role": "user", "content": "coffee order"}]},
        {"session_id": "reversal", "turns": [{"role": "user",
            "content": "Replaced cosine with BGE cross-encoder for stronger semantic signal."}]},
    ]
    q = "What reranker does the pipeline use?"
    print(f"Query: {q}\n")
    print(f"ctx_v2 only:")
    for m in retrieve_ctx_v2(q, haystack, top_k=3):
        marker = "←" if "reversal" in m else " "
        print(f"  {marker} {m[:85]}")
    print(f"\nctx_v3 (BM25 + Chroma cascade):")
    for m in retrieve_ctx_v3(q, haystack, top_k=3):
        marker = "←" if "reversal" in m else " "
        print(f"  {marker} {m[:85]}")
