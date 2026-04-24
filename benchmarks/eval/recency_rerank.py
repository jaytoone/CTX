"""
recency_rerank.py — Recency-aware boost for BM25 decision retrieval.

Finding from iter 7: BM25 alone fails conflict-resolution because initial
and reversal sessions score similarly — BM25 order is insensitive to 'which
came later'. A reversal session MUST rank above its initial if we want
the LLM to answer with the CURRENT state.

Simple fix: apply a recency multiplier to BM25 scores based on session_index
position in the haystack. The haystack is already chronologically ordered
(initial fact → distractors → reversal) so session_index is a proxy for
time. Log-scale boost so the effect is material but doesn't dominate.

Formula:
  final_score = bm25_score * (1 + beta * log(1 + session_index))
  beta = 0.3 (default) — gives ~1.3x boost to the last session in a
         10-session haystack, enough to overcome typical BM25 ties.

This complements the existing bge-daemon cross-encoder rerank: BGE handles
SEMANTIC similarity (paraphrase/cross-lingual), recency_rerank handles
TEMPORAL precedence. Both can compose: BM25 → recency boost → BGE rerank.

Usage: a lightweight retriever wrapper used by tier1_memoryagentbench to
test the architectural claim that recency-aware ranking pushes MAB
Competency-4 accuracy higher.
"""
from __future__ import annotations
import importlib.util
import math
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

HOOK = Path.home() / ".claude" / "hooks" / "bm25-memory.py"


def _bm25_hook():
    spec = importlib.util.spec_from_file_location("bm25mem", str(HOOK))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def retrieve_ctx_recency(question: str, haystack: List[Dict], top_k: int = 7,
                         beta: float = 0.30) -> List[str]:
    """CTX BM25 with a per-session recency boost. Drop-in replacement for
    tier1_longmemeval.retrieve_ctx.

    Each haystack entry is a session with 0-based index; the LAST session
    gets the highest recency multiplier. This matches MemoryAgentBench
    semantics where chronological order is preserved in the haystack."""
    hook = _bm25_hook()
    corpus = []
    # Assign chronological weight per session
    for s_idx, sess in enumerate(haystack):
        sid = sess.get("session_id", f"s{s_idx}")
        for t_idx, turn in enumerate(sess.get("turns", [])):
            txt = turn.get("content", "")[:400]
            if not txt.strip():
                continue
            corpus.append({
                "subject": f"[{sid}/t{t_idx}] {txt}",
                "text": txt,
                "session_index": s_idx,   # <- used for recency
            })
    if not corpus:
        return []
    # Use raw BM25 scores so we can multiply. Avoids the MMR/cluster filters
    # in production bm25_rank_decisions; we want the recency-adjusted ordering.
    if not hook.HAS_BM25:
        return []
    from rank_bm25 import BM25Okapi
    tokenized = [hook.tokenize(c["text"]) for c in corpus]
    q_tokens = hook.tokenize(question, drop_stopwords=True)
    q_tokens = hook.expand_query_tokens(q_tokens)
    if not q_tokens:
        return []
    bm25 = BM25Okapi(tokenized)
    raw = bm25.get_scores(q_tokens)
    n_sessions = max(c["session_index"] for c in corpus) + 1
    # Apply recency multiplier: 1 + beta * log(1 + idx)
    boosted = []
    for i, c in enumerate(corpus):
        idx = c["session_index"]
        mult = 1.0 + beta * math.log(1.0 + idx)
        boosted.append((raw[i] * mult, c))
    boosted.sort(key=lambda x: -x[0])
    # Floor: drop if raw < small epsilon (prevents 0-BM25 from winning by boost alone)
    return [c["subject"] for score, c in boosted if score > 0.01][:top_k]


if __name__ == "__main__":
    # Smoke: build 3 mock sessions where reversal is the last
    haystack = [
        {"session_id": "initial", "turns": [{"role": "user",
            "content": "We chose TF-IDF for doc retrieval."}]},
        {"session_id": "distractor", "turns": [{"role": "user",
            "content": "Discussed the release schedule."}]},
        {"session_id": "reversal", "turns": [{"role": "user",
            "content": "Replaced TF-IDF with BM25 after benchmarking."}]},
    ]
    query = "What retrieval backend are we using?"
    mems = retrieve_ctx_recency(query, haystack, top_k=3)
    print(f"[recency-rerank] returned {len(mems)} memories:")
    for m in mems:
        print(f"  - {m[:90]}")
    # Compare to naive BM25 (without recency boost)
    sys.path.insert(0, "/home/jayone/Project/CTX/benchmarks/eval")
    from tier1_longmemeval import retrieve_ctx
    print(f"\n[naive bm25] returned:")
    for m in retrieve_ctx(query, haystack, top_k=3):
        print(f"  - {m[:90]}")
