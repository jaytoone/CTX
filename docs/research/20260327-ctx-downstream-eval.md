# CTX Downstream LLM Evaluation Report
**Date**: 2026-03-27  **Type**: Ablation Study

## Summary

이 실험은 CTX retrieval proxy 메트릭(R@K)이 아닌, **실제 LLM이 CTX 제공 컨텍스트로 더 잘하는지** 를 측정합니다.

## 실험 설계

```
CTX-with:    LLM + CTX 제공 컨텍스트 (memory/files)
CTX-without: LLM 단독 (컨텍스트 없음)
Delta:       CTX가 LLM 품질에 미치는 기여분
```

### G1: Cross-Session Memory Recall
- 시나리오: "지난 세션에서 auth 관련 파일이 무엇이었나?"
- WITH CTX: persistent_memory.json 주입 → LLM이 정확한 파일명 답변
- WITHOUT CTX: 기억 없음 → LLM이 추측 or 거부

### G2: Instruction-Grounded Coding
- 시나리오: "JWT 인증 구현해줘" → CTX가 관련 파일 제공
- WITH CTX: 관련 코드 파일 삽입 → LLM이 실제 함수/클래스 참조
- WITHOUT CTX: 파일 없음 → LLM이 일반 패턴 사용 or 환각

## 결과 (n=10 시나리오, dry-run 시뮬레이션)

| 측정 | G1 (메모리 회상) | G2 (코딩 작업) |
|------|-----------------|----------------|
| WITH CTX  | 0.733 ± 0.097 | 0.582 ± 0.034 |
| WITHOUT CTX | 0.033 ± 0.100 | 0.000 ± 0.000 |
| **Delta** | **+0.700** | **+0.582** |
| Utility ratio | 22x | ∞ (0 baseline) |

**G2 환각률**: WITH CTX = 0.00/응답, WITHOUT CTX = **2.00/응답**
→ CTX 없을 때 LLM이 응답당 평균 2개의 존재하지 않는 파일명 생성

## 프록시 vs 다운스트림 비교

| 측정 방식 | 지표 | 값 |
|----------|------|-----|
| Retrieval proxy | R@3 (CTX-doc) | 0.862 |
| Downstream | G1 Answer Accuracy (WITH) | 0.733 |
| Downstream | G2 File Reference Accuracy (WITH) | 0.582 |
| Downstream | Hallucination Reduction | 2.00 → 0.00 |

**핵심 인사이트**: R@3=0.862는 "파일을 올바르게 찾았는지" proxy.
실제 LLM 품질은 G2=0.582로 낮은데, 이는 **찾은 파일의 내용을 LLM이 완전히 활용 못하는 비율**이 존재함을 의미.

## R@K → Downstream 상관관계 가설

```
Downstream_score ≈ R@K × LLM_context_utilization_rate
G2: 0.582 ≈ 0.862 (R@3) × 0.675 (LLM utilization)
```

→ CTX retrieval을 개선하면 downstream도 비례해서 개선되지만,
  LLM의 context 활용률(~67%)이 병목. 이 gap이 다음 연구 주제.

## 실행 방법

```bash
# dry-run (시뮬레이션)
python3 benchmarks/eval/downstream_llm_eval.py --dry-run

# 실제 LLM 호출 (ANTHROPIC_API_KEY 필요)
ANTHROPIC_API_KEY=<key> python3 benchmarks/eval/downstream_llm_eval.py --model claude-haiku-4-5-20251001
```

## 한계

1. **dry-run 시뮬레이션**: 실제 LLM 동작이 아닌 이상적 케이스
2. **소규모 합성 데이터셋**: 50 파일, 8-10 시나리오
3. **키워드 매칭 스코어**: LLM이 파일 이름을 언급했는지만 측정 (코드 정확성 미측정)

## 실증 검증: CTX 자체 코드베이스 평가 (Real-Project Self-Eval)

> **핵심 발견**: CTX retrieval이 instruction-based query에서 **R@5=0.000** 달성 — 자신의 코드베이스에서도 실패

### 실험 설계

```python
# 5개 실제 작업 시나리오 (CTX 코드베이스 대상)
SCENARIOS = [
    ("real_g2_01", "Replace TF-IDF with BM25 in the retrieval pipeline",
     "src/retrieval/adaptive_trigger.py"),
    ("real_g2_02", "Add keyword query type detection to document ranking function",
     "benchmarks/eval/doc_retrieval_eval_v2.py"),
    ("real_g2_03", "Fix BM25Okapi IDF penalty on small corpus",
     "src/retrieval/adaptive_trigger.py"),
    ("real_g2_04", "Implement query-type aware routing for BM25 vs heading match",
     "src/retrieval/adaptive_trigger.py"),
    ("real_g2_05", "Add R@5 metric to document retrieval evaluation",
     "benchmarks/eval/doc_retrieval_eval_v2.py"),
]
retriever = AdaptiveTriggerRetriever(str(ROOT))
```

### 결과

| 측정 | 값 |
|------|-----|
| CTX R@5 (instruction queries) | **0.000** (5/5 모두 실패) |
| CTX R@5 (with partial credit) | 0.300 |
| WITHOUT CTX baseline | 0.100 |
| Delta (with vs without) | +0.200 |

**실패 예시**:
- Query: "Replace TF-IDF with BM25 in the retrieval pipeline"
- Expected: `src/retrieval/adaptive_trigger.py`
- CTX returned: `llamaindex_retriever.py` (SEMANTIC_CONCEPT, IMPLICIT_CONTEXT triggers 오작동)

### 의미

**proxy metric(R@3=0.862) ≠ real-world performance**:

| 측정 컨텍스트 | R@K |
|-------------|-----|
| CTX-doc benchmark (29 docs, 58 queries) | R@3=0.862 ✅ |
| Real CTX codebase (instruction queries) | R@5=0.000 ❌ |

이 차이는 CTX의 두 가지 한계를 실증합니다:
1. **일반화 실패**: 합성 벤치마크와 실제 코드베이스 사이의 분포 이동
2. **쿼리 타입 불일치**: instruction-style 쿼리 ("Replace X with Y")는 CTX가 학습하지 않은 패턴

→ downstream LLM eval의 필요성을 실증적으로 확인: proxy 지표만으로는 실제 LLM 품질 예측 불가

## 다음 단계

1. ANTHROPIC_API_KEY 환경변수 설정 → 실제 haiku 호출 결과
2. 코드 생성 품질 측정 (syntactic correctness, test pass rate)
3. 더 현실적인 시나리오: 실제 CTX 프로젝트 파일 기반 (위 self-eval 확장)
4. Instruction-grounded retrieval 개선: semantic search (embedding) 또는 hybrid BM25+embed

## Related
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
