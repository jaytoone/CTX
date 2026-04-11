#!/usr/bin/env python3
"""
G2-DOCS A/B Retrieval Strategy Comparison
==========================================
Compares 4 retrieval strategies for bm25_search_docs() in bm25-memory.py hook:

  A: bm25_chunked      — current implementation (split by ##, BM25Okapi on full chunk)
  B: bm25_fulldoc      — whole doc as unit (no chunking), BM25 on full content
  C: pageindex_header  — PageIndex-inspired: BM25 over section headers only, return full section
  D: hybrid            — max(A_score_norm, C_score_norm) per doc

Metric: recall@5 — any of top-5 retrieved units contains at least one answer_keyword.

Run:
  cd /home/jayone/Project/CTX
  python3 benchmarks/eval/g2_docs_ab_test.py 2>&1
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

from rank_bm25 import BM25Okapi

# ── 33 paraphrase QA pairs ────────────────────────────────────────────────────

QA_PAIRS = [
    {"id": 1,  "difficulty": "medium", "category": "retrieval_perf",
     "query": "어떤 검색 방식이 가장 높은 의사결정 회상 정확도를 달성했나?",
     "answer_keywords": ["0.881", "bm25_retrieval", "BM25 query"]},
    {"id": 2,  "difficulty": "medium", "category": "retrieval_perf",
     "query": "현재 CTX가 사용 중인 프로덕션 훅의 실제 의사결정 회상 수치는?",
     "answer_keywords": ["0.169", "16.9%"]},
    {"id": 3,  "difficulty": "medium", "category": "retrieval_perf",
     "query": "전체 git 로그를 context로 넣었을 때 달성 가능한 최대 회상률은?",
     "answer_keywords": ["0.712", "71.2%", "full_dump"]},
    {"id": 4,  "difficulty": "medium", "category": "retrieval_perf",
     "query": "의미 유사도 기반 검색의 전체 recall 수치는?",
     "answer_keywords": ["0.644", "dense_embedding"]},
    {"id": 5,  "difficulty": "hard",   "category": "efficiency",
     "query": "BM25가 oracle 방식보다 얼마나 효율적인 컨텍스트를 사용하나?",
     "answer_keywords": ["17.5", "17.5x"]},
    {"id": 6,  "difficulty": "medium", "category": "temporal",
     "query": "7일 이내 최신 커밋에 대해 BM25가 달성한 recall은?",
     "answer_keywords": ["0.911", "91.1%"]},
    {"id": 7,  "difficulty": "hard",   "category": "temporal",
     "query": "한 달 이내 오래된 의사결정에 대해 proactive injection 방식이 얼마나 기억하나?",
     "answer_keywords": ["0.000", "zero", "0%"]},
    {"id": 8,  "difficulty": "hard",   "category": "temporal",
     "query": "full_dump가 7-30일 구간에서 낮은 성능을 보이는 이유는?",
     "answer_keywords": ["n=100", "100 commit", "window"]},
    {"id": 9,  "difficulty": "medium", "category": "temporal",
     "query": "연령 버킷별로 일관된 성능을 보인 검색 방식은?",
     "answer_keywords": ["dense", "0.643", "0.644"]},
    {"id": 10, "difficulty": "easy",   "category": "architecture",
     "query": "전체 git 로그 방식의 평균 context 크기(문자수)는?",
     "answer_keywords": ["12,186", "12186"]},
    {"id": 11, "difficulty": "medium", "category": "architecture",
     "query": "BM25 query-aware retrieval이 사용하는 평균 토큰은?",
     "answer_keywords": ["174", "~174"]},
    {"id": 12, "difficulty": "hard",   "category": "architecture",
     "query": "indexed된 의사결정 커밋의 총 수는?",
     "answer_keywords": ["163"]},
    {"id": 13, "difficulty": "hard",   "category": "architecture",
     "query": "G1 권장 하이브리드 아키텍처에서 proactive로 주입하는 결정 수는?",
     "answer_keywords": ["3", "last 3"]},
    {"id": 14, "difficulty": "hard",   "category": "open_set",
     "query": "외부 저장소 평가에서 가장 강건한(나이 불변) 검색 방식은?",
     "answer_keywords": ["dense", "0.375", "dense_embedding"]},
    {"id": 15, "difficulty": "hard",   "category": "open_set",
     "query": "BM25가 외부 저장소에서 성능이 얼마나 하락하는가?",
     "answer_keywords": ["72%", "-72%", "0.250"]},
    {"id": 16, "difficulty": "medium", "category": "open_set",
     "query": "Django 저장소에서 BM25 retrieval의 성적은?",
     "answer_keywords": ["0.000", "0.0", "zero"]},
    {"id": 17, "difficulty": "medium", "category": "open_set",
     "query": "open-set 평가에서 사용된 외부 저장소 수와 QA 쌍 수는?",
     "answer_keywords": ["3", "16", "Flask", "Requests", "Django"]},
    {"id": 18, "difficulty": "easy",   "category": "ctx_internal",
     "query": "heading paraphrase 타입에서 CTX가 달성한 R@3은?",
     "answer_keywords": ["1.000", "100%"]},
    {"id": 19, "difficulty": "medium", "category": "ctx_internal",
     "query": "CTX의 keyword 쿼리 성능이 최종적으로 BM25 단독과 동등해진 수치는?",
     "answer_keywords": ["0.724", "72.4%"]},
    {"id": 20, "difficulty": "hard",   "category": "ctx_internal",
     "query": "BM25 단독 대비 CTX 통합 시스템의 전체 문서 검색 R@5 성능은?",
     "answer_keywords": ["0.954", "0.862", "CTX-doc"]},
    {"id": 21, "difficulty": "hard",   "category": "ctx_internal",
     "query": "CTX가 TF-IDF 방식을 대체한 새 랭킹 알고리즘과 그 이유는?",
     "answer_keywords": ["BM25", "rank_bm25", "0.379"]},
    {"id": 22, "difficulty": "medium", "category": "g2_docs",
     "query": "쿼리와 정답에 동일한 단어를 사용했을 때 G2-DOCS 성능은?",
     "answer_keywords": ["1.000", "10/10"]},
    {"id": 23, "difficulty": "medium", "category": "g2_docs",
     "query": "다른 어휘를 쓴 쿼리로 G2-DOCS를 재평가하면 실제 성능은?",
     "answer_keywords": ["0.700", "7/10"]},
    {"id": 24, "difficulty": "hard",   "category": "g2_docs",
     "query": "G2-DOCS 평가에서 BM25가 틀린 문서를 선택한 쿼리 타입은?",
     "answer_keywords": ["comparison", "numeric_indirect", "indirect"]},
    {"id": 25, "difficulty": "hard",   "category": "g2_docs",
     "query": "G2b 코드 파일 발견이 외부 파일에서 실패하는 이유는?",
     "answer_keywords": ["CLAUDE_PROJECT_DIR", "hooks", "외부", "outside"]},
    {"id": 26, "difficulty": "easy",   "category": "g1_diversity",
     "query": "type1 쿼리에 대한 BM25 구조적 recall은?",
     "answer_keywords": ["1.000", "59/59"]},
    {"id": 27, "difficulty": "medium", "category": "g1_diversity",
     "query": "왜/무엇 형태의 어려운 쿼리에서 BM25 structural recall은?",
     "answer_keywords": ["0.750", "6/8"]},
    {"id": 28, "difficulty": "hard",   "category": "g1_diversity",
     "query": "BM25가 score=0을 반환한 쿼리의 원인은?",
     "answer_keywords": ["Korean", "어휘", "vocabulary", "score=0", "0.0"]},
    {"id": 29, "difficulty": "hard",   "category": "g1_diversity",
     "query": "한국어 조사를 처리하도록 tokenizer를 수정한 이유는?",
     "answer_keywords": ["particle", "조사", "BM25와", "와→", "Korean"]},
    {"id": 30, "difficulty": "hard",   "category": "decision",
     "query": "proactive injection 방식에서 query-time retrieval로 전환한 핵심 근거는?",
     "answer_keywords": ["0.169", "5.2x", "0.881", "recall"]},
    {"id": 31, "difficulty": "medium", "category": "decision",
     "query": "BM25 score 필터링 기준값을 높인 이유는?",
     "answer_keywords": ["3.0", "false positive", "거짓양성", "Korean", "threshold"]},
    {"id": 32, "difficulty": "easy",   "category": "decision",
     "query": "G1 long-term 실험에서 사용한 baseline 수는?",
     "answer_keywords": ["7", "seven"]},
    {"id": 33, "difficulty": "medium", "category": "decision",
     "query": "G1 QA pair 생성에 사용된 LLM 호출 총 수는?",
     "answer_keywords": ["413"]},
]

# ── Tokenizer ─────────────────────────────────────────────────────────────────

_KO_PARTICLES = re.compile(
    r'(와|과|이|가|은|는|을|를|의|에서|으로|에게|부터|까지|처럼|같이|보다|이나|며|에|로|도|만|나|고)$'
)


def tokenize(text: str) -> List[str]:
    raw = re.findall(r'\d+[-\u2013]\d+|\d+\.\d+|\w+', text.lower())
    result = []
    for tok in raw:
        cleaned = _KO_PARTICLES.sub('', tok)
        if cleaned and cleaned != tok:
            result.append(cleaned)
        result.append(tok)
    return list(dict.fromkeys(result))


# ── Document loading ──────────────────────────────────────────────────────────

def load_docs(research_dir: Path) -> List[Tuple[str, str]]:
    docs = []
    for md_file in sorted(research_dir.glob("*.md")):
        try:
            docs.append((md_file.name, md_file.read_text(encoding="utf-8", errors="replace")))
        except Exception:
            pass
    extra = [
        Path("/home/jayone/Project/CTX/CLAUDE.md"),
        Path("/home/jayone/.claude/projects/-home-jayone-Project-CTX/memory/MEMORY.md"),
    ]
    for ef in extra:
        if ef.exists():
            docs.append((ef.name, ef.read_text(encoding="utf-8", errors="replace")))
    return docs


# ── Strategy A: bm25_chunked (current) ───────────────────────────────────────

def build_chunked(docs: List[Tuple[str, str]]) -> Tuple[BM25Okapi, List[str]]:
    chunks = []
    for fname, content in docs:
        parts = re.split(r'\n(?=## )', content)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            lines = part.split('\n', 1)
            header = re.sub(r'^#+\s*', '', lines[0].strip())
            body = lines[1].strip() if len(lines) > 1 else ''
            text = f"{fname} § {header}\n{body}"
            if len(text) > 50:
                chunks.append(text[:2500])
    return BM25Okapi([tokenize(c) for c in chunks]), chunks


def retrieve_chunked(query: str, bm25: BM25Okapi, chunks: List[str],
                     k: int = 5, threshold: float = 3.0) -> List[str]:
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [chunks[i] for i in ranked[:k] if scores[i] > threshold]


# ── Strategy B: bm25_fulldoc ─────────────────────────────────────────────────

def build_fulldoc(docs: List[Tuple[str, str]]) -> Tuple[BM25Okapi, List[str]]:
    units = [f"{fname}\n{content}" for fname, content in docs]
    return BM25Okapi([tokenize(u) for u in units]), units


def retrieve_fulldoc(query: str, bm25: BM25Okapi, units: List[str], k: int = 5) -> List[str]:
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [units[i] for i in ranked[:k]]


# ── Strategy C: pageindex_header ─────────────────────────────────────────────

def build_pageindex_header(docs: List[Tuple[str, str]]) -> Tuple[BM25Okapi, List[Tuple[str, str]]]:
    """BM25 indexed on section headers only; retrieval returns full section body."""
    entries = []
    for fname, content in docs:
        parts = re.split(r'\n(?=## )', content)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            lines = part.split('\n', 1)
            header_title = re.sub(r'^#+\s*', '', lines[0].strip())
            body = lines[1].strip() if len(lines) > 1 else ''
            header_text = f"{fname}: {header_title}"
            full_section = f"{fname} § {header_title}\n{body}"
            if len(header_text) > 5:
                entries.append((header_text, full_section[:2500]))
    tokenized = [tokenize(h) for h, _ in entries]
    return BM25Okapi(tokenized), entries


def retrieve_pageindex_header(query: str, bm25: BM25Okapi,
                               entries: List[Tuple[str, str]], k: int = 5) -> List[str]:
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return [entries[i][1] for i in ranked[:k] if scores[i] > 0]


# ── Strategy D: hybrid (A + C) ────────────────────────────────────────────────

def retrieve_hybrid(query: str,
                    bm25_a: BM25Okapi, chunks_a: List[str],
                    bm25_c: BM25Okapi, entries_c: List[Tuple[str, str]],
                    k: int = 5, threshold: float = 1.5) -> List[str]:
    scores_a = bm25_a.get_scores(tokenize(query))
    scores_c = bm25_c.get_scores(tokenize(query))
    max_a = max(scores_a) if max(scores_a) > 0 else 1.0
    max_c = max(scores_c) if max(scores_c) > 0 else 1.0
    norm_a = [s / max_a for s in scores_a]
    norm_c = [s / max_c for s in scores_c]

    seen: Dict[str, Tuple[float, str]] = {}
    for sc, text in zip(norm_a, chunks_a):
        key = text[:80]
        seen[key] = (max(sc, seen.get(key, (0.0, ""))[0]), text)
    for sc, (_, full_section) in zip(norm_c, entries_c):
        key = full_section[:80]
        seen[key] = (max(sc, seen.get(key, (0.0, ""))[0]), full_section)

    ranked = sorted(seen.values(), key=lambda x: -x[0])
    return [text for sc, text in ranked[:k] if sc * max(max_a, max_c) > threshold]


# ── Benchmark runner ──────────────────────────────────────────────────────────

def kw_hit(answer_keywords: List[str], retrieved: List[str]) -> bool:
    combined = "\n".join(retrieved).lower()
    return any(kw.lower() in combined for kw in answer_keywords)


def run_strategy(name: str, retrieve_fn, qa_pairs: List[dict]) -> dict:
    results = []
    for qa in qa_pairs:
        retrieved = retrieve_fn(qa["query"])
        hit = kw_hit(qa["answer_keywords"], retrieved)
        results.append({
            "id": qa["id"],
            "difficulty": qa["difficulty"],
            "category": qa["category"],
            "hit": hit,
            "n_retrieved": len(retrieved),
        })
    total = len(results)
    n_hit = sum(r["hit"] for r in results)
    by_diff = {}
    by_cat = {}
    for r in results:
        by_diff.setdefault(r["difficulty"], []).append(r["hit"])
        by_cat.setdefault(r["category"], []).append(r["hit"])
    return {
        "strategy": name,
        "recall": n_hit / total,
        "n_correct": n_hit,
        "n_total": total,
        "by_difficulty": {d: {"recall": sum(v)/len(v), "n": len(v)} for d, v in by_diff.items()},
        "by_category": {c: {"recall": sum(v)/len(v), "n": len(v)} for c, v in by_cat.items()},
        "results": results,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    research_dir = Path("/home/jayone/Project/CTX/docs/research")
    results_dir = Path("/home/jayone/Project/CTX/benchmarks/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("G2-DOCS A/B Retrieval Strategy Comparison")
    print("=" * 70)
    print(f"Queries: {len(QA_PAIRS)} paraphrase pairs")

    docs = load_docs(research_dir)
    print(f"Loaded {len(docs)} documents")

    # Build indices
    t = time.time(); bm25_a, chunks_a = build_chunked(docs);      ta = (time.time()-t)*1000
    t = time.time(); bm25_b, units_b  = build_fulldoc(docs);      tb = (time.time()-t)*1000
    t = time.time(); bm25_c, entries_c = build_pageindex_header(docs); tc = (time.time()-t)*1000

    print(f"\nIndex sizes: A={len(chunks_a)} chunks, B={len(units_b)} docs, C={len(entries_c)} headers")
    print(f"Build times: A={ta:.0f}ms  B={tb:.0f}ms  C={tc:.0f}ms")

    fn_a = lambda q: retrieve_chunked(q, bm25_a, chunks_a)
    fn_b = lambda q: retrieve_fulldoc(q, bm25_b, units_b)
    fn_c = lambda q: retrieve_pageindex_header(q, bm25_c, entries_c)
    fn_d = lambda q: retrieve_hybrid(q, bm25_a, chunks_a, bm25_c, entries_c)

    strategies = [
        ("A_bm25_chunked",     fn_a, "Current hook (## chunks, BM25, threshold=3.0)"),
        ("B_bm25_fulldoc",     fn_b, "Full-doc BM25 (no chunking)"),
        ("C_pageindex_header", fn_c, "PageIndex-lite (BM25 on headers only)"),
        ("D_hybrid_A_C",       fn_d, "Hybrid A+C (normalized union)"),
    ]

    all_results = {}
    print("\n" + "=" * 70)
    print(f"{'Strategy':<25} {'@5':>6} {'Easy':>6} {'Med':>6} {'Hard':>6}  Description")
    print("-" * 70)

    for name, fn, desc in strategies:
        t = time.time()
        res = run_strategy(name, fn, QA_PAIRS)
        ms = (time.time() - t) * 1000
        all_results[name] = res
        diff = res["by_difficulty"]
        e = diff.get("easy", {}).get("recall", 0)
        m = diff.get("medium", {}).get("recall", 0)
        h = diff.get("hard", {}).get("recall", 0)
        print(f"  {name:<25} {res['recall']:.3f}  {e:.3f}  {m:.3f}  {h:.3f}  {desc} ({ms:.0f}ms)")

    current = all_results["A_bm25_chunked"]["recall"]
    best_name = max(all_results, key=lambda k: all_results[k]["recall"])
    best = all_results[best_name]["recall"]

    print("\n" + "=" * 70)
    print(f"Delta vs current (A={current:.3f}):")
    for name, res in all_results.items():
        delta = res["recall"] - current
        sign = "+" if delta >= 0 else ""
        mark = " ← BEST" if name == best_name and name != "A_bm25_chunked" else ""
        print(f"  {name:<25} {sign}{delta:.3f}{mark}")

    if best_name != "A_bm25_chunked":
        print(f"\nCategory breakdown A vs {best_name}:")
        cats = sorted(set(list(all_results["A_bm25_chunked"]["by_category"]) +
                          list(all_results[best_name]["by_category"])))
        for cat in cats:
            a_r = all_results["A_bm25_chunked"]["by_category"].get(cat, {}).get("recall", 0)
            b_r = all_results[best_name]["by_category"].get(cat, {}).get("recall", 0)
            n = all_results["A_bm25_chunked"]["by_category"].get(cat, {}).get("n", 0)
            delta = b_r - a_r
            arrow = "^" if delta > 0.05 else ("v" if delta < -0.05 else "=")
            print(f"  {cat:<20} A={a_r:.3f}  {best_name[:1]}={b_r:.3f}  d={delta:+.3f} {arrow}  n={n}")

    print("\n" + "=" * 70)
    print("ADOPTION VERDICT:")
    if best > current + 0.05:
        print(f"  ADOPT {best_name}: +{best-current:.3f} improvement (>{5}% threshold)")
    elif best > current + 0.02:
        print(f"  MARGINAL: {best_name} +{best-current:.3f} (within 2-5% — consider latency trade-off)")
    else:
        print(f"  SKIP: No strategy beats current by >0.02. BM25-chunked is already near-optimal.")
        print(f"  Note: PageIndex/LightRAG require LLM calls — not suitable for <1ms hook constraint.")

    # Save
    out = {
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "n_queries": len(QA_PAIRS),
        "n_docs": len(docs),
        "strategies": {name: {k: v for k, v in res.items() if k != "results"}
                       for name, res in all_results.items()},
        "best": best_name,
        "current_baseline": "A_bm25_chunked",
        "delta_best_vs_current": round(best - current, 4),
        "verdict": "adopt" if best > current + 0.05
                   else "marginal" if best > current + 0.02
                   else "skip",
    }
    out_path = results_dir / "g2_docs_ab_results.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
