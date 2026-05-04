"""
corpus.py — G1 Decision Corpus build/cache for bm25-memory.

Provides:
  get_git_head(project_dir) -> str|None
  build_decision_corpus(project_dir, n=500) -> list[dict]
  embed_corpus_items(corpus) -> int         (vec-daemon, modifies in-place)
  get_decision_corpus(project_dir) -> list[dict]
  _classify_query_type(prompt) -> str       (TEMPORAL/KEYWORD/SEMANTIC)
"""
import json
import re
import subprocess
from pathlib import Path

from .rerank import vec_embed as _vec_embed

# ── Decision commit detection ────────────────────────────────────────────────

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
    r"\s[-—]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
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


# ── Query-type classification (for retrieval_event schema v1.1) ─────────────

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


# ── Git helpers ──────────────────────────────────────────────────────────────

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
