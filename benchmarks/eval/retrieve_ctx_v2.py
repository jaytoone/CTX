"""
retrieve_ctx_v2.py — Stemmed BM25 + recency-aware boost for MAB.

Addresses the two failure modes diagnosed in
docs/research/20260424-mab-recency-tokenization-gap.md:
  1. Tokenization gap ("logs" vs "logging") — fixed by Porter stemmer
  2. First-fact-wins — fixed by recency multiplier favoring later sessions

This is an EXPERIMENTAL retriever for conflict-resolution benchmarks.
Production bm25-memory.py does NOT yet use stemming (preserves exact-match
token discriminability for git-commit subjects). A production migration
would require measuring whether stemming helps or hurts the existing
G1 benchmark first.
"""
from __future__ import annotations
import math
import re
import sys
from pathlib import Path
from typing import List, Dict

try:
    from nltk.stem.porter import PorterStemmer
    _STEMMER = PorterStemmer()
    HAS_STEMMER = True
except ImportError:
    _STEMMER = None
    HAS_STEMMER = False


def _stem_tokens(text: str) -> List[str]:
    toks = re.findall(r"\w+", text.lower())
    if not HAS_STEMMER:
        return toks
    return [_STEMMER.stem(t) for t in toks]


def retrieve_ctx_v2(question: str, haystack: List[Dict], top_k: int = 7,
                    beta: float = 0.5) -> List[str]:
    """Stemmed BM25 + recency-ordered tie-break.

    - Stemming: "logs"/"logging" collapse to "log" so the reversal session
      (which uses "logging") matches a query about "logs".
    - Recency boost: later sessions multiplied by 1 + beta*log(1+idx), so
      when initial and reversal both score, reversal wins.
    - BM25 applied over session-flattened turn corpus; session_index
      tracked for the recency multiplier.
    """
    from rank_bm25 import BM25Okapi

    corpus = []
    for s_idx, sess in enumerate(haystack):
        sid = sess.get("session_id", f"s{s_idx}")
        for t_idx, turn in enumerate(sess.get("turns", [])):
            txt = turn.get("content", "")[:400]
            if not txt.strip():
                continue
            corpus.append({
                "subject": f"[{sid}/t{t_idx}] {txt}",
                "tokens": _stem_tokens(txt),
                "session_index": s_idx,
            })
    if not corpus:
        return []
    q_tokens = _stem_tokens(question)
    bm25 = BM25Okapi([c["tokens"] for c in corpus])
    raw = bm25.get_scores(q_tokens)
    scored = []
    for i, c in enumerate(corpus):
        mult = 1.0 + beta * math.log(1.0 + c["session_index"])
        score = raw[i] * mult
        if raw[i] > 0.01:
            scored.append((score, c["subject"]))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:top_k]]


if __name__ == "__main__":
    # Smoke against the exact MAB failure case
    haystack = [
        {"session_id": "initial", "turns": [{"role": "user",
            "content": "Logs stream to stdout only."}]},
        {"session_id": "d1", "turns": [{"role": "user",
            "content": "mentioning a holiday"}]},
        {"session_id": "d2", "turns": [{"role": "user",
            "content": "discussing weekend plans"}]},
        {"session_id": "d3", "turns": [{"role": "user",
            "content": "reviewing a PR about typo fixes"}]},
        {"session_id": "d4", "turns": [{"role": "user",
            "content": "ordering lunch"}]},
        {"session_id": "reversal", "turns": [{"role": "user",
            "content": "Added structured JSONL logging to live-progress.log alongside stdout."}]},
    ]
    q = "Where do logs go now?"
    print(f"Query: {q}")
    print(f"Stemmer available: {HAS_STEMMER}")
    hits = retrieve_ctx_v2(q, haystack, top_k=3)
    print(f"\nretrieve_ctx_v2 returned {len(hits)}:")
    for m in hits:
        marker = "←" if "reversal" in m else " "
        print(f"  {marker} {m[:100]}")
