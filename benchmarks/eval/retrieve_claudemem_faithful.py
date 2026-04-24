"""
retrieve_claudemem_faithful.py — faithful claude-mem retrieval replication.

Distinct from our existing `chroma` retriever (which indexes raw session turns).
claude-mem's ACTUAL pipeline summarizes each session via Claude CLI first,
then indexes the SUMMARY into Chroma. The summarization step is what the paper
hypothesizes collapses conflict-resolution information.

Pipeline:
  1. For each session, call LLM to produce a short summary (claude-mem uses
     structured {title, narrative, facts, concepts}; we use one-line synthesis)
  2. Index summaries into a fresh Chroma collection (all-MiniLM-L6-v2 default)
  3. Query → top-k summaries
  4. Return summaries as "memories" to the answer pipeline

Cost: 1 LLM summarization call per session per question. For MAB N=10 × ~11
sessions = 110 summary calls per retriever run. Cached to disk by hash so
repeated runs are free.

Purpose: measure the REAL gap between raw-turn Chroma (our proxy) and
summary-indexed Chroma (faithful claude-mem). If they match → proxy is
defensible. If they diverge → paper must use faithful.
"""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))
from downstream_llm_eval import get_llm_client, call_llm

CACHE_DIR = Path("/tmp/claudemem_summary_cache")
CACHE_DIR.mkdir(exist_ok=True)

SUMMARY_SYS = (
    "You are claude-mem, a memory compression agent. Summarize the following "
    "conversation session into ONE concise observation that captures decisions, "
    "state changes, and key facts. Format: single sentence, <=150 chars. "
    "Focus on what the user/assistant decided or discovered — NOT what they "
    "merely discussed. If the session reverses a prior decision, make that "
    "reversal explicit in the summary."
)


def _session_hash(turns: List[Dict]) -> str:
    text = "\n".join(f"{t.get('role','')}:{t.get('content','')[:200]}" for t in turns)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _summarize_session(client, turns: List[Dict]) -> str:
    """One-sentence session summary, cached by content hash."""
    if not turns:
        return ""
    h = _session_hash(turns)
    cache = CACHE_DIR / f"{h}.txt"
    if cache.exists():
        return cache.read_text().strip()
    text = "\n".join(f"{t.get('role','user')}: {t.get('content','')[:300]}" for t in turns[:20])
    summary = call_llm(client, SUMMARY_SYS, f"Session:\n{text}", max_tokens=1024)
    if summary.startswith("["):
        summary = text[:200]   # fallback: use raw text as summary
    # Clean: first line only, strip quotes
    summary = summary.strip().split("\n")[0].strip().strip('"').strip("'")[:300]
    cache.write_text(summary)
    return summary


def retrieve_claudemem_faithful(query: str, haystack: List[Dict], top_k: int = 5) -> List[str]:
    """Faithful claude-mem replication: summarize-then-dense-retrieve."""
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print("[claudemem-faithful] chromadb not installed", file=sys.stderr)
        return []
    client = get_llm_client()
    if client is None:
        print("[claudemem-faithful] no LLM client for summarization", file=sys.stderr)
        return []
    # Summarize each session (cached)
    summaries = []
    for s_idx, sess in enumerate(haystack):
        if isinstance(sess, dict):
            turns = sess.get("turns", [])
        elif isinstance(sess, list):
            turns = sess
        else:
            continue
        summary = _summarize_session(client, turns)
        if summary:
            summaries.append((s_idx, summary))
    if not summaries:
        return []
    # Index summaries in fresh Chroma
    chroma_client = chromadb.Client()
    coll = chroma_client.get_or_create_collection(
        f"claudemem-faithful-{id(haystack)}",
        embedding_function=embedding_functions.DefaultEmbeddingFunction(),
    )
    docs = [s for _, s in summaries]
    ids = [f"s{i}" for i, _ in summaries]
    try:
        coll.upsert(documents=docs, ids=ids)
        res = coll.query(query_texts=[query], n_results=top_k)
        return res.get("documents", [[]])[0]
    except Exception as e:
        print(f"[claudemem-faithful] chroma error: {e}", file=sys.stderr)
        return []


if __name__ == "__main__":
    # Smoke: MAB case 1 (rerank layer reversal)
    import os, sys
    if not os.environ.get("MINIMAX_API_KEY"):
        print("set MINIMAX_API_KEY first"); sys.exit(1)
    haystack = [
        {"session_id": "initial", "turns": [
            {"role": "user", "content": "Using cosine similarity for reranking."}]},
        {"session_id": "d1", "turns": [{"role": "user", "content": "Discussing office layout."}]},
        {"session_id": "d2", "turns": [{"role": "user", "content": "Ordering pizza."}]},
        {"session_id": "reversal", "turns": [
            {"role": "user", "content": "Replaced cosine with BGE cross-encoder for stronger semantic signal."}]},
    ]
    q = "What reranker does the pipeline use?"
    print(f"Query: {q}\n")
    mems = retrieve_claudemem_faithful(q, haystack, top_k=3)
    print(f"returned {len(mems)} memories:")
    for m in mems:
        print(f"  - {m[:120]}")
