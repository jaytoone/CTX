# CTX Real-Project Self-Evaluation: Instruction-Query Failure Analysis
**Date**: 2026-03-27  **Type**: Empirical Validation

## Summary

CTX proxy 메트릭(R@3=0.862)이 실제 코드베이스 instruction-style query에서 완전히 실패하는 것을 실증.
**"자신의 코드베이스도 못 찾는다"** = downstream LLM eval 필요성의 가장 강력한 증거.

## 배경

CTX benchmarks/eval/doc_retrieval_eval_v2.py 에서 R@3=0.862 달성 후 의문:
> "이 proxy 수치가 실제 LLM 코드 작업 품질과 얼마나 상관있나?"

CTX 자체 코드베이스에 대해 instruction-style query를 던져 검증.

## 실험 설정

```python
# CTX 프로젝트 루트에서 직접 실행
from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

ROOT = Path("/home/jayone/Project/CTX")
retriever = AdaptiveTriggerRetriever(str(ROOT))

SCENARIOS = [
    {
        "id": "real_g2_01",
        "query": "Replace TF-IDF with BM25 in the retrieval pipeline",
        "expected_file": "src/retrieval/adaptive_trigger.py",
        "ground_truth_reason": "adaptive_trigger.py contains TF-IDF → BM25 migration code"
    },
    {
        "id": "real_g2_02",
        "query": "Add keyword query type detection to document ranking function",
        "expected_file": "benchmarks/eval/doc_retrieval_eval_v2.py",
        "ground_truth_reason": "doc_retrieval_eval_v2.py contains query_type routing logic"
    },
    {
        "id": "real_g2_03",
        "query": "Fix BM25Okapi IDF penalty on small domain corpus",
        "expected_file": "src/retrieval/adaptive_trigger.py",
        "ground_truth_reason": "adaptive_trigger.py has BM25 implementation to fix"
    },
    {
        "id": "real_g2_04",
        "query": "Implement query-type aware routing for BM25 vs heading match strategy",
        "expected_file": "src/retrieval/adaptive_trigger.py",
        "ground_truth_reason": "routing logic lives in adaptive_trigger.py"
    },
    {
        "id": "real_g2_05",
        "query": "Add R@5 recall metric to document retrieval evaluation script",
        "expected_file": "benchmarks/eval/doc_retrieval_eval_v2.py",
        "ground_truth_reason": "eval script needs R@5 added"
    },
]
```

## 결과

### Strict R@K (exact match in top-K)

| Scenario | Expected File | CTX Returned (top-1) | Match? |
|----------|--------------|---------------------|--------|
| real_g2_01 | adaptive_trigger.py | llamaindex_retriever.py | ❌ |
| real_g2_02 | doc_retrieval_eval_v2.py | doc_retrieval_v1.py | ❌ |
| real_g2_03 | adaptive_trigger.py | bm25_pure.py | ❌ |
| real_g2_04 | adaptive_trigger.py | llamaindex_retriever.py | ❌ |
| real_g2_05 | doc_retrieval_eval_v2.py | metrics_helper.py | ❌ |

**R@5 (strict) = 0.000** — 5/5 시나리오 모두 실패

### Partial Credit (name substring match)

CTX가 관련 파일을 top-5에 포함하는 경우:
- real_g2_03: `bm25_pure.py` (BM25 관련) → partial 0.3
- 나머지: 완전 무관한 파일 반환

**R@5 (partial) = 0.300 / 5 = 0.060**

### Without CTX baseline

LLM이 컨텍스트 없이 파일명을 추측할 때:
- 평균 0.100 (파일명 패턴 추측 성공률)

## 실패 원인 분석

### 1. Trigger Mismatch (가장 큰 원인)

CTX의 `AdaptiveTriggerRetriever`는 다음 트리거로 파일 검색:
- `SEMANTIC_CONCEPT`: 개념 키워드 ("authentication", "database")
- `IMPLICIT_CONTEXT`: 묵시적 컨텍스트 ("이전에 작업한 파일")
- `CROSS_SESSION_MEMORY`: 세션 기억

Instruction-style query ("Replace X with Y in Z")는 어떤 트리거에도 매핑되지 않음.

### 2. Vocabulary Gap

| 쿼리 용어 | CTX 인덱스 용어 | 매칭 실패 이유 |
|-----------|---------------|-------------|
| "retrieval pipeline" | "adaptive_trigger", "rank_bm25" | 추상적 설명 ↔ 구체적 구현 |
| "IDF penalty" | "BM25Okapi", "idf_scores" | 알고리즘 개념 ↔ 코드 구현체 |
| "query-type aware routing" | "query_type == 'keyword'" | 설계 언어 ↔ 코드 패턴 |

### 3. Domain-Specific Benchmark Overfitting

CTX-doc benchmark (R@3=0.862)의 특성:
- 29개 CTX 내부 문서 (대부분 CTX 관련 용어)
- 쿼리가 문서 제목/섹션 기반 → CTX heading match 유리
- **실제 코드베이스 instruction query와 다른 분포**

## CTX Proxy vs Downstream 격차 요약

| 측정 | 지표 | 값 |
|------|------|-----|
| Proxy (CTX-doc benchmark) | R@3 | **0.862** ✅ |
| Real-world (own codebase, instruction) | R@5 | **0.000** ❌ |
| Downstream G2 (dry-run, WITH CTX) | File ref accuracy | **0.582** ✅ |
| Downstream G2 (dry-run, WITHOUT CTX) | File ref accuracy | **0.000** — |

**핵심**: proxy=0.862는 "이상적인 조건에서의 retrieval 정확도". 실제 개발자가 던지는 instruction-style 쿼리에서는 0.000.

## 시사점

### CTX의 실제 포지셔닝

```
CTX는 "무엇을 하라"는 지시보다
"무엇에 대해"라는 개념 기반 쿼리에 최적화됨
```

- ✅ 강점: "auth 관련 파일", "BM25 구현", "context 회상"
- ❌ 약점: "Replace X with Y", "Add Z to function F", instruction-grounded coding

### 개선 방향

1. **Instruction parsing layer**:
   - "Replace A with B in C" → extract {target_concept: A, new_concept: B, scope: C}
   - 이를 CTX의 SEMANTIC_CONCEPT 쿼리로 변환

2. **Hybrid retrieval**:
   - Embedding-based semantic search (sentence-transformers)
   - instruction → embedding → cosine similarity vs file contents

3. **Code structure awareness**:
   - Function/class 이름 인덱싱 (현재 CTX는 파일 단위)
   - "Replace TF-IDF" → grep for TF-IDF occurrences in functions

## 결론

CTX R@3=0.862는 **"CTX 전용 문서에서 CTX 스타일 쿼리"** 에 한정된 수치.
실제 개발자 workflow (instruction-grounded coding)에서는 0.000.

→ **downstream LLM eval이 필수**: proxy 메트릭 개선이 실제 LLM 품질 개선으로 이어지는지 검증 필요.
→ **G2 dry-run 0.582**는 CTX가 ideal 조건에서 제공하는 상한선. 실제는 낮을 가능성.

## Related
- [[projects/CTX/research/20260327-ctx-downstream-eval|20260327-ctx-downstream-eval]]
- [[projects/CTX/research/20260326-ctx-benchmark-validation-roadmap|20260326-ctx-benchmark-validation-roadmap]]
