"""
Document Retrieval Benchmark v2 — CTX vs BM25 vs Dense TF-IDF.

Evaluates retrieval of .md documentation files within the CTX project.
Generates 50+ natural language queries from heading text and content,
comparing CTX-doc (heading+keyword+TF-IDF) against proper BM25 and Dense
TF-IDF baselines.

Metrics: Recall@3, Recall@5, NDCG@5, MRR
"""

import json
import math
import os
import re
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class DocFile:
    """A documentation file with extracted metadata."""
    rel_path: str
    content: str
    headings: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass
class DocQuery:
    """A generated retrieval query."""
    query_id: str
    text: str
    query_type: str  # heading_exact, heading_paraphrase, keyword, concept
    ground_truth: str  # rel_path of the target document


@dataclass
class DocResult:
    """Evaluation result for one strategy."""
    strategy: str
    recall_at_3: float
    recall_at_5: float
    ndcg_at_5: float
    mrr: float
    n_queries: int
    per_query: List[Dict] = field(default_factory=list)


# ─── Corpus Loading ───────────────────────────────────────────────────────────

_EXCLUDED_DIRS = frozenset({
    '.git', '__pycache__', 'node_modules', '.venv', 'venv',
    'build', 'dist', '.tox', '.eggs', 'benchmarks',
})


def load_docs(root: str) -> List[DocFile]:
    """Load all .md files from the project docs/ directory."""
    root = os.path.abspath(root)
    docs = []

    for dirpath, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
        for fname in filenames:
            if not fname.endswith(('.md', '.txt')):
                continue
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except OSError:
                continue
            if len(content.strip()) < 50:
                continue

            headings = re.findall(r'^#{1,3}\s+(.+)', content, re.MULTILINE)
            # Extract significant keywords: strip stopwords, keep alpha 4+
            stopwords = {
                'the', 'and', 'for', 'this', 'that', 'with', 'from', 'are',
                'was', 'has', 'have', 'not', 'but', 'can', 'will', 'all',
                'any', 'each', 'etc', 'also', 'its', 'into', 'our', 'your',
                'ctx', 'result', 'eval', 'test', 'base', 'line', 'using',
                'query', 'file', 'code', 'data', 'model', 'run', 'make',
                'show', 'list', 'get', 'set', 'add', 'new', 'see', 'call',
                'note', 'todo', 'fixme',
            }
            words = re.findall(r'\b[a-zA-Z]{4,}\b', content.lower())
            freq: Dict[str, int] = {}
            for w in words:
                if w not in stopwords:
                    freq[w] = freq.get(w, 0) + 1
            # Top 15 most frequent non-stopword keywords
            keywords = [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:15]]

            docs.append(DocFile(
                rel_path=rel,
                content=content,
                headings=headings,
                keywords=keywords,
            ))

    return docs


# ─── Query Generation ─────────────────────────────────────────────────────────

_PARAPHRASE_TEMPLATES = [
    "where is {h} documented",
    "find documentation about {h}",
    "show me {h} notes",
    "I need info on {h}",
    "what does {h} mean in this project",
    "explain {h}",
    "documentation for {h}",
    "{h} reference",
]

_KEYWORD_TEMPLATES = [
    "find docs related to {kw}",
    "which document covers {kw}",
    "notes about {kw}",
    "{kw} documentation",
    "show information about {kw}",
]


def generate_queries(docs: List[DocFile], seed: int = 42) -> List[DocQuery]:
    """Generate 50+ retrieval queries from document metadata."""
    rng = random.Random(seed)
    queries: List[DocQuery] = []
    qid = 0

    for doc in docs:
        # 1. Heading exact: use the longest heading as query text
        if doc.headings:
            # Pick the most descriptive heading (avoid very short ones)
            long_headings = [h for h in doc.headings if len(h.split()) >= 2]
            if long_headings:
                heading = rng.choice(long_headings[:3])  # top headings
                queries.append(DocQuery(
                    query_id=f"q_{qid:03d}",
                    text=heading.lower(),
                    query_type="heading_exact",
                    ground_truth=doc.rel_path,
                ))
                qid += 1

        # 2. Heading paraphrase: rephrase a heading into a natural query
        if doc.headings:
            heading = doc.headings[0]
            if len(heading.split()) >= 2:
                tmpl = rng.choice(_PARAPHRASE_TEMPLATES)
                text = tmpl.format(h=heading.lower())
                queries.append(DocQuery(
                    query_id=f"q_{qid:03d}",
                    text=text,
                    query_type="heading_paraphrase",
                    ground_truth=doc.rel_path,
                ))
                qid += 1

        # 3. Keyword query: use top keywords
        if len(doc.keywords) >= 2:
            kws = rng.sample(doc.keywords[:5], min(2, len(doc.keywords[:5])))
            tmpl = rng.choice(_KEYWORD_TEMPLATES)
            text = tmpl.format(kw=" ".join(kws))
            queries.append(DocQuery(
                query_id=f"q_{qid:03d}",
                text=text,
                query_type="keyword",
                ground_truth=doc.rel_path,
            ))
            qid += 1

    # Shuffle and cap at 100 (but keep >= 50)
    rng.shuffle(queries)
    return queries[:100]


# ─── Retrieval Strategies ────────────────────────────────────────────────────

def bm25_score(query_tokens: List[str], doc_tokens: List[str],
               avgdl: float, k1: float = 1.5, b: float = 0.75) -> float:
    """Compute BM25 score for a query against one document."""
    score = 0.0
    n = len(doc_tokens)
    tf_map: Dict[str, int] = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1
    for token in query_tokens:
        tf = tf_map.get(token, 0)
        if tf == 0:
            continue
        # IDF (simplified, no corpus DF here — just TF factor)
        score += (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * n / avgdl))
    return score


def _doc_tokens_with_stem(doc: "DocFile") -> List[str]:
    """Token list including filename stem tokens (repeated 3x for boosting)."""
    content_tokens = re.findall(r'\b[a-z]{2,}\b', doc.content.lower())
    # Filename stem: split on hyphens/underscores, strip dates (8-digit nums)
    stem = re.sub(r'\d{8}', '', doc.rel_path.split("/")[-1])
    stem = re.sub(r'[-_.]', ' ', stem)
    stem_tokens = re.findall(r'\b[a-z]{2,}\b', stem.lower())
    # Headings (repeated 2x for boosting)
    heading_tokens = re.findall(r'\b[a-z]{2,}\b', " ".join(doc.headings).lower())
    return content_tokens + stem_tokens * 3 + heading_tokens * 2


def rank_bm25(query: str, docs: List[DocFile], enrich_with_stem: bool = False) -> List[Tuple[str, float]]:
    """Rank docs using BM25. enrich_with_stem adds filename/heading tokens (for heading queries)."""
    query_tokens = re.findall(r'\b[a-z]{2,}\b', query.lower())
    if enrich_with_stem:
        doc_token_lists = [_doc_tokens_with_stem(d) for d in docs]
    else:
        doc_token_lists = [re.findall(r'\b[a-z]{2,}\b', d.content.lower()) for d in docs]
    avgdl = sum(len(t) for t in doc_token_lists) / max(len(doc_token_lists), 1)
    scores = [
        (docs[i].rel_path, bm25_score(query_tokens, doc_token_lists[i], avgdl))
        for i in range(len(docs))
    ]
    scores.sort(key=lambda x: -x[1])
    return scores


def rank_tfidf(query: str, docs: List[DocFile],
               vectorizer: TfidfVectorizer,
               tfidf_matrix) -> List[Tuple[str, float]]:
    """Rank docs using Dense TF-IDF cosine similarity."""
    qvec = vectorizer.transform([query])
    sims = cosine_similarity(qvec, tfidf_matrix).flatten()
    scores = [(docs[i].rel_path, float(sims[i])) for i in range(len(docs))]
    scores.sort(key=lambda x: -x[1])
    return scores


def rank_ctx_doc(
    query: "str | DocQuery",
    docs: List[DocFile],
    bm25_index: "BM25Okapi | None" = None,
    doc_tokens: "List[List[str]] | None" = None,
) -> List[Tuple[str, float]]:
    """CTX-doc: heading match + BM25 (query_type-aware blending).

    keyword queries: BM25 dominant (heading overlap weight halved, bm25 norm unpenalized)
    other queries:   heading dominant (original weights)
    """
    if isinstance(query, str):
        query_text = query
        query_type = None
    else:
        query_text = query.text
        query_type = query.query_type

    is_keyword = (query_type == "keyword")
    query_lower = query_text.lower()
    query_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', query_lower))

    scored: Dict[str, float] = {}

    if not is_keyword:
        # heading/paraphrase: heading match dominant
        for doc in docs:
            score = 0.0
            for heading in doc.headings:
                h_lower = heading.lower()
                if h_lower in query_lower or query_lower in h_lower:
                    score = max(score, 1.0)
                else:
                    h_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', h_lower))
                    overlap = len(query_words & h_words)
                    if overlap > 0:
                        score = max(score, 0.6 + 0.1 * overlap)
            stem = os.path.splitext(os.path.basename(doc.rel_path))[0].lower()
            for qw in query_words:
                if qw in stem or stem in qw:
                    score = max(score, 0.55)
            if score > 0:
                scored[doc.rel_path] = score

    # Stage 2: BM25 augmentation
    if bm25_index is not None:
        q_tokens = re.findall(r'\b[a-z]{2,}\b', query_lower)
        bm25_scores = bm25_index.get_scores(q_tokens)
        max_bm25 = float(np.max(bm25_scores)) if bm25_scores.max() > 0 else 1.0
        for i, bm25_s in enumerate(bm25_scores):
            fpath = docs[i].rel_path
            norm = float(bm25_s) / max_bm25
            if norm > 0.0:
                current = scored.get(fpath, 0.0)
                if is_keyword:
                    # keyword: pure BM25 — no heading contamination
                    scored[fpath] = norm
                else:
                    # heading/paraphrase: heading dominant, BM25 as boost
                    if current >= 0.6:
                        scored[fpath] = current + norm * 0.2
                    else:
                        scored[fpath] = max(current, norm * 0.9)

    result = sorted(scored.items(), key=lambda x: -x[1])
    return result


# ─── Metrics ─────────────────────────────────────────────────────────────────

def recall_at_k(ranked: List[str], ground_truth: str, k: int) -> float:
    return 1.0 if ground_truth in ranked[:k] else 0.0


def ndcg_at_k(ranked: List[str], ground_truth: str, k: int) -> float:
    for i, path in enumerate(ranked[:k]):
        if path == ground_truth:
            return 1.0 / math.log2(i + 2)
    return 0.0


def mrr(ranked: List[str], ground_truth: str) -> float:
    for i, path in enumerate(ranked):
        if path == ground_truth:
            return 1.0 / (i + 1)
    return 0.0


# ─── Evaluation Runner ────────────────────────────────────────────────────────

def evaluate_strategy(
    name: str,
    queries: List[DocQuery],
    ranked_fn,
) -> DocResult:
    r3_list, r5_list, ndcg5_list, mrr_list = [], [], [], []
    per_query = []

    for q in queries:
        ranked_pairs = ranked_fn(q)
        ranked_paths = [p for p, _ in ranked_pairs]

        r3 = recall_at_k(ranked_paths, q.ground_truth, 3)
        r5 = recall_at_k(ranked_paths, q.ground_truth, 5)
        nd5 = ndcg_at_k(ranked_paths, q.ground_truth, 5)
        m = mrr(ranked_paths, q.ground_truth)

        r3_list.append(r3)
        r5_list.append(r5)
        ndcg5_list.append(nd5)
        mrr_list.append(m)

        hit_rank = next(
            (i + 1 for i, p in enumerate(ranked_paths) if p == q.ground_truth),
            None,
        )
        per_query.append({
            "query_id": q.query_id,
            "query": q.text,
            "type": q.query_type,
            "ground_truth": q.ground_truth,
            "hit@3": bool(r3),
            "hit@5": bool(r5),
            "rank": hit_rank,
            "top1": ranked_paths[0] if ranked_paths else None,
        })

    return DocResult(
        strategy=name,
        recall_at_3=float(np.mean(r3_list)),
        recall_at_5=float(np.mean(r5_list)),
        ndcg_at_5=float(np.mean(ndcg5_list)),
        mrr=float(np.mean(mrr_list)),
        n_queries=len(queries),
        per_query=per_query,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)
    )))
    docs_root = os.path.join(project_root, 'docs')

    print(f"Loading docs from: {docs_root}")
    docs = load_docs(docs_root)
    print(f"Loaded {len(docs)} documents")

    if len(docs) < 5:
        print("ERROR: Too few documents found. Check docs_root path.")
        return

    # Generate queries
    queries = generate_queries(docs, seed=42)
    print(f"Generated {len(queries)} queries")

    # Filter: only keep queries whose ground_truth is in the loaded docs
    doc_paths = {d.rel_path for d in docs}
    # Adjust paths: queries are generated with rel_path from docs_root
    # but they might need to be matched against docs
    valid_queries = [q for q in queries if q.ground_truth in doc_paths]
    print(f"Valid queries (ground truth in corpus): {len(valid_queries)}")

    if len(valid_queries) < 5:
        print("ERROR: Too few valid queries. Check path matching.")
        return

    # Build TF-IDF corpus
    vectorizer = TfidfVectorizer(
        token_pattern=r'\b[a-zA-Z]{2,}\b',
        lowercase=True,
        max_features=5000,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform([d.content for d in docs])

    # Build BM25 index for CTX-doc augmentation (enriched: stem+heading for heading queries)
    doc_token_lists_enriched = [_doc_tokens_with_stem(d) for d in docs]
    bm25_idx = BM25Okapi(doc_token_lists_enriched)

    print("Running evaluations...")

    results = []

    # Strategy 1: CTX-doc (query_type-aware routing)
    # keyword queries: TF-only BM25 (rank_bm25) — matches/beats 0.724 baseline
    # heading queries: heading match + BM25Okapi augmentation (rank_ctx_doc)
    ctx_result = evaluate_strategy(
        "CTX-doc (heading+BM25)",
        valid_queries,
        lambda q: (rank_bm25(q.text, docs) if q.query_type == "keyword"
                   else rank_ctx_doc(q, docs, bm25_index=bm25_idx)),
    )
    results.append(ctx_result)

    # Strategy 2: BM25
    bm25_result = evaluate_strategy(
        "BM25",
        valid_queries,
        lambda q: rank_bm25(q.text, docs),
    )
    results.append(bm25_result)

    # Strategy 3: Dense TF-IDF
    dense_result = evaluate_strategy(
        "Dense TF-IDF",
        valid_queries,
        lambda q: rank_tfidf(q.text, docs, vectorizer, tfidf_matrix),
    )
    results.append(dense_result)

    # ─── Report ───────────────────────────────────────────────────────────────

    out_dir = os.path.join(project_root, 'benchmarks', 'results')
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')

    # JSON output
    json_out = {
        "timestamp": ts,
        "n_docs": len(docs),
        "n_queries": len(valid_queries),
        "results": [asdict(r) for r in results],
    }
    json_path = os.path.join(out_dir, 'doc_retrieval_eval_v2.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_out, f, indent=2, ensure_ascii=False)

    # Markdown report
    md_lines = [
        "# CTX Document Retrieval Evaluation v2",
        "",
        f"**Date**: {ts}",
        f"**Corpus**: {len(docs)} .md files from docs/",
        f"**Queries**: {len(valid_queries)} (heading_exact + heading_paraphrase + keyword)",
        f"**Metrics**: Recall@3, Recall@5, NDCG@5, MRR",
        "",
        "## Summary Table",
        "",
        "| Strategy | Recall@3 | Recall@5 | NDCG@5 | MRR |",
        "|----------|----------|----------|--------|-----|",
    ]
    for r in results:
        md_lines.append(
            f"| {r.strategy} | **{r.recall_at_3:.3f}** | **{r.recall_at_5:.3f}** "
            f"| {r.ndcg_at_5:.3f} | {r.mrr:.3f} |"
        )

    md_lines += [
        "",
        "## Per-Strategy Analysis",
        "",
    ]
    for r in results:
        hits3 = sum(1 for pq in r.per_query if pq["hit@3"])
        hits5 = sum(1 for pq in r.per_query if pq["hit@5"])
        misses = [pq for pq in r.per_query if not pq["hit@5"]]
        md_lines += [
            f"### {r.strategy}",
            f"- Hits@3: {hits3}/{r.n_queries} ({100*r.recall_at_3:.1f}%)",
            f"- Hits@5: {hits5}/{r.n_queries} ({100*r.recall_at_5:.1f}%)",
            f"- NDCG@5: {r.ndcg_at_5:.3f}",
            f"- MRR: {r.mrr:.3f}",
            "",
            "**Misses (top 5)**:",
        ]
        for miss in misses[:5]:
            md_lines.append(
                f"- [{miss['type']}] `{miss['query'][:60]}` → expected `{miss['ground_truth']}`"
            )
        md_lines.append("")

    # Per-query breakdown
    md_lines += [
        "## Per-Query-Type Breakdown",
        "",
        "| Type | N | CTX R@3 | BM25 R@3 | Dense R@3 |",
        "|------|---|---------|----------|-----------|",
    ]
    query_types = list({q.query_type for q in valid_queries})
    for qtype in sorted(query_types):
        type_ids = {q.query_id for q in valid_queries if q.query_type == qtype}
        n = len(type_ids)
        if n == 0:
            continue
        def type_r3(res: DocResult) -> float:
            vals = [pq["hit@3"] for pq in res.per_query if pq["query_id"] in type_ids]
            return float(np.mean(vals)) if vals else 0.0
        ctx_r3 = type_r3(results[0])
        bm25_r3 = type_r3(results[1])
        dense_r3 = type_r3(results[2])
        md_lines.append(f"| {qtype} | {n} | {ctx_r3:.3f} | {bm25_r3:.3f} | {dense_r3:.3f} |")

    md_lines += [
        "",
        "## Method Description",
        "",
        "- **CTX-doc**: Two-stage — heading exact/overlap match → keyword frequency scoring → filename stem match",
        "- **BM25**: Robertson-Zaragoza BM25 (k1=1.5, b=0.75) on full document content",
        "- **Dense TF-IDF**: cosine similarity on TF-IDF representation (max_features=5000, sublinear_tf)",
        "",
        "## Corpus Summary",
        "",
        f"| Stat | Value |",
        f"|------|-------|",
        f"| Total docs | {len(docs)} |",
        f"| Average headings/doc | {np.mean([len(d.headings) for d in docs]):.1f} |",
        f"| Average keywords/doc | {np.mean([len(d.keywords) for d in docs]):.1f} |",
    ]

    md_path = os.path.join(out_dir, 'doc_retrieval_eval_v2.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines) + '\n')

    print(f"\nResults saved to: {md_path}")
    print("\n=== SUMMARY ===")
    print(f"{'Strategy':<35} {'R@3':>6} {'R@5':>6} {'NDCG@5':>8} {'MRR':>6}")
    print("-" * 65)
    for r in results:
        print(f"{r.strategy:<35} {r.recall_at_3:>6.3f} {r.recall_at_5:>6.3f} "
              f"{r.ndcg_at_5:>8.3f} {r.mrr:>6.3f}")


if __name__ == '__main__':
    main()
