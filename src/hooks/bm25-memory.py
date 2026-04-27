#!/usr/bin/env python3
"""
bm25-memory: BM25-based reactive memory for Claude Code.
Replaces git-memory.py (G1 proactive, recall 0.169) + g2-augment.py (G2 graph).

G1: ALL git decision commits → BM25 query-time ranking → top-7 relevant to prompt
    Keyword-identical: Structural Recall@7=1.000 (inflated, token overlap=0.476)
    Paraphrase fair eval: Structural Recall@7=0.627 (bias=0.373, 20260410 g1_fair_eval.py)
    Type2/3/4 (why/what/rationale): Structural Recall@7=0.667
    Combined fair Recall@7=0.634 (71 queries) — vs proactive 0.169 → 3.7x improvement
    Fix: CTX YYYYMMDD-prefix commits now recognized as decisions

G2a: docs/research/*.md + CLAUDE.md + MEMORY.md → BM25 → top-5 relevant chunks
     Keyword-identical eval: 10/10 (1.000) | Paraphrase eval: 7/10 (0.700)
     Note: 1.000 is inflated — paraphrase 0.700 is the honest fairness-adjusted score
G2b: codebase graph (codebase-memory-mcp SQLite) → relevant code files (project-internal only)
     Fallback: git grep -c keyword ranking when no DB available
G2b-hooks: ~/.claude/hooks/*.py BM25 search (triggered by "hook/훅/bm25-memory/auto-index/..." keywords)
     Directly indexes hook file function signatures — solves G2b external file gap

Cache: .omc/decision_corpus.json (auto-invalidated on git HEAD change)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

RICH = "--rich" in sys.argv


# ── Tokenizer ────────────────────────────────────────────────────

_KO_PARTICLES = re.compile(
    r'(와|과|이|가|은|는|을|를|의|에서|으로|에게|부터|까지|처럼|같이|보다|이나|며|에|로|도|만|나|고)$'
)

# Conversational stopwords — filtered from QUERIES only (not the corpus).
# These appear in nearly every conversational prompt and make BM25 return
# noise matches on common words instead of real topic terms.
# Kept conservative — only words that are almost never content-bearing in
# a software-engineering commit subject.
_STOPWORDS = frozenset([
    # English function words
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "am", "do", "does", "did", "have", "has", "had", "will", "would",
    "could", "should", "may", "might", "can", "to", "of", "in", "on",
    "at", "by", "for", "with", "from", "as", "into", "about",
    "and", "or", "but", "if", "then", "than", "so", "not", "no",
    "i", "you", "we", "he", "she", "it", "they", "me", "my", "your",
    "our", "his", "her", "their", "this", "that", "these", "those",
    "there", "here", "what", "which", "when", "where", "why", "how",
    "who", "whom", "some", "any", "all", "each", "every", "both",
    "more", "most", "less", "few", "much", "many",
    "just", "only", "very", "too", "also", "even", "still", "yet",
    "now", "then", "up", "down", "out", "over", "again",
    # Conversational fillers
    "ok", "yeah", "yep", "pls", "please", "thanks", "thank",
    "hi", "hey", "hello", "want", "like", "think", "need",
    "make", "use", "using", "try", "trying", "get", "got",
    # Korean fillers (particles already stripped; these are standalone)
    "음", "어", "아", "그", "저", "이거", "저거", "그거",
])


# ── Semantic rerank helpers (2026-04-24) ────────────────────────────────
# Three layers:
#   1. bi-encoder rerank via vec-daemon (e5-small, CPU-friendly, ~20ms/candidate)
#   2. Korean-English synonym expansion (zero-cost lexical bridge)
#   3. BGE cross-encoder rerank (GPU, ~50ms for top-20, +15-25%p quality)
# Layer 3 is opt-in via CTX_CROSS_ENCODER=1 env var; loads lazily on first use.

_VEC_SOCK = Path.home() / ".local/share/claude-vault/vec-daemon.sock"
_VEC_TIMEOUT = 0.8   # seconds — fail fast if daemon is down
_VEC_DISABLED = os.environ.get("CTX_DISABLE_SEMANTIC_RERANK") == "1"

# ── Auto-tune: read flywheel parameter recommendations (ctx-telemetry tune output) ──
_AUTO_TUNE_PATH = Path.home() / ".claude" / "ctx-auto-tune.json"
_AUTO_TUNE: dict = {}
_AUTO_TUNE_ACTIVE: bool = False
try:
    if _AUTO_TUNE_PATH.exists():
        _auto_tune_raw = json.loads(_AUTO_TUNE_PATH.read_text())
        if isinstance(_auto_tune_raw, dict):
            _AUTO_TUNE = _auto_tune_raw
            _AUTO_TUNE_ACTIVE = True
except Exception:
    pass

# Retrieval score capture: populated by bm25_rank_decisions / dense_rank_decisions
# so callers can read top_score_bm25 / top_score_dense without signature changes.
_last_retrieval_scores: dict = {}

# bge-daemon: BGE cross-encoder served over Unix socket (same pattern as vec-daemon).
# Hook stays fast because the 7s model load happens ONCE in the daemon, not per
# UserPromptSubmit. Default ON; disable via CTX_CROSS_ENCODER=0 if daemon is down
# and we don't want even the 0.8s connect-timeout cost per prompt.
_BGE_SOCK = Path.home() / ".local/share/claude-vault/bge-daemon.sock"
_BGE_TIMEOUT = 2.0   # seconds — rerank 20 cands typically <80ms, give slack
_USE_CROSS_ENCODER = os.environ.get("CTX_CROSS_ENCODER", "1") != "0"

# Small Korean-English synonym map for query expansion (Layer 2).
# Keys are case-folded. Additions expand the query token set — BM25 will match
# commits mentioning either side of each pair. Focused on CTX domain vocabulary
# that commonly appears in Korean prompts but English commits (and vice versa).
_SYNONYM_EXPANSION = {
    "cross-session":   ["long-term", "persistent", "inter-session", "장기기억"],
    "long-term":       ["cross-session", "persistent", "장기", "장기기억"],
    "memory":          ["recall", "retrieval", "기억"],
    "retrieval":       ["search", "recall", "fetch", "검색", "조회"],
    "search":          ["retrieval", "lookup", "검색"],
    "hook":            ["plugin", "extension", "훅"],
    "embed":           ["embedding", "vector", "임베딩"],
    "embedding":       ["embed", "vector", "임베딩"],
    "rerank":          ["rank", "reorder", "재정렬", "순위"],
    "semantic":        ["vector", "dense", "의미"],
    "context":         ["memory", "state", "컨텍스트"],
    "prompt":          ["query", "question", "프롬프트"],
    "improve":         ["enhance", "boost", "optimize", "개선", "향상"],
    "quality":         ["accuracy", "score", "품질"],
    "noise":           ["garbage", "irrelevant", "노이즈"],
    "cluster":         ["group", "dedup", "중복"],
    "dashboard":       ["ui", "visualization", "대시보드"],
    "bootstrap":       ["install", "setup", "부트스트랩"],
    "gpu":             ["cuda", "device", "가속"],
    "claude":          ["anthropic", "llm"],
    "korean":          ["한국어", "ko", "hangul"],
    "기억":             ["memory", "recall"],
    "검색":             ["search", "retrieval"],
    "장기기억":          ["long-term memory", "cross-session", "persistent"],
    "의사결정":          ["decision", "choice"],
    "훅":               ["hook", "plugin"],
    "임베딩":            ["embedding", "vector"],
}


def expand_query_tokens(query_tokens):
    """Layer 2: bridge Korean<->English lexical gaps via synonym map.
    Returns the original tokens + synonym expansions (capped at 2x length)."""
    out = list(query_tokens)
    for t in query_tokens:
        syns = _SYNONYM_EXPANSION.get(t.lower())
        if syns:
            out.extend(syns)
    # Dedupe while preserving order
    seen = set(); uniq = []
    for t in out:
        k = t.lower()
        if k not in seen:
            seen.add(k); uniq.append(t)
    return uniq[:len(query_tokens) * 2 + 5]   # cap growth


def _bge_rerank(query: str, docs: list):
    """Query the running bge-daemon for cross-encoder scores.

    Returns list[float] (raw logits, same length as docs) or None on failure.
    Caller applies sigmoid + filtering. Fail-fast: 2s timeout keeps the hook
    responsive if the daemon is wedged.
    """
    if not _USE_CROSS_ENCODER or not _BGE_SOCK.exists():
        return None
    try:
        import socket as _sk
        s = _sk.socket(_sk.AF_UNIX, _sk.SOCK_STREAM)
        s.settimeout(_BGE_TIMEOUT)
        s.connect(str(_BGE_SOCK))
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


def _vec_embed(text: str):
    """Query the running vec-daemon for an embedding. Returns list[float] or None.
    Uses the same Unix socket protocol as chat-memory.py; 0 if daemon is down."""
    if _VEC_DISABLED or not _VEC_SOCK.exists():
        return None
    try:
        import socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(_VEC_TIMEOUT)
        s.connect(str(_VEC_SOCK))
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


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    import math
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
    # Calls the resident bge-daemon over Unix socket. Daemon holds BGE weights
    # in GPU memory so hook pays ~50ms per rerank, not the 7s cold-load.
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
    q_emb = _vec_embed(query)
    if not q_emb:
        return candidates[:top_k]   # daemon down → no-op

    rescored = []
    for i, c in enumerate(candidates):
        text = c.get("subject") or c.get("text") or ""
        if not text:
            continue
        c_emb = _vec_embed(text[:400])   # short for speed
        if not c_emb:
            continue
        cos = _cosine(q_emb, c_emb)
        if cos < cosine_min:
            continue   # hard drop — semantic dissimilarity overrides BM25 rank
        # Normalize BM25 to [0,1] by rank position (top = 1.0, bottom = ~0)
        bm25_norm = (bm25_scores[i] if bm25_scores else (len(candidates) - i) / max(1, len(candidates)))
        blend = alpha_bm25 * bm25_norm + (1.0 - alpha_bm25) * cos
        rescored.append((blend, cos, c))
    rescored.sort(key=lambda x: -x[0])
    return [c for _, _, c in rescored[:top_k]]


# Porter stemmer (opt-in via CTX_STEM=1, default ON 2026-04-24 after G1 regression
# showed +0.034 improvement on Recall@7 with zero losses. See
# benchmarks/results/g1_regression_ctx_v2.json).
# Rationale: collapses "logs"/"logging"/"logged" → "log" so queries match stem-
# variants in commit subjects. Especially important for conflict-resolution
# (MAB Competency-4) where reversal vocab shifts (e.g. "rerank" → "reranking").
_USE_STEMMER = os.environ.get("CTX_STEM", "1") != "0"
_STEMMER = None
if _USE_STEMMER:
    try:
        from nltk.stem.porter import PorterStemmer as _PS
        _STEMMER = _PS()
    except ImportError:
        _STEMMER = None   # stemming silently disabled if nltk not installed


def tokenize(text: str, drop_stopwords: bool = False):
    """Preserve decimal numbers (0.724) and numeric ranges (7-30) as single tokens.
    Also strips Korean particles from mixed Korean-ASCII tokens (e.g. 'BM25와' → 'bm25' + 'bm25와')
    so that Korean queries match English commit subjects correctly.

    When `drop_stopwords=True` (query-side only), conversational fillers are
    removed to prevent BM25 from matching on common words like "i", "to", "how",
    "would", etc. Corpus tokenization never drops stopwords — IDF handles those.

    Porter stemmer (2026-04-24): adds stemmed variant for each token so "logs"
    matches "logging". Preserves the original token too so exact-match precision
    is never lost (dedup handles duplicates). Opt-out via CTX_STEM=0.
    """
    raw = re.findall(r'\d+[-\u2013]\d+|\d+\.\d+|\w+', text.lower())
    result = []
    for tok in raw:
        if drop_stopwords and tok in _STOPWORDS:
            continue
        cleaned = _KO_PARTICLES.sub('', tok)
        if cleaned and cleaned != tok:
            if not (drop_stopwords and cleaned in _STOPWORDS):
                result.append(cleaned)
        result.append(tok)
        # Porter stem — adds a THIRD variant. Dedup at return preserves order
        # so original tokens remain ranked; stem is a recall-rescue fallback.
        if _STEMMER is not None and tok.isalpha() and len(tok) > 3:
            stemmed = _STEMMER.stem(tok)
            if stemmed != tok:
                result.append(stemmed)
    return list(dict.fromkeys(result))


# ── G1: Decision Corpus ──────────────────────────────────────────

_CONV_PREFIXES = (
    "feat:", "fix:", "refactor:", "perf:", "security:", "design:", "test:",
    "feat(", "fix(", "refactor(", "perf(",
)
_VERSION_RE = re.compile(r"^v\d+\.\d+")
_DECISION_KEYWORDS = (
    "pivot", "revert", "dead-end", "rejected", "chose", "switched",
    "CONVERGED", "failed", "success", "fix", "improvement",
    "benchmark", "eval", "decision", "iter",
)
_NOISE_PREFIXES = ("# ", "wip:", "merge ", 'revert "')
_STRICT_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+")
_OMC_ITER_RE = re.compile(r"^(omc-live|live-inf)\s+iter", re.IGNORECASE)
_EMBEDDED_DECISION_RE = re.compile(
    r"\s[-\u2014]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
    re.IGNORECASE,
)
_YYYYMMDD_RE = re.compile(r"^\d{8}\s")  # CTX-style: "20260408 G1 temporal..."


def _is_structural_noise(subject):
    s = subject.strip()
    if _OMC_ITER_RE.match(s):
        return True
    if _STRICT_VERSION_RE.match(s):
        return not bool(_EMBEDDED_DECISION_RE.search(s))
    return False


def _is_decision(subject):
    """Detect decision commits: conventional, version-tagged, YYYYMMDD, or keyword."""
    s = subject.strip()
    if not s:
        return False
    sl = s.lower()
    if any(sl.startswith(p) for p in _NOISE_PREFIXES):
        return False
    if any(sl.startswith(p) for p in _CONV_PREFIXES):
        return True
    if _VERSION_RE.match(s):
        return True
    if _YYYYMMDD_RE.match(s):  # CTX-style date-prefixed commits
        return True
    return any(kw.lower() in sl for kw in _DECISION_KEYWORDS)


# ── query_type classification (for retrieval_event schema v1.1) ──────────────
_TEMPORAL_KW = frozenset([
    "when", "history", "timeline", "progression", "what happened", "progress",
    "previously", "before", "after", "last time", "since", "ago", "recent",
    "changed", "evolution", "how long", "session", "yesterday", "last week",
    "진행", "역사", "이전", "지난", "타임라인", "최근", "변경", "이번",
])

def _classify_query_type(prompt: str) -> str:
    """Classify prompt into TEMPORAL / KEYWORD / SEMANTIC.

    TEMPORAL  — query is about history/timeline/progression
    KEYWORD   — short technical lookup (≤60 chars) or pure symbol/identifier
    SEMANTIC  — natural language conceptual query (default)
    """
    if not prompt:
        return "KEYWORD"
    pl = prompt.lower()
    if any(kw in pl for kw in _TEMPORAL_KW):
        return "TEMPORAL"
    words = pl.split()
    if len(words) <= 6:
        return "KEYWORD"
    return "SEMANTIC"


def get_git_head(project_dir):
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir, capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def build_decision_corpus(project_dir, n=500):
    """Extract all decision commits from git log (no cap)."""
    try:
        r = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H\x1f%s\x1f%ai"],
            cwd=project_dir, capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return []
    except Exception:
        return []

    corpus = []
    seen = set()
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 2)
        if len(parts) < 2:
            continue
        commit_hash = parts[0]
        subject = parts[1][:120]
        date = parts[2][:10] if len(parts) == 3 else ""

        if _is_structural_noise(subject):
            continue
        key = subject[:60]
        if key in seen:
            continue
        seen.add(key)

        if _is_decision(subject):
            # 고우선순위 패턴 → text 중복 삽입으로 BM25 가중치 증폭
            is_milestone = any(p in subject for p in [
                "CONVERGED", "pivot", "완성", "완료", "검증", "수렴", "FAILED", "KILL"
            ])
            text = f"{date} {subject}"
            if is_milestone:
                text = f"{text}\n{text}"  # 2배 가중치
            corpus.append({
                "hash": commit_hash,
                "subject": subject,
                "date": date,
                "text": text,
            })

    return corpus


def get_decision_corpus(project_dir):
    """Return cached corpus or rebuild if git HEAD changed.

    Extended (2026-04-26): also pre-embeds corpus items via vec-daemon and caches
    embeddings in the same file under an 'emb_head' sentinel. Embeddings allow
    dense first-stage retrieval (dense_rank_decisions) without per-query N socket
    calls. Falls back gracefully: if vec-daemon is down, items lack 'emb' field
    and dense_rank_decisions returns [].
    """
    cache_path = Path(project_dir) / ".omc" / "decision_corpus.json"
    head = get_git_head(project_dir)

    if cache_path.exists() and head:
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("head") == head:
                corpus = cached["corpus"]
                # Check if embeddings are fresh for this HEAD
                if cached.get("emb_head") != head:
                    n = embed_corpus_items(corpus)
                    if n > 0:
                        cache_path.write_text(json.dumps({
                            "head": head, "corpus": corpus, "emb_head": head
                        }))
                return corpus
        except Exception:
            pass

    corpus = build_decision_corpus(project_dir)
    if head and corpus:
        try:
            cache_path.parent.mkdir(exist_ok=True)
            embed_corpus_items(corpus)
            cache_path.write_text(json.dumps({
                "head": head, "corpus": corpus, "emb_head": head
            }))
        except Exception:
            pass
    return corpus


def embed_corpus_items(corpus):
    """Add 'emb' field to corpus items using vec-daemon. Modifies in-place.

    Only embeds items missing 'emb'. Returns count of newly embedded items.
    Fail-safe: if vec-daemon is down, items are left without 'emb' and
    dense_rank_decisions will return [] (BM25-only fallback).
    """
    embedded = 0
    for item in corpus:
        if item.get("emb"):
            continue
        text = (item.get("subject") or item.get("text") or "")[:400]
        if not text:
            continue
        emb = _vec_embed(text)
        if emb:
            item["emb"] = emb
            embedded += 1
    return embedded


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
    _last_retrieval_scores["dense_top"] = float(scored[0][0])
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
    # (e.g. "cross-session memory" now matches "persistent long-term 장기기억" too).
    query_tokens = expand_query_tokens(query_tokens)

    tokenized = [tokenize(c["text"]) for c in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query_tokens)
    if len(scores) == 0 or float(max(scores)) < min_score:
        return []

    top_score = float(max(scores))
    _last_retrieval_scores["bm25_top"] = top_score
    adaptive_floor = max(min_score, top_score * adaptive_floor_ratio)

    ranked_idx = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)

    # Cluster signature: normalizes "live-infinite iter N/∞: goal_vM" boilerplate
    # so different iter-numbers don't escape MMR dedup (MEMORY.md: "live-inf iter
    # N/∞ topic-dedup collapse" known issue).
    import re as _re
    def _cluster_sig(subject: str) -> str:
        s = subject.lower()
        s = _re.sub(r'\b\d{4,}\b|\b\d+/\d+\b|\b\d+/∞\b|goal_v\d+', '', s)
        s = _re.sub(r'iter\s*\d+', 'iter', s)
        s = _re.sub(r'[^a-z가-힣\s]', ' ', s)
        s = _re.sub(r'\s+', ' ', s).strip()
        # First 4 distinctive words form the cluster signature
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
        # Cluster dedup: skip if any selected item has the same normalized sig
        if cand_sig and cand_sig in selected_cluster_sigs:
            continue
        # MMR-lite: skip if too similar to already-selected items
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
        # Keep 2x the target so semantic rerank has room to re-order/filter
        if len(selected) >= top_k * 2:
            break
    # Layer 1 (2026-04-24): lowered gate — rerank fires for 60%+ of queries now,
    # was ~30% with `> top_k` (many queries returned exactly top_k candidates).
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

    Advantage over BM25-only: recovers nodes that BM25 misses entirely (zero score)
    but are semantically close to the query (e.g. synonyms, paraphrases, concept drift).

    Fail-safe: if dense_rank_decisions() returns [] (vec-daemon down or no embeddings),
    falls back to BM25-only + semantic rerank (existing behavior).
    """
    # Step 1: BM25 candidates (skip rerank here — we'll do it after RRF)
    bm25_cands = bm25_rank_decisions(
        corpus, query, top_k=top_k * 2,
        skip_rerank=True
    )
    if not bm25_cands:
        return []

    # Step 2: Dense candidates
    dense_cands = dense_rank_decisions(corpus, query, top_k=top_k * 2)

    if not dense_cands:
        # Dense unavailable — fall back to BM25 with rerank
        if len(bm25_cands) >= top_k + 2:
            bm25_cands = semantic_rerank_filter(bm25_cands, query, top_k=top_k)
        return bm25_cands[:top_k]

    # Step 3: RRF merge
    merged = rrf_merge(bm25_cands, dense_cands, k_rrf=60)

    # Step 4: Semantic rerank on merged pool
    if len(merged) >= top_k + 2:
        merged = semantic_rerank_filter(merged, query, top_k=top_k)

    return merged[:top_k]


# ── G2: Docs BM25 ────────────────────────────────────────────────

def _extra_doc_files(project_dir):
    """Return extra files to include in the docs index (project-agnostic)."""
    # MEMORY.md: ~/.claude/projects/{slug}/memory/MEMORY.md
    # Claude uses leading-dash slug: /home/foo/bar → -home-foo-bar
    slug = project_dir.replace("/", "-")
    memory_md = os.path.expanduser(f"~/.claude/projects/{slug}/memory/MEMORY.md")
    candidates = [
        os.path.join(project_dir, "CLAUDE.md"),
        os.path.join(project_dir, "README.md"),
        memory_md,
    ]
    return [p for p in candidates if os.path.exists(p)]


def chunk_document(filename, content):
    """Split by ## headers; each chunk = 'filename § header\\nbody'."""
    chunks = []
    parts = re.split(r"\n(?=## )", content)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        header = re.sub(r"^#+\s*", "", lines[0].strip())
        body = lines[1].strip() if len(lines) > 1 else ""
        text = f"{filename} § {header}\n{body}"
        if len(text) > 50:
            chunks.append(text[:2500])
    return chunks


def build_docs_bm25(project_dir):
    """Build BM25 index over docs/research/*.md + CLAUDE.md + MEMORY.md.
    Strategy: full-doc (no chunking) — A/B test 2026-04-11 confirms +9.1% recall@5
    vs header-chunked approach (0.758 vs 0.667 on 33 paraphrase pairs).
    Full-doc wins on temporal/open-set/perf queries where answers span multiple sections.
    """
    all_units = []
    docs_dir = Path(project_dir) / "docs" / "research"
    if docs_dir.exists():
        for md_file in sorted(docs_dir.glob("*.md")):
            try:
                text = f"{md_file.name}\n{md_file.read_text()}"
                if len(text) > 50:
                    all_units.append(text)
            except Exception:
                pass

    for fpath in _extra_doc_files(project_dir):
        try:
            p = Path(fpath)
            text = f"{p.name}\n{p.read_text()}"
            if len(text) > 50:
                all_units.append(text)
        except Exception:
            pass

    if not all_units or not HAS_BM25:
        return None, []
    tokenized = [tokenize(u) for u in all_units]
    return BM25Okapi(tokenized), all_units



# Korean→English expansion for G2-DOCS BM25 path (iter 44).
# Docs corpus is English; Korean queries must be expanded to match.
# These are CTX/ML domain terms that appear frequently in research docs.
_KO_EN_DOCS = {
    "하이브리드": "hybrid", "밀집": "dense", "검색": "search,retrieve",
    "재색인": "reindex", "인용": "citation", "거짓": "false",
    "양성": "positive", "시멘틱": "semantic", "지연": "latency",
    "시간": "time,latency", "수준": "tier,level",
    "벡터": "vector,embedding", "마이그레이션": "migration",
    "임베딩": "embedding", "벤치마크": "benchmark,eval",
    "메모리": "memory", "코드베이스": "codebase",
    "데이터베이스": "database", "오래된": "stale,staleness",
    "측정": "measure,probe", "비율": "rate,ratio",
    "성능": "performance,latency", "업그레이드": "upgrade",
    "노드": "node", "병합": "merge", "구현": "implementation",
    "분석": "analysis,evaluation", "아키텍처": "architecture",
    "평가": "eval,evaluate,benchmark", "프레임워크": "framework",
    "알고리즘": "algorithm", "최적화": "optimize,optimization",
    "자동": "auto,automatic", "색인": "index", "인덱스": "index",
}


def _expand_ko_en_docs(tokens):
    """Expand Korean tokens via _KO_EN_DOCS for G2-DOCS BM25 queries."""
    expanded = list(tokens)
    for t in tokens:
        mapping = _KO_EN_DOCS.get(t)
        if mapping:
            expanded.extend(mapping.split(","))
    return list(dict.fromkeys(expanded))


def bm25_search_docs(project_dir, query, top_k=5):
    """Return top-k docs most relevant to query (full-doc BM25, no chunking).
    Query-side stopword filter prevents conversational fillers from dominating.
    Korean queries are expanded via _KO_EN_DOCS before scoring (iter 44).
    """
    if not query.strip():
        return []
    bm25, units = build_docs_bm25(project_dir)
    if not bm25:
        return []
    query_tokens = tokenize(query, drop_stopwords=True)
    query_tokens = _expand_ko_en_docs(query_tokens)  # Korean→English expansion
    if not query_tokens:
        return []
    scores = bm25.get_scores(query_tokens)
    ranked = sorted(range(len(units)), key=lambda i: scores[i], reverse=True)
    # threshold=1.0: full-doc scores for relevant queries are 3.0-6.0; 0.0 = no overlap
    # adaptive floor (2026-04-24): also drop anything below 35% of top score
    top_score = float(max(scores)) if len(scores) else 0.0
    floor = max(1.0, top_score * 0.35)
    bm_filtered = [units[i] for i in ranked[:top_k * 2] if scores[i] >= floor]
    # Semantic rerank (2026-04-24 iter 2): dedupes BM25-surface hits from different meanings
    if len(bm_filtered) > top_k:
        # Each unit is "filename\ncontent"; wrap as dict for the reranker
        cand_dicts = [{"subject": u.split("\n", 1)[0], "text": u[:400]} for u in bm_filtered]
        reranked_dicts = semantic_rerank_filter(cand_dicts, query, top_k=top_k)
        # Map back to original units by subject (filename)
        subject_to_unit = {u.split("\n", 1)[0]: u for u in bm_filtered}
        return [subject_to_unit[d["subject"]] for d in reranked_dicts if d["subject"] in subject_to_unit]
    return bm_filtered[:top_k]


# ── G2-DOCS: Hybrid BM25+Dense Search ───────────────────────────

_docs_emb_cache_state = {}  # in-memory: {"key": str, "units_emb": [...]}


def _docs_cache_key(units):
    """Stable cache key based on doc filenames (sorted join → simple hash)."""
    filenames = sorted(u.split("\n", 1)[0] for u in units)
    key_str = "|".join(filenames)
    # stdlib-only fingerprint: sum of char ords mod 10^10
    return str(sum(ord(c) * (i + 1) for i, c in enumerate(key_str)) % (10 ** 10))


def embed_docs_units(units, cache_path):
    """Pre-embed docs corpus. Returns list of dicts:
    {"hash": filename, "text": unit_string, "emb": list_or_[]}.

    Caches to cache_path; invalidates when doc set changes.
    Fail-safe: items without embedding skip dense but still contribute via BM25.
    """
    key = _docs_cache_key(units)

    if _docs_emb_cache_state.get("key") == key:
        return _docs_emb_cache_state["units_emb"]

    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("key") == key:
                _docs_emb_cache_state.update(cached)
                return cached["units_emb"]
        except Exception:
            pass

    # Embed each unit (filename + first 400 chars as subject)
    units_emb = []
    for u in units:
        filename = u.split("\n", 1)[0]
        preview = u[:400]
        emb = _vec_embed(preview)
        units_emb.append({"hash": filename, "text": u, "emb": emb or []})

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"key": key, "units_emb": units_emb}))
    except Exception:
        pass

    _docs_emb_cache_state.update({"key": key, "units_emb": units_emb})
    return units_emb


def dense_rank_docs(units_emb, query, top_k=10):
    """Dense first-stage retrieval for docs corpus.

    units_emb: list of {"hash": filename, "text": unit_str, "emb": list}
    Returns top_k dicts ranked by cosine similarity, or [] if vec-daemon down.
    """
    q_emb = _vec_embed(query)
    if not q_emb:
        return []
    scored = []
    for item in units_emb:
        emb = item.get("emb")
        if not emb:
            continue
        cos = _cosine(q_emb, emb)
        if cos > 0.0:
            scored.append((cos, item))
    if not scored:
        return []
    scored.sort(key=lambda x: -x[0])
    _last_retrieval_scores["dense_top"] = float(scored[0][0])
    return [item for _, item in scored[:top_k]]


def hybrid_search_docs(project_dir, query, top_k=5):
    """Hybrid BM25+dense RRF search over docs/research/*.md corpus.

    Same pipeline as hybrid_rank_decisions() for G1:
      1. BM25 top-(top_k*2) candidates (threshold filtered)
      2. Dense top-(top_k*2) via pre-embedded corpus (vec-daemon cosine)
      3. RRF merge (k=60)
      4. Semantic rerank (BGE/vec-daemon) on merged pool

    Fail-safe: dense unavailable → BM25+semantic rerank (existing behavior).
    Returns list of unit strings — same format as bm25_search_docs().
    """
    bm25, units = build_docs_bm25(project_dir)
    if not bm25 or not units or not query.strip():
        return []

    query_tokens = tokenize(query, drop_stopwords=True)
    query_tokens = _expand_ko_en_docs(query_tokens)  # Korean→English expansion (iter 44)
    if not query_tokens:
        return []

    # Step 1: BM25 candidates
    scores = bm25.get_scores(query_tokens)
    top_score = float(max(scores)) if len(scores) else 0.0
    _last_retrieval_scores["bm25_top"] = top_score
    if top_score < 1.0:
        return []
    floor = max(1.0, top_score * 0.35)
    ranked = sorted(range(len(units)), key=lambda i: scores[i], reverse=True)
    bm25_filtered = [units[i] for i in ranked[:top_k * 2] if scores[i] >= floor]
    if not bm25_filtered:
        return []

    bm25_dicts = [{"hash": u.split("\n", 1)[0], "text": u} for u in bm25_filtered]

    # Step 2: Dense candidates (pre-embedded corpus, 1 vec-daemon call for query)
    cache_path = Path(project_dir) / ".omc" / "docs_corpus_emb.json"
    units_emb = embed_docs_units(units, cache_path)
    dense_dicts = dense_rank_docs(units_emb, query, top_k=top_k * 2)

    if not dense_dicts:
        # Fallback: BM25 + semantic rerank
        if len(bm25_filtered) > top_k:
            cand_dicts = [{"subject": u.split("\n", 1)[0], "text": u[:400]}
                          for u in bm25_filtered]
            reranked = semantic_rerank_filter(cand_dicts, query, top_k=top_k)
            subj_map = {u.split("\n", 1)[0]: u for u in bm25_filtered}
            return [subj_map[d["subject"]] for d in reranked if d["subject"] in subj_map]
        return bm25_filtered[:top_k]

    # Step 3: RRF merge
    merged = rrf_merge(bm25_dicts, dense_dicts, k_rrf=60)

    # Step 4: Semantic rerank on merged pool
    if len(merged) >= top_k + 2:
        reranked = semantic_rerank_filter(merged, query, top_k=top_k)
        return [item.get("text", "") for item in reranked if item.get("text")]

    return [item.get("text", "") for item in merged[:top_k] if item.get("text")]


# ── G2: Code File Discovery ──────────────────────────────────────

_STOP_WORDS = {
    "the","a","an","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","can",
    "to","of","in","for","on","with","at","by","from","as","into",
    "it","this","that","i","you","he","she","we","they","me",
    "and","or","but","not","no","if","then","else","when","where","how","what",
    "해줘","해","바람","좀","것","수","있","없","하다","되다","이","그","저","뭐","어떻게",
    "기능","작업","관련","파일","코드","문서","수정","추가","변경","확인","돌려봐",
    "올려","실행","해봐","분석","개선","확인해",
}
_KO_EN = {
    "검색": "search,retrieve,find", "엔진": "engine,retriever",
    "벤치마크": "benchmark,eval", "평가": "eval,evaluate",
    "트리거": "trigger", "분류": "classify,classifier",
    "밀도": "dense,density", "테스트": "test",
    "결과": "result", "스코어": "score",
    "그래프": "graph", "다운스트림": "downstream",
    "외부": "external,reeval", "정확도": "accuracy,precision",
    "이메일": "email,mail", "발송": "send,outreach",
    "대시보드": "dashboard,admin", "구독": "subscription,subscribe",
    "인증": "auth,authenticate", "로그인": "login,signin",
    "사용자": "user,member", "데이터베이스": "database,schema",
    "함수": "function,handler", "컴포넌트": "component",
    "페이지": "page,route", "설정": "config,settings",
    "환경": "env,environment", "서버": "server,backend",
    "실험": "experiment,trial", "배포": "deploy,deployment",
    "오류": "error,exception", "버그": "bug,error",
    "성능": "performance,latency", "최적화": "optimize,cache",
    "알림": "notification,alert", "권한": "permission,auth",
    "훅": "hook", "메모리": "memory", "인덱스": "index",
}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".sh", ".bash", ".yaml", ".yml", ".toml", ".sql", ".css", ".html",
    ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt",
}
_SKIP_PREFIXES = (".omc/", "docs/", "benchmarks/results/", "tests/fixtures/")


def extract_keywords(prompt):
    """Extract meaningful keywords from prompt; expand Korean→English."""
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}|[가-힣]{2,}', prompt)
    keywords = []
    for w in words:
        if w.lower() in _STOP_WORDS or len(w) < 2:
            continue
        if re.match(r'[가-힣]', w) and w in _KO_EN:
            keywords.extend(_KO_EN[w].split(","))
        else:
            keywords.append(w)
    return keywords[:8]


def find_db(project_dir):
    """Locate codebase-memory-mcp SQLite DB for this project."""
    cache_dir = os.path.expanduser("~/.cache/codebase-memory-mcp")
    if not os.path.isdir(cache_dir):
        return None
    slug = project_dir.replace("/", "-").lstrip("-")
    db_path = os.path.join(cache_dir, f"{slug}.db")
    if os.path.exists(db_path):
        return db_path
    for f in os.listdir(cache_dir):
        if f.endswith(".db") and os.path.basename(project_dir).lower() in f.lower():
            return os.path.join(cache_dir, f)
    return None


_REINDEX_LOCK = os.path.expanduser("~/.cache/codebase-memory-mcp/.reindex_in_progress")
_STALE_THRESHOLD_HOURS = 24

# ── Citation Probe (iter 40) ──────────────────────────────────────────────────
# Logs retrieved nodes per turn to .omc/retrieval_log.jsonl.
# A separate analysis script (benchmarks/eval/citation_probe.py) cross-references
# these logs with vault.db chat history to compute actual citation rate per node type.
# Goal: measure what fraction of retrieved G1/G2 nodes Claude actually cites in responses.

def log_retrieved_nodes(project_dir, session_id, prompt, block, items):
    """
    Append a retrieval event to .omc/retrieval_log.jsonl.

    Args:
        project_dir: project root path
        session_id: Claude session ID (from input_data)
        prompt: user prompt (first 120 chars stored)
        block: "g1_decisions" | "g2_docs" | "g2_prefetch" | "g2_hooks"
        items: list of dicts, each with at minimum {"id": str, "text": str}
               g1: {"id": hash, "text": subject, "date": date}
               g2_docs: {"id": filename, "text": unit_preview}
               g2_prefetch: {"id": fpath, "text": f"{label}:{name}"}
    """
    if not items:
        return
    try:
        import time as _t
        log_path = os.path.join(project_dir, ".omc", "retrieval_log.jsonl")
        entry = {
            "ts": _t.time(),
            "session_id": session_id,
            "prompt_prefix": prompt[:120],
            "block": block,
            "items": items[:10],  # cap at 10 per block
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # citation probe is non-critical — never break the main hook


def check_and_trigger_reindex(project_dir, db_path):
    """
    Check if codebase-memory-mcp DB is stale (>24h). If so, spawn an incremental
    reindex in the background (non-blocking). Returns a warning string if stale,
    or None if fresh.

    Uses a lock file to prevent multiple concurrent reindex launches.
    Tool: codebase-memory-mcp cli index_repository '{"repo_path":"...", "mode":"fast"}'
    """
    try:
        import time as _t_mod
        age_hours = (_t_mod.time() - os.path.getmtime(db_path)) / 3600
    except OSError:
        return None

    if age_hours < _STALE_THRESHOLD_HOURS:
        return None  # fresh — no action needed

    age_str = f"{age_hours:.0f}h" if age_hours < 48 else f"{age_hours/24:.1f}d"

    # Check if reindex already running (lock file < 10 min old)
    if os.path.exists(_REINDEX_LOCK):
        try:
            import time as _t_mod
            lock_age = (_t_mod.time() - os.path.getmtime(_REINDEX_LOCK)) / 60
            if lock_age < 10:
                return f"⚠ G2-CODE DB stale ({age_str}) — reindex already running"
        except OSError:
            pass

    # Spawn background reindex
    try:
        import json as _json
        args = _json.dumps({"repo_path": project_dir, "mode": "fast"})
        cmd = ["codebase-memory-mcp", "cli", "index_repository", args]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach from hook process group
        )
        # Touch lock file
        open(_REINDEX_LOCK, "w").close()
        return f"⚠ G2-CODE DB stale ({age_str}) — auto-reindex triggered (fast mode, background)"
    except Exception:
        return f"⚠ G2-CODE DB stale ({age_str}) — run: codebase-memory-mcp cli index_repository to reindex"


def search_graph_for_prompt(db_path, keywords, limit=5):
    """Query codebase graph nodes matching keywords."""
    if not keywords:
        return []
    try:
        import sqlite3
        db = sqlite3.connect(db_path)
        results, seen = [], set()
        for kw in keywords:
            rows = db.execute(
                "SELECT DISTINCT label, name, file_path FROM nodes "
                "WHERE name LIKE ? AND label IN ('Function','Method','Class') "
                "ORDER BY length(name) ASC LIMIT ?",
                (f"%{kw}%", 3),
            ).fetchall()
            for r in rows:
                key = (r[1], r[2])
                if key not in seen:
                    seen.add(key)
                    results.append(r)
            if len(results) < limit:
                frows = db.execute(
                    "SELECT DISTINCT label, name, file_path FROM nodes "
                    "WHERE file_path LIKE ? AND label IN ('Module','File') "
                    "ORDER BY length(file_path) ASC LIMIT ?",
                    (f"%{kw}%", 2),
                ).fetchall()
                for r in frows:
                    key = (r[1], r[2])
                    if key not in seen:
                        seen.add(key)
                        results.append(r)
        db.close()
        return results[:limit]
    except Exception:
        return []


def search_files_by_grep(project_dir, keywords, limit=5):
    """Fallback: git grep -c to rank files by keyword match count."""
    long_kws = [k for k in keywords if len(k) >= 4 and not re.match(r'[가-힣]', k)]
    if not long_kws:
        return []
    try:
        pattern = "|".join(re.escape(k) for k in long_kws[:4])
        r = subprocess.run(
            ["git", "grep", "-c", "-E", "-i", "--", pattern],
            cwd=project_dir, capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return []
        scored = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                fpath, count = line.rsplit(":", 1)
                scored.append((int(count), fpath.strip()))
            except ValueError:
                continue
        scored.sort(key=lambda x: -x[0])
        files = [f for _, f in scored]
        code = [
            f for f in files
            if any(f.endswith(ext) for ext in _CODE_EXT)
            and not any(f.startswith(p) for p in _SKIP_PREFIXES)
        ]
        return code[:limit]
    except Exception:
        return []


# ── G2: Hooks File Discovery ─────────────────────────────────────

_HOOKS_DIR = Path.home() / ".claude" / "hooks"
_HOOKS_TRIGGER_KWS = frozenset({
    # English
    "hook", "hooks", "bm25-memory", "bm25_memory", "git-memory", "git_memory",
    "auto-index", "auto_index", "g2-augment", "g2_augment",
    "userPromptSubmit", "sessionstart", "posttooluse",
    # Korean
    "훅", "후크",
})


def _build_hook_doc(py_path: Path) -> str:
    """Extract file name + docstring + function/class signatures from a hook file."""
    try:
        src = py_path.read_text(errors="replace")
    except Exception:
        return ""
    lines = src.split("\n")
    header_lines = []
    # Collect: module docstring (first triple-quoted block) + def/class lines
    in_docstring = False
    docstring_done = False
    for line in lines[:80]:
        stripped = line.strip()
        if not docstring_done:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                header_lines.append(stripped[:200])
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    in_docstring = False
                    docstring_done = True
                continue
            if in_docstring:
                header_lines.append(stripped[:200])
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                    docstring_done = True
                continue
            else:
                docstring_done = True
        if stripped.startswith("def ") or stripped.startswith("class "):
            header_lines.append(stripped[:120])
    return f"{py_path.name}\n" + "\n".join(header_lines)


def search_hooks_files(query: str, limit: int = 3):
    """BM25-search ~/.claude/hooks/*.py for hook function/filename matches."""
    if not _HOOKS_DIR.exists() or not HAS_BM25:
        return []
    py_files = sorted(_HOOKS_DIR.glob("*.py"))
    if not py_files:
        return []
    docs = [(p, _build_hook_doc(p)) for p in py_files]
    docs = [(p, d) for p, d in docs if d]
    if not docs:
        return []
    tokenized = [tokenize(d) for _, d in docs]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    return [(docs[i][0], scores[i]) for i in ranked[:limit] if scores[i] > 0]


def _has_hooks_keywords(prompt: str) -> bool:
    """Return True if prompt mentions hook-related terms."""
    low = prompt.lower()
    return any(kw in low for kw in _HOOKS_TRIGGER_KWS)


# ── Rich Mode: World Model ────────────────────────────────────────

def get_world_model(project_dir):
    """Load dead-ends and facts from .omc/world-model.json (--rich mode)."""
    wm_path = Path(project_dir) / ".omc" / "world-model.json"
    if not wm_path.exists():
        return [], []
    try:
        wm = json.loads(wm_path.read_text())
    except Exception:
        return [], []
    raw_de = wm.get("dead_ends", [])
    if isinstance(raw_de, dict):
        raw_de = []
    dead_ends = [
        f"  x {de.get('goal','')[:60]} -- {de.get('reason','')[:80]}"
        for de in raw_de[-5:]
    ]
    facts = []
    for fact in wm.get("known_facts", []):
        if isinstance(fact, dict):
            facts.append(f"  * {fact['fact'][:80]}")
        elif isinstance(fact, str) and not any(
            fact.startswith(p) for p in ("paper:", "README:", "uncertain:")
        ):
            facts.append(f"  * {fact[:80]}")
    return dead_ends, facts[-8:]


# ── Session Decisions ─────────────────────────────────────────────

def get_session_decisions(project_dir):
    """Read .omc/session-decisions.md for uncommitted decisions."""
    p = Path(project_dir) / ".omc" / "session-decisions.md"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().split("\n")
        return [l.strip() for l in lines if l.strip().startswith(">")][-5:]
    except Exception:
        return []


# ── Pending Decisions (from previous session Stop hook) ──────────

def consume_pending_decisions(project_dir: str):
    """
    이전 세션 stop-decision-capture.py가 남긴 .pending-decisions.json 읽고 삭제.
    Returns list of formatted strings for additionalContext injection, or [].
    """
    slug = project_dir.replace("/", "-")
    pending_path = Path.home() / ".claude" / "projects" / slug / "memory" / ".pending-decisions.json"
    if not pending_path.exists():
        return []

    try:
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        captured_at = payload.get("captured_at", "")[:16]  # "2026-04-14T12:34"
    except Exception:
        try:
            pending_path.unlink(missing_ok=True)
        except Exception:
            pass
        return []

    # 읽은 즉시 삭제 (1회성 전달)
    try:
        pending_path.unlink(missing_ok=True)
    except Exception:
        pass

    if not decisions:
        return []

    lines = [f"[PENDING MEMORY] 이전 세션({captured_at}) 결정 후보 — MEMORY.md 업데이트 필요 여부 판단:"]
    for d in decisions:
        tag = d.get("tag", "")
        ctx = d.get("context", "")
        lines.append(f"  [{tag}] {ctx}")
    lines.append("→ 위 항목 중 MEMORY.md에 없는 중요한 결정이 있으면 즉시 Edit tool로 기록하세요.")
    return lines


# ── Main ──────────────────────────────────────────────────────────

def _log_event(event_type, payload):
    """Opt-in telemetry wrapper — silent no-op if gate off. Never breaks hook path."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import log_event
        log_event(event_type, payload)
    except Exception:
        pass


def main():
    import time as _time
    _t_start = _time.perf_counter()
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    prompt = input_data.get("prompt", "")
    _session_id = input_data.get("session_id", "")

    # A/B scaffold: control arm skips injection entirely (CTX_AB_DISABLE=1).
    # Dashboard uses the logged ab_skipped events to count control-arm sessions.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import ab_disabled, log_event
        if ab_disabled():
            log_event("ab_skipped", {"hook": "bm25-memory", "reason": "CTX_AB_DISABLE"})
            sys.exit(0)
    except Exception:
        pass
    lines = []
    _blocks_fired = []  # for final hook_invoked telemetry summary
    _retrieval_meta = {"ts": _time.time(), "blocks": {}}  # retrieval_event telemetry

    # 0a. Pending decisions from previous session (Stop hook → queue file)
    pending = consume_pending_decisions(project_dir)
    if pending:
        lines.extend(pending)

    # 0b. Session decisions (uncommitted notes)
    session_notes = get_session_decisions(project_dir)
    if session_notes:
        lines.append("[SESSION NOTES (미커밋 판단)]")
        lines.extend(session_notes)

    # 1. G1: Hybrid BM25+dense RRF over decision corpus (2026-04-26)
    # Uses hybrid_rank_decisions() when vec-daemon is up (BM25+dense→RRF→rerank).
    # Falls back to bm25_rank_decisions() if dense unavailable — explicit coverage.
    # Eval: BM25=0.966, Hybrid=0.983 (+1.7pp) on 59-query G1 bench (172 commits).
    _t_g1 = _time.perf_counter()
    corpus = get_decision_corpus(project_dir)
    g1_header = ""
    if corpus:
        # Auto-tune: adjust top_k based on flywheel recommendations
        _g1_top_k = 7
        if _AUTO_TUNE:
            _qtype_now = _classify_query_type(prompt)
            _temporal_gap = _AUTO_TUNE.get("temporal_utility_gap", 0)
            # If TEMPORAL utility is 10pp below KEYWORD, reduce top_k to inject only best matches
            if _qtype_now == "TEMPORAL" and _temporal_gap > 0.10:
                _g1_top_k = 5  # more selective for low-utility temporal queries
            # Project-type profile adjustments (Stage 3 local loop)
            _proj_type = _AUTO_TUNE.get("project_type_hint", "")
            _proj_conf = _AUTO_TUNE.get("project_type_confidence", "LOW")
            if _proj_conf in ("HIGH", "MEDIUM"):
                if _proj_type == "python_ml":
                    # ML projects: training/model decisions span longer history
                    _g1_top_k = min(_g1_top_k + 1, 10)
                elif _proj_type == "nextjs_react":
                    # React: component decisions are keyword-specific, fewer suffice
                    _g1_top_k = max(_g1_top_k - 1, 4)
        _last_retrieval_scores.clear()
        relevant = hybrid_rank_decisions(corpus, prompt, top_k=_g1_top_k)
        if relevant:
            # Build forced display header (mechanically injected, not advisory)
            first_subj = relevant[0]["subject"][:70]
            rest_count = len(relevant) - 1
            g1_header = f'> **G1** (time memory): "{first_subj}" and {rest_count} more'

            lines.append(
                f"[RECENT DECISIONS] (BM25: top {len(relevant)} of {len(corpus)})"
            )
            for c in relevant:
                date = c.get("date", "")
                subj = c["subject"]
                prefix = f"  > [{date}] " if date else "  > "
                lines.append(f"{prefix}{subj}")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g1_decisions",
                "count": len(relevant),
                "duration_ms": int((_time.perf_counter() - _t_g1) * 1000),
            })
            _blocks_fired.append("g1")
            _g1_meta: dict = {
                "candidates": len(corpus),
                "returned": len(relevant),
                "retrieval_method": "HYBRID" if (_VEC_SOCK.exists() and not _VEC_DISABLED) else "BM25",
                "duration_ms": int((_time.perf_counter() - _t_g1) * 1000),
                "query_type": _classify_query_type(prompt),
            }
            if "bm25_top" in _last_retrieval_scores:
                _g1_meta["top_score_bm25"] = round(_last_retrieval_scores["bm25_top"], 4)
            if "dense_top" in _last_retrieval_scores:
                _g1_meta["top_score_dense"] = round(_last_retrieval_scores["dense_top"], 4)
            _retrieval_meta["blocks"]["g1_decisions"] = _g1_meta
            # Citation probe: log G1 retrieved nodes
            log_retrieved_nodes(project_dir, _session_id, prompt, "g1_decisions", [
                {"id": c.get("hash", c["subject"][:20]), "text": c["subject"], "date": c.get("date", "")}
                for c in relevant
            ])

    # 2. G2: BM25 over project docs
    g2_files = []
    g2_keywords = []
    if prompt:
        _t_g2d = _time.perf_counter()
        # Auto-tune: adjust G2-DOCS top_k based on flywheel recommendations
        _g2d_top_k = 5
        if _AUTO_TUNE:
            _qtype_now2 = _classify_query_type(prompt)
            _g2_temporal_gap = _AUTO_TUNE.get("temporal_utility_gap", 0)
            if _qtype_now2 == "TEMPORAL" and _g2_temporal_gap > 0.10:
                _g2d_top_k = 3  # more selective for low-utility temporal doc queries
            # Project-type profile adjustments (Stage 3 local loop)
            _proj_type2 = _AUTO_TUNE.get("project_type_hint", "")
            _proj_conf2 = _AUTO_TUNE.get("project_type_confidence", "LOW")
            if _proj_conf2 in ("HIGH", "MEDIUM"):
                if _proj_type2 == "nextjs_react":
                    # Next.js: more framework docs per query (more component/API docs)
                    _g2d_top_k = min(_g2d_top_k + 1, 8)
                elif _proj_type2 == "rust_systems":
                    # Rust: docs are precise, fewer higher-quality docs preferred
                    _g2d_top_k = max(_g2d_top_k - 1, 3)
        _last_retrieval_scores.pop("bm25_top", None)
        _last_retrieval_scores.pop("dense_top", None)
        doc_chunks = hybrid_search_docs(project_dir, prompt, top_k=_g2d_top_k)
        if doc_chunks:
            lines.append("[G2-DOCS] (BM25+dense RRF relevant research docs)")
            for chunk in doc_chunks:
                chunk_lines = chunk.strip().split("\n")
                header = chunk_lines[0]  # "filename § section"
                fname = header.split(" §")[0].strip()
                if fname and fname not in g2_files:
                    g2_files.append(fname)
                snippet = ""
                if len(chunk_lines) > 1:
                    # Find first non-empty content line
                    for cl in chunk_lines[1:]:
                        cl = cl.strip()
                        if cl and not cl.startswith("#"):
                            snippet = cl[:120]
                            break
                lines.append(f"  > {header}")
                if snippet:
                    lines.append(f"    {snippet}")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g2_docs",
                "count": len(doc_chunks),
                "duration_ms": int((_time.perf_counter() - _t_g2d) * 1000),
            })
            _blocks_fired.append("g2_docs")
            _g2d_corpus_size = len(build_docs_bm25(project_dir)[1]) if doc_chunks else None
            _g2d_meta: dict = {
                "candidates": _g2d_corpus_size,
                "returned": len(doc_chunks),
                "retrieval_method": "HYBRID" if (_VEC_SOCK.exists() and not _VEC_DISABLED) else "BM25",
                "duration_ms": int((_time.perf_counter() - _t_g2d) * 1000),
                "query_type": _classify_query_type(prompt),
            }
            if "bm25_top" in _last_retrieval_scores:
                _g2d_meta["top_score_bm25"] = round(_last_retrieval_scores["bm25_top"], 4)
            if "dense_top" in _last_retrieval_scores:
                _g2d_meta["top_score_dense"] = round(_last_retrieval_scores["dense_top"], 4)
            _retrieval_meta["blocks"]["g2_docs"] = _g2d_meta
            # Citation probe: log G2-DOCS retrieved nodes
            log_retrieved_nodes(project_dir, _session_id, prompt, "g2_docs", [
                {"id": chunk.strip().split("\n")[0].split(" §")[0].strip(), "text": chunk.strip().split("\n")[0][:80]}
                for chunk in doc_chunks
            ])

    # 3. G2: Code file discovery (graph → grep fallback)
    if prompt:
        keywords = extract_keywords(prompt)
        g2_keywords = keywords[:3]
        if keywords:
            _t_g2p = _time.perf_counter()
            db_path = find_db(project_dir)
            if db_path:
                # Staleness check: auto-reindex if DB > 24h old
                stale_warn = check_and_trigger_reindex(project_dir, db_path)
                if stale_warn:
                    lines.append(stale_warn)
                graph_results = search_graph_for_prompt(db_path, keywords)
                if graph_results:
                    lines.append(f"[G2-PREFETCH] Related code for '{' '.join(keywords[:3])}':")
                    seen_files = set()
                    for label, name, fpath in graph_results:
                        lines.append(f"  {label}: {name} @ {fpath}")
                        seen_files.add(fpath)
                    if seen_files:
                        lines.append(f"  Start with: {', '.join(sorted(seen_files)[:3])}")
                    _log_event("block_fired", {
                        "hook": "bm25-memory", "block": "g2_prefetch",
                        "count": len(graph_results),
                        "duration_ms": int((_time.perf_counter() - _t_g2p) * 1000),
                    })
                    _blocks_fired.append("g2_prefetch")
            else:
                # Fallback: git grep
                files = search_files_by_grep(project_dir, keywords)
                if files:
                    lines.append(f"[G2-GREP] Files matching '{' '.join(keywords[:3])}' (grep):")
                    for f in files:
                        lines.append(f"  {f}")
                    lines.append(f"  Start with: {', '.join(files[:3])}")
                    _log_event("block_fired", {
                        "hook": "bm25-memory", "block": "g2_grep",
                        "count": len(files),
                        "duration_ms": int((_time.perf_counter() - _t_g2p) * 1000),
                    })
                    _blocks_fired.append("g2_grep")

    # 3b. G2: Hooks file discovery (when hook-related terms in prompt)
    if prompt and _has_hooks_keywords(prompt):
        _t_g2h = _time.perf_counter()
        hook_results = search_hooks_files(prompt)
        if hook_results:
            lines.append(f"[G2-HOOKS] Hook files matching '{prompt[:40]}':")
            for hp, score in hook_results:
                lines.append(f"  {hp}  (score={score:.1f})")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g2_hooks",
                "count": len(hook_results),
                "duration_ms": int((_time.perf_counter() - _t_g2h) * 1000),
            })
            _blocks_fired.append("g2_hooks")

    # 4. World model (--rich)
    if RICH:
        dead_ends, facts = get_world_model(project_dir)
        if dead_ends:
            lines.append("[DEAD-ENDS -- do not retry]")
            lines.extend(dead_ends)
        if facts:
            lines.append("[KNOWN FACTS]")
            lines.extend(facts)

    if lines:
        # Prepend forced display header (mechanically enforced, replaces CLAUDE.md advisory)
        header_lines = []
        if g1_header:
            header_lines.append(g1_header)
        if g2_files or g2_keywords:
            files_str = ", ".join(f"`{f}`" for f in g2_files[:3]) if g2_files else "(docs BM25)"
            kw_str = " ".join(g2_keywords[:3]) if g2_keywords else ""
            via_str = f' — found via "{kw_str}"' if kw_str else ""
            header_lines.append(f"> **G2** (space search): {files_str}{via_str}")
        # Daemon degradation warnings — shown only when socket is absent
        _daemon_warns = []
        if not _VEC_DISABLED and not _VEC_SOCK.exists():
            _daemon_warns.append("vec-daemon down — BM25-only mode (semantic rerank disabled)")
        if _USE_CROSS_ENCODER and not _BGE_SOCK.exists():
            _daemon_warns.append("bge-daemon down — cross-encoder rerank disabled")
        if _daemon_warns:
            header_lines.append("> **⚠ Semantic layer**: " + " | ".join(_daemon_warns))
        # Auto-tune active badge — shows flywheel is running
        if _AUTO_TUNE_ACTIVE:
            n_rec = _AUTO_TUNE.get("based_on_n", "?")
            prefer_hybrid = _AUTO_TUNE.get("prefer_hybrid_G1", False)
            temporal_gap = _AUTO_TUNE.get("temporal_utility_gap")
            proj_hint = _AUTO_TUNE.get("project_type_hint")
            proj_conf = _AUTO_TUNE.get("project_type_confidence", "LOW")
            parts = [f"n={n_rec}"]
            if prefer_hybrid:
                parts.append("hybrid✓")
            if temporal_gap and temporal_gap > 0.05:
                parts.append(f"temporal-gap={temporal_gap*100:.0f}pp")
            if proj_hint and proj_hint != "multi_lang" and proj_conf in ("HIGH", "MEDIUM"):
                parts.append(proj_hint)
            header_lines.append(f"> **CTX auto-tune** [{', '.join(parts)}] — run `ctx-telemetry tune` to refresh")
        if header_lines:
            lines = header_lines + [""] + lines

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n".join(lines),
            }
        }
        json.dump(output, sys.stdout)
        sys.stdout.flush()
        if header_lines:
            print("\n".join(header_lines), file=sys.stderr)
            sys.stderr.flush()

    # Final summary event: one record per hook invocation (outside `if lines:`)
    _log_event("hook_invoked", {
        "hook": "bm25-memory",
        "duration_ms": int((_time.perf_counter() - _t_start) * 1000),
        "prompt_len": len(prompt) if prompt else 0,
    })

    # ── P1: record what we injected for utility-rate measurement ─────
    # Stop hook reads this + the latest assistant turn + substring-matches
    # each item's distinctive tokens. Not stored when dashboard-internal.
    if os.environ.get("CTX_DASHBOARD_INTERNAL") != "1":
        try:
            # Preview = first 120 chars, newlines stripped (same privacy surface
            # as vault.db which already stores full prompts; this just makes the
            # dashboard see new prompts *before* vault.db incremental fires on Stop).
            preview = (prompt or "")[:120].replace("\n", " ").replace("\r", " ")
            # Full prompt stored too so the dashboard's node-details pane can
            # show the whole message before vault.db catches up.
            prompt_full_str = (prompt or "").replace("\r", "")
            # Derive the project basename from CLAUDE_PROJECT_DIR (fallback to cwd)
            try:
                _proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
                _project_name = os.path.basename(_proj.rstrip("/")) if _proj else None
            except Exception:
                _project_name = None
            injection = {
                "ts": _time.time(),
                "prompt_len": len(prompt) if prompt else 0,
                "prompt_preview": preview,
                "prompt_full": prompt_full_str,
                "project": _project_name,
                "items": [],
            }
            # Collect distinctive substrings from emitted blocks.
            # Each item is (block, signature) — signature is a 4-20 char
            # distinctive substring the assistant's response can echo.
            # Meta/filler words from commit subjects that never represent a topic.
            # Drops CTX's internal taxonomy (live-infinite, iter, goal_vN) + conventional
            # commit prefixes + common English verbs — anything that would generate
            # false-positive matches against unrelated responses.
            _META_WORDS = frozenset([
                "live-infinite", "live-inf", "omc-live", "iter", "live",
                "goal_v1", "goal_v2", "goal_v3", "goal",
                "feat", "fix", "refactor", "perf", "docs", "test", "chore",
                "success", "section", "update", "add", "remove", "change",
                "fixed", "added", "removed", "completed",
            ])
            # Header-row detector for "> **G1/G2**" and similar markdown headers
            _is_header_line = lambda st: st.startswith("> **") and "** (" in st

            def _extract_content_tokens(subject: str, n: int = 5) -> list:
                """Pick up to N distinctive content tokens from a commit subject.
                Filters meta words, pure digits, punctuation-only fragments.
                Prefers longer words (more specific = better substring hit rate)."""
                candidates = []
                for w in subject.split():
                    w_clean = w.strip(".,()[]{}:;!?\"'").lower()
                    if len(w_clean) < 4:
                        continue
                    if w_clean in _META_WORDS:
                        continue
                    if w_clean.replace("/", "").replace(".", "").replace("-", "").isdigit():
                        continue   # 20260402, 58/∞, etc.
                    # Keep case of original for better citation-style match
                    candidates.append(w.strip(".,()[]{}:;!?\"'"))
                # Dedup preserving order, sort by length desc for specificity
                seen = set()
                uniq = [t for t in candidates if not (t.lower() in seen or seen.add(t.lower()))]
                uniq.sort(key=lambda t: -len(t))
                return uniq[:n]

            for line in lines:
                s = line.strip()
                # Skip markdown headers like "> **G1** (time memory): ..." — they are
                # not items, they're section labels that would leak into signatures.
                if _is_header_line(s):
                    continue
                # G1 decisions: "> [YYYY-MM-DD] subject" — capture date for age-based wow trigger
                if s.startswith("> [") and "]" in s:
                    close_idx = s.index("]")
                    date_str = s[3:close_idx]
                    subj = s[close_idx + 1:].strip()
                    tokens = _extract_content_tokens(subj, n=5)
                    if tokens:
                        item = {
                            "block": "g1",
                            "tokens": tokens,
                            "subject": subj[:200],  # preserved for semantic scoring
                        }
                        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                            item["date"] = date_str
                        injection["items"].append(item)
                # G2-DOCS entries: "  > filename.md" → filename AS signature AND
                # also extract date-token + topic words from filename for more hit
                # surface (e.g. "20260411-g1-generalization-validation.md" also
                # matches on "generalization" / "validation").
                elif s.startswith("> ") and (".md" in s or s.endswith(".py")):
                    fname = s.lstrip("> ").strip().split(" §")[0].split()[0]
                    if fname:
                        # filename + its stem words as tokens
                        stem = fname.rsplit(".", 1)[0]
                        parts = [p for p in stem.replace("-", " ").replace("_", " ").split()
                                 if len(p) >= 4 and not p.isdigit()]
                        tokens = [fname] + parts[:4]
                        # Subject for semantic: the filename's natural-language form
                        subject = " ".join(parts) if parts else fname
                        injection["items"].append({
                            "block": "g2_docs", "tokens": tokens, "subject": subject[:200]
                        })
                # G2-PREFETCH: symbol names (function/class) + their path
                elif ": " in s and "@" in s and any(k in s for k in ("Function:", "Class:", "Method:", "Module:", "File:")):
                    try:
                        name = s.split(":", 1)[1].split("@")[0].strip()
                        path = s.split("@", 1)[1].strip() if "@" in s else ""
                        path_base = path.rsplit("/", 1)[-1] if path else ""
                        tokens = [t for t in [name, path_base] if t and len(t) >= 4]
                        if tokens:
                            injection["items"].append({
                                "block": "g2_prefetch",
                                "tokens": tokens,
                                "subject": f"{name} in {path}"[:200],
                            })
                    except Exception:
                        pass
            Path(os.path.expanduser("~/.claude/last-injection.json")).write_text(
                json.dumps(injection)
            )
            # Write retrieval metadata for utility-rate.py → retrieval_event schema
            _retrieval_meta["vec_daemon_up"] = _VEC_SOCK.exists() and not _VEC_DISABLED
            _retrieval_meta["bge_daemon_up"] = _BGE_SOCK.exists() and bool(
                os.environ.get("CTX_CROSS_ENCODER", "1") != "0"
            )
            _retrieval_meta["query_char_count"] = len(prompt) if prompt else 0
            _retrieval_meta["session_id"] = _session_id or ""
            Path(os.path.expanduser("~/.claude/last-retrieval-meta.json")).write_text(
                json.dumps(_retrieval_meta)
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
