"""
docs_search.py — G2-DOCS BM25+hybrid search for bm25-memory.

Provides:
  _extra_doc_files(project_dir) -> list[str]
  chunk_document(filename, content) -> list[str]
  build_docs_bm25(project_dir) -> (BM25Okapi|None, list[str])
  bm25_search_docs(project_dir, query, top_k=5) -> list[str]
  embed_docs_units(units, cache_path) -> list[dict]
  dense_rank_docs(units_emb, query, top_k=10) -> list[dict]
  hybrid_search_docs(project_dir, query, top_k=5) -> list[str]
"""
import json
import os
import re
from pathlib import Path

try:
    from rank_bm25 import BM25Okapi
    _HAS_BM25 = True
except ImportError:
    BM25Okapi = None  # type: ignore
    _HAS_BM25 = False

from .tokenizer import tokenize
from .rerank import vec_embed as _vec_embed, cosine as _cosine, semantic_rerank_filter
from .ranker import rrf_merge, last_retrieval_scores as _last_retrieval_scores

# ── Korean→English expansion for G2-DOCS BM25 path (iter 44) ────────────────

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


# ── Doc corpus helpers ───────────────────────────────────────────────────────

def _extra_doc_files(project_dir):
    """Return extra files to include in the docs index (project-agnostic)."""
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

    if not all_units or not _HAS_BM25:
        return None, []
    tokenized = [tokenize(u) for u in all_units]
    return BM25Okapi(tokenized), all_units


def bm25_search_docs(project_dir, query, top_k=5):
    """Return top-k docs most relevant to query (full-doc BM25, no chunking)."""
    if not query.strip():
        return []
    bm25, units = build_docs_bm25(project_dir)
    if not bm25:
        return []
    query_tokens = tokenize(query, drop_stopwords=True)
    query_tokens = _expand_ko_en_docs(query_tokens)
    if not query_tokens:
        return []
    scores = bm25.get_scores(query_tokens)
    ranked = sorted(range(len(units)), key=lambda i: scores[i], reverse=True)
    top_score = float(max(scores)) if len(scores) else 0.0
    floor = max(1.0, top_score * 0.35)
    bm_filtered = [units[i] for i in ranked[:top_k * 2] if scores[i] >= floor]
    if len(bm_filtered) > top_k:
        cand_dicts = [{"subject": u.split("\n", 1)[0], "text": u[:400]} for u in bm_filtered]
        reranked_dicts = semantic_rerank_filter(cand_dicts, query, top_k=top_k)
        subject_to_unit = {u.split("\n", 1)[0]: u for u in bm_filtered}
        return [subject_to_unit[d["subject"]] for d in reranked_dicts if d["subject"] in subject_to_unit]
    return bm_filtered[:top_k]


# ── Hybrid BM25+Dense Search ─────────────────────────────────────────────────

_docs_emb_cache_state: dict = {}  # in-memory: {"key": str, "units_emb": [...]}


def _docs_cache_key(units):
    """Stable cache key based on doc filenames (sorted join → simple hash)."""
    filenames = sorted(u.split("\n", 1)[0] for u in units)
    key_str = "|".join(filenames)
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

    Pipeline (2026-04-26):
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
    query_tokens = _expand_ko_en_docs(query_tokens)
    if not query_tokens:
        return []

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

    cache_path = Path(project_dir) / ".omc" / "docs_corpus_emb.json"
    units_emb = embed_docs_units(units, cache_path)
    dense_dicts = dense_rank_docs(units_emb, query, top_k=top_k * 2)

    if not dense_dicts:
        if len(bm25_filtered) > top_k:
            cand_dicts = [{"subject": u.split("\n", 1)[0], "text": u[:400]}
                          for u in bm25_filtered]
            reranked = semantic_rerank_filter(cand_dicts, query, top_k=top_k)
            subj_map = {u.split("\n", 1)[0]: u for u in bm25_filtered}
            return [subj_map[d["subject"]] for d in reranked if d["subject"] in subj_map]
        return bm25_filtered[:top_k]

    merged = rrf_merge(bm25_dicts, dense_dicts, k_rrf=60)

    if len(merged) >= top_k + 2:
        reranked = semantic_rerank_filter(merged, query, top_k=top_k)
        return [item.get("text", "") for item in reranked if item.get("text")]

    return [item.get("text", "") for item in merged[:top_k] if item.get("text")]
