#!/usr/bin/env python3
"""
G2-DOCS Paraphrase Eval — 30 pairs, diverse difficulty
=======================================================
Tests BM25 retrieval against paraphrase queries (different vocabulary from answers).
Unlike the original 10-pair eval (keyword-identical inflation), these queries
deliberately use different vocabulary from the answer text.

Difficulty levels:
  easy:   synonyms within same domain
  medium: indirect reference, reformulation
  hard:   semantic reframe, comparison frame, negation, numeric_indirect

Run:
  cd /home/jayone/Project/CTX
  python3 benchmarks/eval/g2_docs_paraphrase_eval.py 2>&1
"""

import json
import re
import time
from pathlib import Path
from typing import List, Tuple

from rank_bm25 import BM25Okapi


# ──────────────────────────────────────────────────────────────────────────────
# 30 Paraphrase QA Pairs
# Each query uses different vocabulary from the answer_keywords.
# ──────────────────────────────────────────────────────────────────────────────

QA_PAIRS = [
    # ── Group 1: Retrieval performance — paraphrase of metric values ──────────
    {
        "id": 1,
        "category": "retrieval_perf",
        "difficulty": "medium",
        "query": "어떤 검색 방식이 가장 높은 의사결정 회상 정확도를 달성했나?",
        "answer_keywords": ["0.881", "bm25_retrieval", "BM25 query"],
        "note": "paraphrase of 'BM25 Recall@5=0.881' — uses '회상 정확도' instead of 'recall'"
    },
    {
        "id": 2,
        "category": "retrieval_perf",
        "difficulty": "medium",
        "query": "현재 CTX가 사용 중인 프로덕션 훅의 실제 의사결정 회상 수치는?",
        "answer_keywords": ["0.169", "16.9%"],
        "note": "paraphrase of 'git_memory_real recall=0.169' — uses '프로덕션 훅' not 'git_memory'"
    },
    {
        "id": 3,
        "category": "retrieval_perf",
        "difficulty": "medium",
        "query": "전체 git 로그를 context로 넣었을 때 달성 가능한 최대 회상률은?",
        "answer_keywords": ["0.712", "71.2%", "full_dump"],
        "note": "paraphrase of 'full_dump recall=0.712' — oracle ceiling framed as upper bound"
    },
    {
        "id": 4,
        "category": "retrieval_perf",
        "difficulty": "medium",
        "query": "의미 유사도 기반 검색의 전체 recall 수치는?",
        "answer_keywords": ["0.644", "dense_embedding"],
        "note": "paraphrase of 'dense_embedding recall=0.644'"
    },
    {
        "id": 5,
        "category": "efficiency",
        "difficulty": "hard",
        "query": "BM25가 oracle 방식보다 얼마나 효율적인 컨텍스트를 사용하나?",
        "answer_keywords": ["17.5", "17.5x"],
        "note": "paraphrase of '17.5x smaller' — uses '효율적인' not 'smaller'"
    },

    # ── Group 2: Temporal recall breakdown ───────────────────────────────────
    {
        "id": 6,
        "category": "temporal",
        "difficulty": "medium",
        "query": "7일 이내 최신 커밋에 대해 BM25가 달성한 recall은?",
        "answer_keywords": ["0.911", "91.1%"],
        "note": "paraphrase of 'bm25 0-7d recall=0.911'"
    },
    {
        "id": 7,
        "category": "temporal",
        "difficulty": "hard",
        "query": "한 달 이내 오래된 의사결정에 대해 proactive injection 방식이 얼마나 기억하나?",
        "answer_keywords": ["0.000", "zero", "0%"],
        "note": "paraphrase of '7-30d recall=0.000 for proactive methods' — uses '오래된 의사결정' not '7-30d'"
    },
    {
        "id": 8,
        "category": "temporal",
        "difficulty": "hard",
        "query": "full_dump가 7-30일 구간에서 낮은 성능을 보이는 이유는?",
        "answer_keywords": ["n=100", "100 commit", "window"],
        "note": "asks WHY full_dump fails on 7-30d — answer is n=100 window"
    },
    {
        "id": 9,
        "category": "temporal",
        "difficulty": "medium",
        "query": "연령 버킷별로 일관된 성능을 보인 검색 방식은?",
        "answer_keywords": ["dense", "0.643", "0.644"],
        "note": "paraphrase of 'dense embedding age-insensitive 0.643-0.644'"
    },

    # ── Group 3: Context size and architecture ────────────────────────────────
    {
        "id": 10,
        "category": "architecture",
        "difficulty": "easy",
        "query": "전체 git 로그 방식의 평균 context 크기(문자수)는?",
        "answer_keywords": ["12,186", "12186"],
        "note": "paraphrase of 'full_dump ~12,186 chars'"
    },
    {
        "id": 11,
        "category": "architecture",
        "difficulty": "medium",
        "query": "BM25 query-aware retrieval이 사용하는 평균 토큰은?",
        "answer_keywords": ["174", "~174"],
        "note": "paraphrase of 'BM25 ~174 tokens'"
    },
    {
        "id": 12,
        "category": "architecture",
        "difficulty": "hard",
        "query": "indexed된 의사결정 커밋의 총 수는?",
        "answer_keywords": ["163"],
        "note": "paraphrase of '163 decision commits in corpus'"
    },
    {
        "id": 13,
        "category": "architecture",
        "difficulty": "hard",
        "query": "G1 권장 하이브리드 아키텍처에서 proactive로 주입하는 결정 수는?",
        "answer_keywords": ["3", "last 3"],
        "note": "paraphrase of 'hybrid: proactive last 3 decisions + BM25 top-4'"
    },

    # ── Group 4: Open-set / external repos ───────────────────────────────────
    {
        "id": 14,
        "category": "open_set",
        "difficulty": "hard",
        "query": "외부 저장소 평가에서 가장 강건한(나이 불변) 검색 방식은?",
        "answer_keywords": ["dense", "0.375", "dense_embedding"],
        "note": "paraphrase of 'dense_embedding is most robust in open-set' — uses '강건한' not 'robust'"
    },
    {
        "id": 15,
        "category": "open_set",
        "difficulty": "hard",
        "query": "BM25가 외부 저장소에서 성능이 얼마나 하락하는가?",
        "answer_keywords": ["72%", "-72%", "0.250"],
        "note": "paraphrase of 'BM25 open-set drop = -72%'"
    },
    {
        "id": 16,
        "category": "open_set",
        "difficulty": "medium",
        "query": "Django 저장소에서 BM25 retrieval의 성적은?",
        "answer_keywords": ["0.000", "0.0", "zero"],
        "note": "paraphrase of 'BM25 Django = 0.000'"
    },
    {
        "id": 17,
        "category": "open_set",
        "difficulty": "medium",
        "query": "open-set 평가에서 사용된 외부 저장소 수와 QA 쌍 수는?",
        "answer_keywords": ["3", "16", "Flask", "Requests", "Django"],
        "note": "paraphrase of '3 repos, 16 quality-filtered pairs'"
    },

    # ── Group 5: CTX internal benchmark (doc/code retrieval) ─────────────────
    {
        "id": 18,
        "category": "ctx_internal",
        "difficulty": "easy",
        "query": "heading paraphrase 타입에서 CTX가 달성한 R@3은?",
        "answer_keywords": ["1.000", "100%"],
        "note": "paraphrase of 'heading_paraphrase R@3=1.000' — still uses 'paraphrase' which is query type name"
    },
    {
        "id": 19,
        "category": "ctx_internal",
        "difficulty": "medium",
        "query": "CTX의 keyword 쿼리 성능이 최종적으로 BM25 단독과 동등해진 수치는?",
        "answer_keywords": ["0.724", "72.4%"],
        "note": "paraphrase of 'keyword R@3=0.724' — '동등해진' frames as convergence"
    },
    {
        "id": 20,
        "category": "ctx_internal",
        "difficulty": "hard",
        "query": "BM25 단독 대비 CTX 통합 시스템의 전체 문서 검색 R@5 성능은?",
        "answer_keywords": ["0.954", "0.862", "CTX-doc"],
        "note": "paraphrase of 'CTX-doc R@5=0.954' or R@3=0.862"
    },
    {
        "id": 21,
        "category": "ctx_internal",
        "difficulty": "hard",
        "query": "CTX가 TF-IDF 방식을 대체한 새 랭킹 알고리즘과 그 이유는?",
        "answer_keywords": ["BM25", "rank_bm25", "0.379"],
        "note": "paraphrase of 'replaced TF-IDF with BM25 because keyword R@3 was 0.379'"
    },

    # ── Group 6: G2-DOCS evaluation fairness ─────────────────────────────────
    {
        "id": 22,
        "category": "g2_docs",
        "difficulty": "medium",
        "query": "쿼리와 정답에 동일한 단어를 사용했을 때 G2-DOCS 성능은?",
        "answer_keywords": ["1.000", "10/10"],
        "note": "paraphrase of 'keyword-identical eval: 10/10=1.000'"
    },
    {
        "id": 23,
        "category": "g2_docs",
        "difficulty": "medium",
        "query": "다른 어휘를 쓴 쿼리로 G2-DOCS를 재평가하면 실제 성능은?",
        "answer_keywords": ["0.700", "7/10"],
        "note": "paraphrase of 'paraphrase eval: 7/10=0.700' — uses '다른 어휘' not 'paraphrase'"
    },
    {
        "id": 24,
        "category": "g2_docs",
        "difficulty": "hard",
        "query": "G2-DOCS eval에서 BM25가 틀린 문서를 선택한 쿼리 타입은?",
        "answer_keywords": ["comparison", "numeric_indirect", "indirect"],
        "note": "paraphrase of '3 miss categories' — asks what types failed"
    },
    {
        "id": 25,
        "category": "g2_docs",
        "difficulty": "hard",
        "query": "G2b 코드 파일 발견이 외부 파일에서 실패하는 이유는?",
        "answer_keywords": ["CLAUDE_PROJECT_DIR", "hooks", "외부", "outside"],
        "note": "paraphrase of 'G2b scope limited to CLAUDE_PROJECT_DIR'"
    },

    # ── Group 7: G1 query type diversity ─────────────────────────────────────
    {
        "id": 26,
        "category": "g1_diversity",
        "difficulty": "easy",
        "query": "type1 쿼리에 대한 BM25 구조적 recall은?",
        "answer_keywords": ["1.000", "59/59"],
        "note": "uses 'type1' explicitly — still fair as docs use 'type1' too"
    },
    {
        "id": 27,
        "category": "g1_diversity",
        "difficulty": "medium",
        "query": "왜/무엇 형태의 어려운 쿼리에서 BM25 structural recall은?",
        "answer_keywords": ["0.750", "6/8"],
        "note": "paraphrase of 'type2/3/4 strict recall=0.750' — uses '왜/무엇 형태' not type numbers"
    },
    {
        "id": 28,
        "category": "g1_diversity",
        "difficulty": "hard",
        "query": "BM25가 score=0을 반환한 쿼리의 원인은?",
        "answer_keywords": ["Korean", "어휘", "vocabulary", "score=0", "0.0"],
        "note": "paraphrase of 'BM25 complete failure on Korean-English mismatch query'"
    },
    {
        "id": 29,
        "category": "g1_diversity",
        "difficulty": "hard",
        "query": "한국어 조사를 처리하도록 tokenizer를 수정한 이유는?",
        "answer_keywords": ["particle", "조사", "BM25와", "와→", "Korean"],
        "note": "paraphrase of 'tokenizer v2: Korean particle stripping'"
    },

    # ── Group 8: Decision motivation ─────────────────────────────────────────
    {
        "id": 30,
        "category": "decision",
        "difficulty": "hard",
        "query": "proactive injection 방식에서 query-time retrieval로 전환한 핵심 근거는?",
        "answer_keywords": ["0.169", "5.2x", "0.881", "recall"],
        "note": "paraphrase of 'git_memory 0.169 → BM25 0.881 (+5.2x)' — asks for rationale"
    },
    {
        "id": 31,
        "category": "decision",
        "difficulty": "medium",
        "query": "BM25 score 필터링 기준값을 높인 이유는?",
        "answer_keywords": ["3.0", "false positive", "거짓양성", "Korean", "threshold"],
        "note": "paraphrase of 'threshold 0→3.0 to eliminate Korean token false positives'"
    },
    {
        "id": 32,
        "category": "decision",
        "difficulty": "easy",
        "query": "G1 long-term eval에서 사용한 baseline 수는?",
        "answer_keywords": ["7", "seven"],
        "note": "paraphrase of '7 baselines' — uses '사용한 baseline 수' not 'baselines'"
    },
    {
        "id": 33,
        "category": "decision",
        "difficulty": "medium",
        "query": "G1 eval QA pair 생성에 사용된 LLM 호출 총 수는?",
        "answer_keywords": ["413"],
        "note": "paraphrase of '413 LLM calls (59 pairs × 7 baselines)'"
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# BM25 index construction
# ──────────────────────────────────────────────────────────────────────────────

_KO_PARTICLES = re.compile(
    r'(와|과|이|가|은|는|을|를|의|에서|으로|에게|부터|까지|처럼|같이|보다|이나|며|에|로|도|만|나|고)$'
)


def tokenize(text: str) -> List[str]:
    """Preserve decimal numbers and numeric ranges. Strip Korean particles from mixed tokens."""
    raw = re.findall(r'\d+[-\u2013]\d+|\d+\.\d+|\w+', text.lower())
    result = []
    for tok in raw:
        cleaned = _KO_PARTICLES.sub('', tok)
        if cleaned and cleaned != tok:
            result.append(cleaned)
        result.append(tok)
    return list(dict.fromkeys(result))


def chunk_document(filename: str, content: str) -> List[str]:
    """Split by ## section headers."""
    chunks = []
    parts = re.split(r'\n(?=## )', content)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split('\n', 1)
        header_line = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ''
        header = re.sub(r'^#+\s*', '', header_line)
        chunk_text = f"{filename} § {header}\n{body}"
        if len(body) > 50:
            chunks.append(chunk_text)
    if not chunks and len(content) > 50:
        chunks.append(f"{filename} § (full)\n{content}")
    return chunks


def build_bm25_index(research_dir: Path) -> Tuple[BM25Okapi, List[str]]:
    """Index all *.md files + supplementary memory files."""
    md_files = sorted(research_dir.glob("*.md"))
    all_chunks: List[str] = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8", errors="replace")
        all_chunks.extend(chunk_document(md_file.name, content))

    extra_files = [
        Path("/home/jayone/Project/CTX/CLAUDE.md"),
        Path("/home/jayone/.claude/projects/-home-jayone-Project-CTX/memory/MEMORY.md"),
    ]
    for ef in extra_files:
        if ef.exists():
            content = ef.read_text(encoding="utf-8", errors="replace")
            all_chunks.extend(chunk_document(ef.name, content))

    tokenized_corpus = [tokenize(chunk) for chunk in all_chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    return bm25, all_chunks


def retrieve_top_k(query: str, bm25: BM25Okapi, chunks: List[str], k: int = 5) -> Tuple[List[str], List[float]]:
    scores = bm25.get_scores(tokenize(query))
    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [chunks[i] for i in top_idx], [scores[i] for i in top_idx]


def bm25_kw_check(answer_keywords: List[str], top_chunks: List[str]) -> bool:
    combined = "\n".join(top_chunks).lower()
    return any(kw.lower() in combined for kw in answer_keywords)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    research_dir = Path("/home/jayone/Project/CTX/docs/research")
    results_dir = Path("/home/jayone/Project/CTX/benchmarks/results")

    print("=" * 70)
    print("G2-DOCS Paraphrase Eval — 33 pairs, diverse difficulty")
    print("BM25-keyword structural check (no LLM needed)")
    print("=" * 70)

    # Build index
    t0 = time.time()
    bm25, chunks = build_bm25_index(research_dir)
    build_ms = (time.time() - t0) * 1000
    print(f"\nIndex: {len(chunks)} chunks from {len(list(research_dir.glob('*.md')))} docs ({build_ms:.0f}ms)")

    # Difficulty breakdown
    diff_counts = {}
    for qa in QA_PAIRS:
        d = qa["difficulty"]
        diff_counts[d] = diff_counts.get(d, 0) + 1
    print(f"QA pairs: {len(QA_PAIRS)} total — " + " | ".join(f"{d}: {n}" for d, n in sorted(diff_counts.items())))
    print()

    results = []
    by_category: dict = {}
    by_difficulty: dict = {}

    for qa in QA_PAIRS:
        top_chunks, top_scores = retrieve_top_k(qa["query"], bm25, chunks, k=5)
        correct = bm25_kw_check(qa["answer_keywords"], top_chunks)
        top1_score = top_scores[0] if top_scores else 0.0
        top1_preview = top_chunks[0][:100].replace('\n', ' ') if top_chunks else ""

        verdict = "YES" if correct else "NO "
        results.append({**qa, "correct": correct, "top1_score": top1_score})

        cat = qa["category"]
        diff = qa["difficulty"]
        by_category.setdefault(cat, []).append(correct)
        by_difficulty.setdefault(diff, []).append(correct)

        print(f"[{qa['id']:02d}] [{verdict}] ({diff:6s}) {qa['query'][:60]}")
        print(f"      keywords={qa['answer_keywords']} | top1_score={top1_score:.1f}")
        if not correct:
            print(f"      MISS — top1: {top1_preview}...")
        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(results)
    n_correct = sum(r["correct"] for r in results)
    recall = n_correct / total

    print("=" * 70)
    print(f"OVERALL: {n_correct}/{total} = {recall:.3f} ({recall * 100:.1f}%)")
    print()
    print("By difficulty:")
    for diff in ["easy", "medium", "hard"]:
        if diff in by_difficulty:
            n = len(by_difficulty[diff])
            c = sum(by_difficulty[diff])
            print(f"  {diff:6s}: {c}/{n} = {c/n:.3f}")
    print()
    print("By category:")
    for cat, vals in sorted(by_category.items()):
        c = sum(vals)
        n = len(vals)
        print(f"  {cat:20s}: {c}/{n} = {c/n:.3f}")
    print()

    # Comparison with keyword-identical baseline
    print("Comparison:")
    print(f"  Keyword-identical (original 10 pairs): 1.000 — inflated (same vocab as answers)")
    print(f"  Paraphrase 10-pair (prev session):     0.700 — honest fairness-adjusted")
    print(f"  Paraphrase 33-pair (this eval):        {recall:.3f} — expanded statistical confidence")

    # Save results
    results_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "eval": "g2_docs_paraphrase_eval",
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "num_pairs": total,
        "num_correct": n_correct,
        "recall": recall,
        "by_difficulty": {d: {"correct": sum(v), "total": len(v), "recall": sum(v) / len(v)}
                          for d, v in by_difficulty.items()},
        "by_category": {c: {"correct": sum(v), "total": len(v), "recall": sum(v) / len(v)}
                        for c, v in by_category.items()},
        "results": [{
            "id": r["id"],
            "category": r["category"],
            "difficulty": r["difficulty"],
            "query": r["query"],
            "answer_keywords": r["answer_keywords"],
            "correct": r["correct"],
            "top1_score": r["top1_score"],
        } for r in results],
    }
    out_path = results_dir / "g2_docs_paraphrase_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")
    return recall


if __name__ == "__main__":
    main()
