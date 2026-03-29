#!/usr/bin/env python3
"""
CTX Hook Improvement — Before/After Benchmark
==============================================
이번 세션 변경사항 정량 측정:
  1. classify_intent: frozenset 키워드 → regex 동사어미 앵커링
  2. 훅 intent 출력: CAUTION/REFERENCE 헤더 → LLM 위임
  3. session bleeding 수정: cwd 필터 추가

측정 항목:
  - Intent 분류 정확도 (TP율 / FP율)
  - 변경 전 FP 케이스 7개에 대한 before/after
  - 지연시간 (μs per call)
"""
import re
import sys
import time
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.trigger.trigger_classifier import TriggerClassifier


# ─── BEFORE: Original frozenset-based classify_intent ────────────────────────

class TriggerClassifierBefore:
    """
    세션 이전 버전 — English + Korean 혼합 frozenset 키워드 기반.
    동사어미 앵커링 없음: 명사 컨텍스트에서 FP 발생.
    """
    _MODIFY_KEYWORDS = frozenset({
        # English
        "fix", "change", "update", "replace", "refactor", "rewrite",
        "correct", "improve", "modify", "rename", "move", "delete",
        "remove", "edit", "patch", "repair", "convert", "migrate",
        # Korean — verb-ending 없이 명사만으로 매칭 (FP 원인)
        "수정", "변경", "개선", "삭제", "제거", "이동", "교체",
        "고쳐", "바꿔", "리팩토링",
    })
    _CREATE_KEYWORDS = frozenset({
        # English
        "create", "implement", "write", "add new", "generate", "make",
        "build", "new function", "new class", "new method",
        # Korean — verb-ending 없이 명사만으로 매칭 (FP 원인)
        "만들어", "작성", "구현", "생성", "추가",
    })

    def classify_intent(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if any(kw in prompt_lower for kw in self._MODIFY_KEYWORDS):
            return "modify"
        if any(kw in prompt_lower for kw in self._CREATE_KEYWORDS):
            return "create"
        return "read"


# ─── Test Corpus ─────────────────────────────────────────────────────────────

@dataclass
class TestCase:
    prompt: str
    expected: str
    category: str
    description: str


# Ground truth test cases (40 cases from test_trigger_classifier_ko.py)
TEST_CASES: List[TestCase] = [
    # Korean MODIFY (TP cases)
    TestCase("이 함수 수정해줘", "modify", "ko_modify", "수정+해줘"),
    TestCase("retrieve 함수 수정", "modify", "ko_modify", "EOS implicit imperative"),
    TestCase("이 코드 고쳐줘", "modify", "ko_modify", "고쳐줘"),
    TestCase("변경해서 재실행해", "modify", "ko_modify", "변경+해서"),
    TestCase("로직 바꿔줘", "modify", "ko_modify", "바꿔줘"),
    TestCase("전체 리팩토링 해줘", "modify", "ko_modify", "리팩토링+해줘"),
    TestCase("성능 개선해줘", "modify", "ko_modify", "개선+해줘"),
    TestCase("이 코드 삭제해줘", "modify", "ko_modify", "삭제+해줘"),
    TestCase("중복 코드 제거해줘", "modify", "ko_modify", "제거+해줘"),
    TestCase("retrieve 함수의 버그를 수정해줘", "modify", "ko_modify", "버그 수정+해줘"),

    # Korean CREATE (TP cases)
    TestCase("새로운 함수 만들어줘", "create", "ko_create", "만들어줘"),
    TestCase("클래스 만들어", "create", "ko_create", "EOS 만들어"),
    TestCase("테스트 코드 작성해줘", "create", "ko_create", "작성+해줘"),
    TestCase("BFS 알고리즘 구현해줘", "create", "ko_create", "구현+해줘"),
    TestCase("구현해줘", "create", "ko_create", "구현만"),
    TestCase("새 파일 생성해줘", "create", "ko_create", "생성+해줘"),
    TestCase("기능 추가해줘", "create", "ko_create", "추가+해줘"),
    TestCase("새로운 retriever 클래스 만들어줘", "create", "ko_create", "만들어줘"),

    # Korean READ (TP cases)
    TestCase("어떻게 동작하는지 설명해줘", "read", "ko_read", "설명해줘"),
    TestCase("이 코드 분석해줘", "read", "ko_read", "분석해줘"),
    TestCase("AdaptiveTriggerRetriever 어떻게 사용해?", "read", "ko_read", "어떻게"),
    TestCase("classify 함수 보여줘", "read", "ko_read", "보여줘"),
    TestCase("BM25L이 뭐야", "read", "ko_read", "뭐야"),

    # English regression
    TestCase("fix the bug in retrieve", "modify", "en_modify", "fix"),
    TestCase("update the threshold value", "modify", "en_modify", "update"),
    TestCase("refactor this module", "modify", "en_modify", "refactor"),
    TestCase("create a new retriever class", "create", "en_create", "create"),
    TestCase("implement BFS traversal", "create", "en_create", "implement"),
    TestCase("how does this function work", "read", "en_read", "how does"),
    TestCase("explain the scoring logic", "read", "en_read", "explain"),

    # Mixed language
    TestCase("retrieve function 수정해줘", "modify", "mixed", "ko_verb+en_noun"),
    TestCase("fix 해줘 이 버그", "modify", "mixed", "en_fix+ko_verb"),
    TestCase("BM25 retriever 만들어줘", "create", "mixed", "ko_create+en_noun"),

    # FALSE POSITIVE PREVENTION (핵심 — 7 cases)
    TestCase("추가 설명해줘", "read", "fp_prevent", "추가=명사 (additional)"),
    TestCase("추가로 어떻게 동작해?", "read", "fp_prevent", "추가로=부사"),
    TestCase("수정 없이 그냥 실행해", "read", "fp_prevent", "수정=명사 (without modification)"),
    TestCase("만들어진 과정 설명해줘", "read", "fp_prevent", "만들어진=수동 (was made)"),
    TestCase("생성 시점이 언제야?", "read", "fp_prevent", "생성=명사 (creation time)"),
    TestCase("삭제된 이유가 뭐야?", "read", "fp_prevent", "삭제된=과거수동 (was deleted)"),
    TestCase("새로운 기능이 뭔지 알려줘", "read", "fp_prevent", "새로운=형용사 (adj)"),
]


def run_benchmark() -> dict:
    before_clf = TriggerClassifierBefore()
    after_clf = TriggerClassifier()

    results = {
        "before": {"correct": 0, "wrong": 0, "fp": 0, "fn": 0, "details": []},
        "after":  {"correct": 0, "wrong": 0, "fp": 0, "fn": 0, "details": []},
    }

    # Latency measurement
    N_LATENCY = 1000
    t0 = time.perf_counter()
    for _ in range(N_LATENCY):
        for tc in TEST_CASES:
            before_clf.classify_intent(tc.prompt)
    before_total_us = (time.perf_counter() - t0) * 1e6
    before_per_call_us = before_total_us / (N_LATENCY * len(TEST_CASES))

    t0 = time.perf_counter()
    for _ in range(N_LATENCY):
        for tc in TEST_CASES:
            after_clf.classify_intent(tc.prompt)
    after_total_us = (time.perf_counter() - t0) * 1e6
    after_per_call_us = after_total_us / (N_LATENCY * len(TEST_CASES))

    # Accuracy per case
    fp_cases_before = []
    fp_cases_after = []

    for tc in TEST_CASES:
        b_pred = before_clf.classify_intent(tc.prompt)
        a_pred = after_clf.classify_intent(tc.prompt)

        b_correct = b_pred == tc.expected
        a_correct = a_pred == tc.expected

        if b_correct:
            results["before"]["correct"] += 1
        else:
            results["before"]["wrong"] += 1
            if tc.category == "fp_prevent":
                fp_cases_before.append({
                    "prompt": tc.prompt,
                    "expected": tc.expected,
                    "got": b_pred,
                    "desc": tc.description,
                })

        if a_correct:
            results["after"]["correct"] += 1
        else:
            results["after"]["wrong"] += 1
            if tc.category == "fp_prevent":
                fp_cases_after.append({
                    "prompt": tc.prompt,
                    "expected": tc.expected,
                    "got": a_pred,
                    "desc": tc.description,
                })

        results["before"]["details"].append({
            "prompt": tc.prompt,
            "category": tc.category,
            "expected": tc.expected,
            "got": b_pred,
            "correct": b_correct,
        })
        results["after"]["details"].append({
            "prompt": tc.prompt,
            "category": tc.category,
            "expected": tc.expected,
            "got": a_pred,
            "correct": a_correct,
        })

    # FP rate specifically for fp_prevent category
    fp_total = sum(1 for tc in TEST_CASES if tc.category == "fp_prevent")
    results["before"]["fp_prevent_count"] = fp_total
    results["before"]["fp_count"] = len(fp_cases_before)
    results["before"]["fp_rate"] = len(fp_cases_before) / fp_total
    results["after"]["fp_prevent_count"] = fp_total
    results["after"]["fp_count"] = len(fp_cases_after)
    results["after"]["fp_rate"] = len(fp_cases_after) / fp_total

    # TP rate for actual intent cases (non-FP-prevent categories)
    tp_cases = [tc for tc in TEST_CASES if tc.category != "fp_prevent"]
    tp_total = len(tp_cases)
    results["before"]["tp_total"] = tp_total
    results["after"]["tp_total"] = tp_total

    b_tp = sum(1 for tc in tp_cases
               if before_clf.classify_intent(tc.prompt) == tc.expected)
    a_tp = sum(1 for tc in tp_cases
               if after_clf.classify_intent(tc.prompt) == tc.expected)

    results["before"]["tp_count"] = b_tp
    results["before"]["tp_rate"] = b_tp / tp_total
    results["after"]["tp_count"] = a_tp
    results["after"]["tp_rate"] = a_tp / tp_total

    # Overall accuracy
    total = len(TEST_CASES)
    results["before"]["accuracy"] = results["before"]["correct"] / total
    results["after"]["accuracy"] = results["after"]["correct"] / total
    results["total_cases"] = total

    # Latency
    results["latency_us"] = {
        "before_per_call": round(before_per_call_us, 3),
        "after_per_call": round(after_per_call_us, 3),
        "overhead_us": round(after_per_call_us - before_per_call_us, 3),
    }

    results["fp_cases_before"] = fp_cases_before
    results["fp_cases_after"] = fp_cases_after

    # Category breakdown
    categories = sorted(set(tc.category for tc in TEST_CASES))
    results["category_breakdown"] = {}
    for cat in categories:
        cat_cases = [tc for tc in TEST_CASES if tc.category == cat]
        b_correct_cat = sum(
            1 for tc in cat_cases
            if before_clf.classify_intent(tc.prompt) == tc.expected
        )
        a_correct_cat = sum(
            1 for tc in cat_cases
            if after_clf.classify_intent(tc.prompt) == tc.expected
        )
        results["category_breakdown"][cat] = {
            "total": len(cat_cases),
            "before_correct": b_correct_cat,
            "after_correct": a_correct_cat,
            "before_acc": b_correct_cat / len(cat_cases),
            "after_acc": a_correct_cat / len(cat_cases),
        }

    return results


def print_report(r: dict):
    print("\n" + "=" * 70)
    print("CTX Hook Improvement — Before/After Benchmark Report")
    print("=" * 70)

    b = r["before"]
    a = r["after"]
    total = r["total_cases"]

    print(f"\n[Overall Accuracy] ({total} test cases)")
    print(f"  Before: {b['correct']}/{total} = {b['accuracy']:.1%}")
    print(f"  After:  {a['correct']}/{total} = {a['accuracy']:.1%}")
    print(f"  Delta:  {(a['accuracy'] - b['accuracy']) * 100:+.1f}pp")

    print(f"\n[False Positive Rate] ({b['fp_prevent_count']} noun-context cases)")
    print(f"  Before FP: {b['fp_count']}/{b['fp_prevent_count']} = {b['fp_rate']:.1%}")
    print(f"  After  FP: {a['fp_count']}/{a['fp_prevent_count']} = {a['fp_rate']:.1%}")
    delta_fp = (a['fp_rate'] - b['fp_rate']) * 100
    print(f"  Delta:  {delta_fp:+.1f}pp  ({'IMPROVED' if delta_fp < 0 else 'DEGRADED' if delta_fp > 0 else 'NO CHANGE'})")

    print(f"\n[True Positive Rate] ({b['tp_total']} intent cases excl. FP-prevent)")
    print(f"  Before TP: {b['tp_count']}/{b['tp_total']} = {b['tp_rate']:.1%}")
    print(f"  After  TP: {a['tp_count']}/{a['tp_total']} = {a['tp_rate']:.1%}")
    delta_tp = (a['tp_rate'] - b['tp_rate']) * 100
    print(f"  Delta:  {delta_tp:+.1f}pp  ({'MAINTAINED/IMPROVED' if delta_tp >= 0 else 'DEGRADED'})")

    print(f"\n[Latency] (avg per classify_intent call)")
    lat = r["latency_us"]
    print(f"  Before: {lat['before_per_call']:.3f} μs/call")
    print(f"  After:  {lat['after_per_call']:.3f} μs/call")
    print(f"  Overhead: {lat['overhead_us']:+.3f} μs  (regex vs frozenset)")

    print(f"\n[Category Breakdown]")
    print(f"  {'Category':<20} {'Before':>8} {'After':>8} {'Total':>6}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*6}")
    for cat, v in r["category_breakdown"].items():
        print(f"  {cat:<20} {v['before_acc']:>7.1%} {v['after_acc']:>7.1%} {v['total']:>6}")

    if r["fp_cases_before"]:
        print(f"\n[Before FP Cases — should be 'read' but misclassified]")
        for c in r["fp_cases_before"]:
            print(f"  ✗ '{c['prompt']}' → got={c['got']} ({c['desc']})")
    else:
        print(f"\n[Before FP Cases] none (before already perfect?)")

    if r["fp_cases_after"]:
        print(f"\n[After FP Cases — regressions]")
        for c in r["fp_cases_after"]:
            print(f"  ✗ '{c['prompt']}' → got={c['got']} ({c['desc']})")
    else:
        print(f"\n[After FP Cases] 0 — all noun-context cases correctly classified as 'read' ✓")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    results = run_benchmark()
    print_report(results)

    # Save raw JSON
    out_path = Path(__file__).parent / "benchmark_results.json"
    with open(out_path, "w") as f:
        # Remove details from JSON output (large)
        compact = {k: v for k, v in results.items() if k not in ("before", "after")}
        compact["before_summary"] = {k: v for k, v in results["before"].items() if k != "details"}
        compact["after_summary"] = {k: v for k, v in results["after"].items() if k != "details"}
        json.dump(compact, f, indent=2, ensure_ascii=False)
    print(f"\nJSON saved → {out_path}")
