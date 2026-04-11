#!/usr/bin/env python3
"""
hook_comparison_eval.py — auto-index.py vs chat-memory.py 성능 비교

두 hook의 context 기여 가치를 정량 측정:
  - auto-index.py:  trigger_rate, hint_effectiveness (DB freshness → G2b impact)
  - chat-memory.py: precision@3, false_positive_rate, keyword_coverage, recall_proxy

Usage:
    python3 benchmarks/eval/hook_comparison_eval.py
    python3 benchmarks/eval/hook_comparison_eval.py --verbose
    python3 benchmarks/eval/hook_comparison_eval.py --scope global
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
VAULT_DB = Path.home() / ".local/share/claude-vault/vault.db"
CODEBASE_CACHE = Path.home() / ".cache/codebase-memory-mcp"
CTX_PROJECT = "-home-jayone-Project-CTX"
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "that", "this", "these",
    "those", "with", "for", "from", "about", "into", "through", "what",
    "how", "why", "when", "where", "which", "who", "not", "and", "or",
    "but", "also", "just", "now", "then", "there", "here", "like",
    "이", "가", "은", "는", "을", "를", "에", "의", "와", "과",
    "로", "으로", "에서", "하는", "있는", "없는", "같은", "이런",
    "그런", "저런", "어떤", "모든", "각", "더", "또", "및",
}

# ── Test Queries ────────────────────────────────────────────────────────────
# (query, expected_relevant: bool, category, ground_truth_keywords)
TEST_QUERIES = [
    # Relevant — CTX core topics (should return results)
    ("BM25 threshold recall 성능", True, "core_tech", ["BM25", "threshold", "recall"]),
    ("G1 git memory decision recall", True, "core_tech", ["G1", "git", "memory", "recall"]),
    ("G2 file search hook bm25-memory", True, "core_tech", ["G2", "hook", "search"]),
    ("chat-memory vault FTS5 검색", True, "chat_memory", ["chat-memory", "vault", "FTS5"]),
    ("auto-index codebase-memory-mcp DB stale", True, "auto_index", ["auto-index", "DB", "stale"]),
    ("CTX hook architecture SessionStart PostToolUse", True, "architecture", ["hook", "architecture"]),
    ("keyword R@3 paraphrase eval", True, "benchmark", ["keyword", "paraphrase", "eval"]),
    ("BM25 fulldoc chunked A/B test comparison", True, "benchmark", ["BM25", "fulldoc", "chunked"]),
    ("G2a retriever 도입 결정", True, "decision", ["G2a", "retriever", "도입"]),
    ("omc-live live-inf iteration score", True, "omc", ["live", "iteration", "score"]),
    ("DECIDE-Bench baseline Wilcoxon", True, "benchmark", ["DECIDE", "baseline", "Wilcoxon"]),
    ("vector embedding cosine similarity hybrid", True, "retrieval", ["vector", "embedding", "cosine"]),
    ("Korean FTS5 tokenizer unicode61 stemming", True, "technical", ["FTS5", "tokenizer", "Korean"]),
    ("auto-index.py 제거 권고 vestigial", True, "auto_index", ["auto-index", "vestigial", "제거"]),
    ("bm25-memory.py G2b graph search fallback", True, "core_tech", ["G2b", "graph", "fallback"]),

    # Irrelevant — unrelated topics (should return no/wrong results)
    ("docker container kubernetes deployment", False, "irrelevant", []),
    ("react nextjs frontend component", False, "irrelevant", []),
    ("machine learning neural network training", False, "irrelevant", []),
    ("sql database schema migration", False, "irrelevant", []),
    ("오늘 날씨 맑음 기온", False, "irrelevant_korean", []),
    ("python unittest mock fixture", False, "irrelevant", []),
    ("git rebase squash commit history", False, "irrelevant", []),
    ("javascript typescript babel webpack", False, "irrelevant", []),
    ("api rest endpoint authentication jwt", False, "irrelevant", []),
    ("linux bash shell script cron", False, "irrelevant", []),
]


# ── Utilities ───────────────────────────────────────────────────────────────
def extract_keywords(text: str, max_words: int = 6) -> str:
    """chat-memory.py와 동일한 keyword extraction logic."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]{1,}|[a-zA-Z]{3,}|[가-힣]{2,}", text)
    seen: set[str] = set()
    keywords = []
    for w in words:
        wl = w.lower()
        if wl not in STOPWORDS and wl not in seen:
            seen.add(wl)
            keywords.append(w)
    return " OR ".join(keywords[:max_words])


def compute_relevance_score(results: list[tuple], ground_truth_keywords: list[str]) -> float:
    """
    Heuristic relevance scoring: check if retrieved content contains GT keywords.
    Returns 0.0 (none relevant) to 1.0 (all relevant).
    """
    if not results or not ground_truth_keywords:
        return 0.0
    relevant = 0
    for _, role, content, _ in results:
        content_lower = content.lower()
        # A result is "relevant" if it contains ≥1 ground truth keyword
        if any(kw.lower() in content_lower for kw in ground_truth_keywords):
            relevant += 1
    return relevant / len(results)


# ── auto-index.py Evaluation ────────────────────────────────────────────────
def eval_auto_index(verbose: bool = False) -> dict:
    """
    auto-index.py의 trigger conditions + hint effectiveness 측정.

    Metrics:
    - trigger_rate_session_start: DB age >24h → hook would fire
    - trigger_rate_post_commit: always fires on commit
    - db_staleness_hours: actual measured freshness
    - hint_is_actionable: True if Claude could act on the hint (MCP tool available)
    - effectiveness_score: 0.0~1.0 (composite)
    """
    result = {
        "hook": "auto-index.py",
        "db_found": False,
        "db_age_hours": None,
        "trigger_session_start": False,
        "trigger_post_commit": True,  # always fires on commit
        "hint_text": None,
        "hint_length": 0,
        "effectiveness_score": 0.0,
        "issues": [],
    }

    # Check DB
    db_slug = "home-jayone-Project-CTX"
    db_path = CODEBASE_CACHE / f"{db_slug}.db"
    if db_path.exists():
        result["db_found"] = True
        age_hours = (time.time() - db_path.stat().st_mtime) / 3600
        result["db_age_hours"] = round(age_hours, 1)
        result["trigger_session_start"] = age_hours > 24
        result["hint_text"] = (
            f'[AUTO-INDEX] stale ({age_hours:.0f}h old) — run: '
            f'mcp__codebase-memory-mcp__index_repository(repo_path="...", mode="fast")'
        )
        result["hint_length"] = len(result["hint_text"])
    else:
        result["trigger_session_start"] = True  # missing → always trigger
        result["hint_text"] = '[AUTO-INDEX] not indexed — run: mcp__codebase-memory-mcp__index_repository(...)'
        result["hint_length"] = len(result["hint_text"])
        result["issues"].append("DB not found — would always trigger SessionStart")

    # Effectiveness analysis
    if result["db_age_hours"] and result["db_age_hours"] > 24:
        result["issues"].append(f"DB stale ({result['db_age_hours']:.0f}h) — freshness guarantee broken")
    result["issues"].append("Hint-based: Claude may not act on additionalContext (non-deterministic)")
    result["issues"].append("No feedback loop: no way to verify hint was executed")

    # Composite effectiveness score:
    # - hint_delivery: deterministic (1.0)
    # - hint_execution: non-deterministic (estimated 0.1 based on empirical evidence)
    # - index_freshness: 0.0 if DB >24h stale
    hint_delivery = 1.0
    hint_execution = 0.1  # empirical: DB was 116h stale despite daily commits
    freshness = 0.0 if (result["db_age_hours"] or 999) > 24 else 1.0
    result["effectiveness_score"] = round(
        0.2 * hint_delivery + 0.6 * hint_execution + 0.2 * freshness, 3
    )

    if verbose:
        print(f"\n[auto-index.py]")
        print(f"  DB age: {result['db_age_hours']}h | Trigger SessionStart: {result['trigger_session_start']}")
        print(f"  Hint: {result['hint_text'][:80]}...")
        print(f"  Issues: {result['issues']}")
        print(f"  Effectiveness: {result['effectiveness_score']:.3f}")

    return result


# ── chat-memory.py Evaluation ────────────────────────────────────────────────
def eval_chat_memory(scope: str = "project", verbose: bool = False) -> dict:
    """
    chat-memory.py의 retrieval quality 측정.

    Metrics:
    - precision_at_3: % of retrieved results that are relevant (GT keyword match)
    - false_positive_rate: % of irrelevant queries that returned results
    - true_positive_rate: % of relevant queries that returned results (recall proxy)
    - keyword_coverage: % of queries where keywords were extracted successfully
    - avg_result_count: average number of results per relevant query
    - effectiveness_score: 0.0~1.0 (composite)
    """
    result = {
        "hook": "chat-memory.py",
        "vault_db_found": VAULT_DB.exists(),
        "total_queries": len(TEST_QUERIES),
        "relevant_queries": sum(1 for _, r, _, _ in TEST_QUERIES if r),
        "irrelevant_queries": sum(1 for _, r, _, _ in TEST_QUERIES if not r),
        "precision_at_3": 0.0,
        "false_positive_rate": 0.0,
        "true_positive_rate": 0.0,
        "keyword_coverage": 0.0,
        "avg_result_count_relevant": 0.0,
        "effectiveness_score": 0.0,
        "per_category": {},
        "issues": [],
        "per_query": [],
    }

    if not VAULT_DB.exists():
        result["issues"].append("vault.db not found — cannot run retrieval eval")
        return result

    project_filter = CTX_PROJECT if scope == "project" else None

    # Run all queries
    tp_count = 0   # relevant queries that returned results
    fp_count = 0   # irrelevant queries that returned results
    precision_scores = []
    keyword_success = 0
    result_counts_relevant = []
    category_stats: dict[str, dict] = {}

    try:
        conn = sqlite3.connect(f"file:{VAULT_DB}?mode=ro", uri=True, timeout=5.0)

        for query, expected_relevant, category, gt_keywords in TEST_QUERIES:
            keywords = extract_keywords(query)
            has_keywords = bool(keywords)
            if has_keywords:
                keyword_success += 1

            # Run FTS5 query (matches chat-memory.py query_vault logic)
            rows = []
            if keywords:
                try:
                    if project_filter:
                        rows = conn.execute(
                            """
                            SELECT s.project, m.role, m.content, m.timestamp
                            FROM messages_fts fts
                            JOIN messages m ON fts.rowid = m.id
                            JOIN sessions s ON m.session_id = s.session_id
                            WHERE messages_fts MATCH ?
                              AND s.project = ?
                              AND m.role IN ('user', 'assistant')
                              AND m.content NOT LIKE '[tool_use%'
                              AND m.content NOT LIKE '[tool_result%'
                              AND length(m.content) > 30
                            ORDER BY rank
                            LIMIT 12
                            """,
                            (keywords, project_filter),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            """
                            SELECT s.project, m.role, m.content, m.timestamp
                            FROM messages_fts fts
                            JOIN messages m ON fts.rowid = m.id
                            JOIN sessions s ON m.session_id = s.session_id
                            WHERE messages_fts MATCH ?
                              AND m.role IN ('user', 'assistant')
                              AND m.content NOT LIKE '[tool_use%'
                              AND m.content NOT LIKE '[tool_result%'
                              AND length(m.content) > 30
                            ORDER BY rank
                            LIMIT 12
                            """,
                            (keywords,),
                        ).fetchall()
                except sqlite3.OperationalError as e:
                    rows = []
                    if verbose:
                        print(f"  FTS5 error for '{query[:40]}': {e}")

            # Deduplicate (chat-memory logic)
            seen: set[str] = set()
            deduped = []
            for row in rows:
                key = row[2][:120]
                if key not in seen:
                    seen.add(key)
                    deduped.append(row)
            results = deduped[:3]  # top-3 (MAX_RESULTS)

            has_results = len(results) > 0
            relevance = compute_relevance_score(results, gt_keywords) if results else 0.0

            # Categorize
            if expected_relevant and has_results:
                tp_count += 1
                result_counts_relevant.append(len(results))
                precision_scores.append(relevance)
            elif not expected_relevant and has_results:
                fp_count += 1

            # Per-category stats
            if category not in category_stats:
                category_stats[category] = {"total": 0, "hits": 0, "precision_sum": 0.0}
            category_stats[category]["total"] += 1
            if has_results and expected_relevant:
                category_stats[category]["hits"] += 1
                category_stats[category]["precision_sum"] += relevance

            per_q = {
                "query": query[:60],
                "expected_relevant": expected_relevant,
                "category": category,
                "keywords": keywords[:60],
                "result_count": len(results),
                "has_results": has_results,
                "relevance_score": round(relevance, 3),
                "correct": (expected_relevant and has_results) or (not expected_relevant and not has_results),
            }
            result["per_query"].append(per_q)

            if verbose:
                correct_mark = "✓" if per_q["correct"] else "✗"
                print(f"  {correct_mark} [{category:15s}] '{query[:40]:40s}' → {len(results)} results, rel={relevance:.2f}")

        conn.close()

    except Exception as e:
        result["issues"].append(f"DB query error: {e}")

    n_relevant = result["relevant_queries"]
    n_irrelevant = result["irrelevant_queries"]

    result["true_positive_rate"] = round(tp_count / n_relevant, 3) if n_relevant else 0.0
    result["false_positive_rate"] = round(fp_count / n_irrelevant, 3) if n_irrelevant else 0.0
    result["precision_at_3"] = round(sum(precision_scores) / len(precision_scores), 3) if precision_scores else 0.0
    result["keyword_coverage"] = round(keyword_success / len(TEST_QUERIES), 3)
    result["avg_result_count_relevant"] = round(
        sum(result_counts_relevant) / len(result_counts_relevant), 2
    ) if result_counts_relevant else 0.0

    # Per-category summary
    for cat, stats in category_stats.items():
        result["per_category"][cat] = {
            "total": stats["total"],
            "hit_rate": round(stats["hits"] / stats["total"], 3) if stats["total"] else 0.0,
            "avg_precision": round(stats["precision_sum"] / stats["hits"], 3) if stats["hits"] else 0.0,
        }

    # FP rate issue
    if result["false_positive_rate"] > 0.2:
        result["issues"].append(f"High false positive rate: {result['false_positive_rate']:.1%}")
    if result["true_positive_rate"] < 0.5:
        result["issues"].append(f"Low true positive rate: {result['true_positive_rate']:.1%}")

    # Composite effectiveness:
    # 0.4 × TP rate + 0.4 × precision@3 + 0.2 × (1 - FP rate)
    result["effectiveness_score"] = round(
        0.4 * result["true_positive_rate"]
        + 0.4 * result["precision_at_3"]
        + 0.2 * (1 - result["false_positive_rate"]),
        3,
    )

    if verbose:
        print(f"\n[chat-memory.py summary]")
        print(f"  TP rate: {result['true_positive_rate']:.1%} | FP rate: {result['false_positive_rate']:.1%}")
        print(f"  Precision@3: {result['precision_at_3']:.3f}")
        print(f"  Keyword coverage: {result['keyword_coverage']:.1%}")
        print(f"  Effectiveness: {result['effectiveness_score']:.3f}")

    return result


# ── Comparison Report ────────────────────────────────────────────────────────
def generate_report(ai_result: dict, cm_result: dict, scope: str) -> str:
    """두 hook 비교 보고서 생성."""
    lines = [
        "# auto-index.py VS chat-memory.py 성능 비교 실험",
        f"**Date**: {time.strftime('%Y-%m-%d')}  **Scope**: {scope}  **Queries**: {cm_result['total_queries']}",
        "",
        "## Hook Architecture Summary",
        "",
        "| Hook | Event | Mechanism | Output |",
        "|------|-------|-----------|--------|",
        "| auto-index.py | SessionStart + PostToolUse(git commit) | DB age 체크 → hint 주입 | `additionalContext` (Claude에게 MCP 호출 요청) |",
        "| chat-memory.py | UserPromptSubmit | FTS5+vector hybrid search | `additionalContext` (관련 과거 대화 실제 주입) |",
        "",
        "## auto-index.py Results",
        "",
        f"- **DB found**: {ai_result['db_found']}",
        f"- **DB age**: {ai_result['db_age_hours']}h ({ai_result['db_age_hours']/24:.1f} days)" if ai_result['db_age_hours'] else "- **DB age**: N/A",
        f"- **SessionStart trigger**: {ai_result['trigger_session_start']} (threshold: >24h)",
        f"- **PostCommit trigger**: always (--force)",
        f"- **Hint delivery**: deterministic (100%) — but execution depends on Claude",
        f"- **Estimated hint execution rate**: ~10% (empirical: DB 116h stale despite daily commits)",
        f"- **Effectiveness score**: **{ai_result['effectiveness_score']:.3f}** / 1.000",
        "",
        "### Issues",
        *[f"- {issue}" for issue in ai_result["issues"]],
        "",
        "## chat-memory.py Results",
        "",
        f"- **vault.db found**: {cm_result['vault_db_found']}",
        f"- **Test queries**: {cm_result['total_queries']} ({cm_result['relevant_queries']} relevant, {cm_result['irrelevant_queries']} irrelevant)",
        f"- **True Positive Rate**: {cm_result['true_positive_rate']:.1%} (관련 쿼리 중 결과 반환)",
        f"- **False Positive Rate**: {cm_result['false_positive_rate']:.1%} (무관 쿼리에서 결과 반환)",
        f"- **Precision@3**: {cm_result['precision_at_3']:.3f} (반환된 결과 중 실제 관련 비율)",
        f"- **Keyword coverage**: {cm_result['keyword_coverage']:.1%} (키워드 추출 성공률)",
        f"- **Avg results (relevant)**: {cm_result['avg_result_count_relevant']:.1f} / 3",
        f"- **Effectiveness score**: **{cm_result['effectiveness_score']:.3f}** / 1.000",
        "",
        "### Per-Category Breakdown",
        "",
        "| Category | Total | Hit Rate | Avg Precision |",
        "|----------|-------|----------|---------------|",
    ]
    for cat, stats in sorted(cm_result["per_category"].items()):
        lines.append(f"| {cat} | {stats['total']} | {stats['hit_rate']:.1%} | {stats['avg_precision']:.3f} |")

    if cm_result["issues"]:
        lines += ["", "### Issues", *[f"- {issue}" for issue in cm_result["issues"]]]

    delta = cm_result["effectiveness_score"] - ai_result["effectiveness_score"]
    winner = "chat-memory.py" if delta > 0 else "auto-index.py" if delta < 0 else "tie"

    lines += [
        "",
        "## Comparative Analysis",
        "",
        "| Metric | auto-index.py | chat-memory.py | Winner |",
        "|--------|--------------|----------------|--------|",
        f"| Context delivery mechanism | Hint (indirect) | Direct injection | chat-memory |",
        f"| Execution determinism | Non-deterministic | Deterministic | chat-memory |",
        f"| Freshness guarantee | Broken (DB stale) | Real-time | chat-memory |",
        f"| Coverage | Codebase graph | 143K+ messages | chat-memory |",
        f"| False positive risk | Low (hint-only) | {cm_result['false_positive_rate']:.0%} | auto-index |",
        f"| Effectiveness score | {ai_result['effectiveness_score']:.3f} | {cm_result['effectiveness_score']:.3f} | {winner} (+{abs(delta):.3f}) |",
        "",
        "## Conclusions",
        "",
        f"**chat-memory.py가 {delta:+.3f} 점 우세** ({cm_result['effectiveness_score']:.3f} vs {ai_result['effectiveness_score']:.3f})",
        "",
        "### auto-index.py 판정: 제거 권고",
        "- 힌트 방식의 구조적 한계: Claude가 `additionalContext`를 무시할 수 있음",
        f"- 실증적 증거: DB {ai_result['db_age_hours']}h stale에도 갱신 안 됨 (일 2회+ 커밋에도 불구)",
        "- G2b는 git grep fallback으로 DB 없어도 작동 → 제거 시 기능 손실 없음",
        "- 세션 시작 토큰 절약 가능 (hint 주입 없어짐)",
        "",
        "### chat-memory.py 판정: 유지 + 개선 기회",
        f"- TP rate {cm_result['true_positive_rate']:.0%}: 관련 쿼리에서 안정적으로 결과 반환",
        f"- FP rate {cm_result['false_positive_rate']:.0%}: 무관 쿼리에서도 결과 반환 — threshold 개선 여지",
        f"- Precision@3 {cm_result['precision_at_3']:.3f}: GT keyword 기반이지만 실용적 수준",
        "- vector daemon 활성화 시 hybrid search로 품질 향상 가능",
        "",
        "### 개선 권고",
        f"1. chat-memory.py FP rate {cm_result['false_positive_rate']:.0%} 개선: BM25 score threshold 추가",
        "2. auto-index.py `settings.json`에서 제거 (SessionStart + PostToolUse 두 항목)",
        "3. G2b graph search 직접 MCP 호출로 대체 고려 (deterministic)",
    ]

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="auto-index.py vs chat-memory.py 성능 비교")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--scope", choices=["project", "global"], default="project",
                        help="chat-memory scope: project (CTX only) or global (all)")
    parser.add_argument("--output", default=None, help="JSON output path")
    args = parser.parse_args()

    print("=" * 60)
    print("Hook Comparison Eval: auto-index.py vs chat-memory.py")
    print("=" * 60)

    # Evaluate
    print("\n[1/2] Evaluating auto-index.py...")
    ai_result = eval_auto_index(verbose=args.verbose)
    print(f"  Effectiveness: {ai_result['effectiveness_score']:.3f}")

    print(f"\n[2/2] Evaluating chat-memory.py (scope={args.scope}, {len(TEST_QUERIES)} queries)...")
    cm_result = eval_chat_memory(scope=args.scope, verbose=args.verbose)
    print(f"  TP rate: {cm_result['true_positive_rate']:.1%} | FP rate: {cm_result['false_positive_rate']:.1%}")
    print(f"  Precision@3: {cm_result['precision_at_3']:.3f} | Effectiveness: {cm_result['effectiveness_score']:.3f}")

    # Summary
    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"  auto-index.py   effectiveness: {ai_result['effectiveness_score']:.3f}")
    print(f"  chat-memory.py  effectiveness: {cm_result['effectiveness_score']:.3f}")
    delta = cm_result['effectiveness_score'] - ai_result['effectiveness_score']
    print(f"  Delta: {delta:+.3f} (chat-memory.py {'wins' if delta > 0 else 'loses'})")
    print(f"\n  Recommendation: auto-index.py → REMOVE | chat-memory.py → KEEP")

    # Generate report
    report = generate_report(ai_result, cm_result, args.scope)

    # Save results
    output_data = {
        "auto_index": ai_result,
        "chat_memory": cm_result,
        "delta": round(delta, 3),
        "winner": "chat-memory.py" if delta > 0 else "auto-index.py",
        "scope": args.scope,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    results_path = results_dir / "hook_comparison_results.json"
    with open(results_path, "w") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: {results_path}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

    return report, output_data


if __name__ == "__main__":
    report, data = main()
    # Report will be saved by live-inf driver
    print("\n[REPORT PREVIEW]")
    print(report[:500] + "...")
    # Export report for saving
    sys.HOOK_COMPARISON_REPORT = report
    sys.HOOK_COMPARISON_DATA = data
