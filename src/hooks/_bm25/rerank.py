"""
rerank.py — Semantic rerank helpers for bm25-memory.

Three layers:
  1. bi-encoder rerank via vec-daemon (e5-small, CPU-friendly, ~20ms/candidate)
  2. Korean-English synonym expansion (zero-cost lexical bridge) — in tokenizer.py
  3. BGE cross-encoder rerank (GPU, ~50ms for top-20, +15-25%p quality)
Layer 3 is opt-in via CTX_CROSS_ENCODER=1 env var.

Provides:
  VEC_SOCK, VEC_DISABLED           — vec-daemon config (read by orchestrator)
  BGE_SOCK, USE_CROSS_ENCODER      — bge-daemon config (read by orchestrator)
  vec_embed(text) -> list|None
  cosine(a, b) -> float
  semantic_rerank_filter(candidates, query, top_k, ...) -> list
"""
import json
import os
from pathlib import Path

# ── Vec-daemon config ────────────────────────────────────────────────────────

VEC_SOCK = Path.home() / ".local/share/claude-vault/vec-daemon.sock"
VEC_TIMEOUT = 0.8   # seconds — fail fast if daemon is down
VEC_DISABLED = os.environ.get("CTX_DISABLE_SEMANTIC_RERANK") == "1"

# ── BGE cross-encoder config ─────────────────────────────────────────────────

BGE_SOCK = Path.home() / ".local/share/claude-vault/bge-daemon.sock"
BGE_TIMEOUT = 2.0   # seconds — rerank 20 cands typically <80ms, give slack
USE_CROSS_ENCODER = os.environ.get("CTX_CROSS_ENCODER", "1") != "0"


def _bge_rerank(query: str, docs: list):
    """Query the running bge-daemon for cross-encoder scores.

    Returns list[float] (raw logits, same length as docs) or None on failure.
    Caller applies sigmoid + filtering. Fail-fast: 2s timeout keeps the hook
    responsive if the daemon is wedged.
    """
    if not USE_CROSS_ENCODER or not BGE_SOCK.exists():
        return None
    try:
        import socket as _sk
        s = _sk.socket(_sk.AF_UNIX, _sk.SOCK_STREAM)
        s.settimeout(BGE_TIMEOUT)
        s.connect(str(BGE_SOCK))
        payload = (json.dumps({"query": query[:400],
                               "docs": [str(d)[:400] for d in docs]}) + "\n").encode("utf-8")
        s.sendall(payload)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        resp = json.loads(buf.split(b"\n")[0].decode("utf-8"))
        if resp.get("ok"):
            return resp.get("scores")
    except Exception:
        return None
    return None


def vec_embed(text: str):
    """Query the running vec-daemon for an embedding. Returns list[float] or None.
    Uses the same Unix socket protocol as chat-memory.py; 0 if daemon is down."""
    if VEC_DISABLED or not VEC_SOCK.exists():
        return None
    try:
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(VEC_TIMEOUT)
        s.connect(str(VEC_SOCK))
        payload = (json.dumps({"q": text[:1000]}) + "\n").encode("utf-8")
        s.sendall(payload)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(8192)
            if not chunk:
                break
            buf += chunk
        s.close()
        line = buf.split(b"\n")[0]
        resp = json.loads(line.decode("utf-8"))
        if resp.get("ok"):
            return resp.get("emb")
    except Exception:
        return None
    return None


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    import math  # noqa: F401 (math.exp not used here but kept for clarity)
    dot = sum(x * y for x, y in zip(a, b))
    # embeddings from vec-daemon are already normalized → dot = cosine
    return max(0.0, min(1.0, dot))


def semantic_rerank_filter(candidates, query, top_k, alpha_bm25=0.6,
                           cosine_min=0.55, bm25_scores=None):
    """Rerank a list of candidate items by blended BM25 + cosine semantic.

    candidates: list of dicts, each with a 'text' or 'subject' field
    query: user query string
    top_k: final count
    alpha_bm25: weight of BM25 score in blend (1-alpha = semantic weight)
    cosine_min: hard floor — items below this cosine get dropped even if BM25 is high
    bm25_scores: optional pre-computed BM25 scores (normalized 0-1); if None,
                 assume candidates are already ordered by BM25 → use rank position

    Fail-safe: if vec-daemon is down, returns candidates[:top_k] (no-op).

    Layer 3 (2026-04-24): prefer BGE cross-encoder when available — it scores
    (query, candidate) jointly instead of computing independent embeddings +
    cosine. Much stronger semantic judgement on short commit subjects.
    Falls back to bi-encoder cosine path if cross-encoder fails to load.
    """
    # ── Layer 3: bge-daemon cross-encoder path (strongest semantic signal) ───
    kept = []
    doc_texts = []
    for i, c in enumerate(candidates):
        text = c.get("subject") or c.get("text") or ""
        if not text:
            continue
        kept.append((i, c))
        doc_texts.append(text[:400])
    if doc_texts:
        ce_scores = _bge_rerank(query, doc_texts)
        if ce_scores is not None and len(ce_scores) == len(kept):
            import math
            def _sig(x): return 1.0 / (1.0 + math.exp(-float(x)))
            rescored = []
            ce_min = 0.35
            for (i, c), s in zip(kept, ce_scores):
                ce_norm = _sig(s)
                if ce_norm < ce_min:
                    continue
                bm25_norm = (bm25_scores[i] if bm25_scores else (len(candidates) - i) / max(1, len(candidates)))
                blend = alpha_bm25 * bm25_norm + (1.0 - alpha_bm25) * ce_norm
                rescored.append((blend, ce_norm, c))
            rescored.sort(key=lambda x: -x[0])
            if rescored:
                return [c for _, _, c in rescored[:top_k]]
            # CE filtered everything → fall back to bi-encoder

    # ── Bi-encoder fallback (original path) ───
    q_emb = vec_embed(query)
    if not q_emb:
        return candidates[:top_k]   # daemon down → no-op

    rescored = []
    for i, c in enumerate(candidates):
        text = c.get("subject") or c.get("text") or ""
        if not text:
            continue
        c_emb = vec_embed(text[:400])   # short for speed
        if not c_emb:
            continue
        cos = cosine(q_emb, c_emb)
        if cos < cosine_min:
            continue   # hard drop — semantic dissimilarity overrides BM25 rank
        bm25_norm = (bm25_scores[i] if bm25_scores else (len(candidates) - i) / max(1, len(candidates)))
        blend = alpha_bm25 * bm25_norm + (1.0 - alpha_bm25) * cos
        rescored.append((blend, cos, c))
    rescored.sort(key=lambda x: -x[0])
    return [c for _, _, c in rescored[:top_k]]
