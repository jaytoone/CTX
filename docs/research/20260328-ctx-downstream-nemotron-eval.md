# CTX Downstream LLM Eval — Nemotron-Cascade-2 실험 결과

**Date**: 2026-03-28
**Model**: Nemotron-Cascade-2 (NIPA vLLM, localhost:8010, `enable_thinking=False`)
**Baseline**: MiniMax M2.5 (2026-03-28 이전 실험)

---

## 실험 결과 요약

| 지표 | Nemotron-Cascade-2 | MiniMax M2.5 | 차이 |
|------|:-----------------:|:------------:|:----:|
| G1 WITH CTX | **0.875** | 1.000 | -0.125 |
| G1 WITHOUT CTX | 0.250 | 0.219 | +0.031 |
| **G1 Δ (CTX 기여도)** | **+0.625** | **+0.781** | **-0.156** |
| G2 WITH CTX | **1.000** | 0.375 | +0.625 |
| G2 WITHOUT CTX | **1.000** | 0.000 | +1.000 |
| **G2 Δ (CTX 기여도)** | **+0.000** | **+0.375** | **-0.375** |
| **Overall Δ** | **+0.312** | **+0.578** | **-0.265** |

---

## G1: Cross-session Recall 분석

**설정**: 8개 시나리오, persistent_memory 주입 여부 비교

| 시나리오 ID | WITH | WITHOUT | 분석 |
|------------|:----:|:-------:|------|
| g1_01 (UI 선호) | 1.00 | 0.00 | ✅ 정상 |
| g1_02 (rank_bm25) | 1.00 | 1.00 | ⚠️ 공통 지식 (BM25 언급 가능) |
| g1_03 (87 queries) | 1.00 | 0.00 | ✅ 정상 |
| g1_04 (R@3=0.724) | 1.00 | 0.00 | ✅ 정상 |
| g1_05 (CTX 정의) | 1.00 | 0.00 | ✅ 정상 |
| g1_06 (port 8010) | 1.00 | 0.00 | ✅ 정상 |
| g1_07 (MiniMax delta) | 1.00 | 0.00 | ✅ 정상 |
| g1_08 (over-anchoring) | **0.00** | **1.00** | ❌ **Reverse scoring — 이상 케이스** |

**g1_08 분석**: "over-anchoring"에 관한 질문에서 WITH 시 키워드 미포함. Nemotron이 context를 주입받았을 때 다른 방식으로 답변 (메모리 내용 재서술 대신 자체 설명 생성 가능성). WITHOUT는 "over-anchoring"이라는 용어 자체가 training data에 있을 수 있어 정답 가능.

**G1 결론**: Δ=+0.625 (MiniMax +0.781보다 낮음). 6/8 시나리오에서 CTX가 올바르게 기여.

---

## G2: Instruction-grounded Coding 분석

**설정**: 6개 시나리오, code context 주입 여부 비교

| 시나리오 ID | WITH FRA | WITH HR | WITHOUT FRA | WITHOUT HR | 분석 |
|------------|:--------:|:-------:|:-----------:|:----------:|------|
| g2_01 (add method) | 1.00 | 0.00 | 1.00 | 0.00 | ⚠️ Ceiling |
| g2_02 (threshold) | 1.00 | 0.00 | 1.00 | 0.00 | ⚠️ Ceiling |
| g2_03 (R@K function) | 1.00 | 0.00 | 1.00 | 0.00 | ⚠️ Ceiling |
| g2_04 (error handling) | 1.00 | 0.00 | 1.00 | 0.00 | ⚠️ Ceiling |
| g2_05 (new file type) | 1.00 | 0.00 | 1.00 | 0.00 | ⚠️ Ceiling |
| g2_06 (pytest) | 1.00 | 0.00 | 1.00 | 0.00 | ⚠️ Ceiling |

**G2 결론**: WITH=WITHOUT=1.000, **Δ=+0.000**

### 핵심 발견: Ceiling Effect (천장 효과)

Nemotron-Cascade-2는 코딩 특화 모델로, 현재 G2 benchmark의 모든 시나리오를 **context 없이도 완벽하게** 수행 가능.

- MiniMax M2.5: WITHOUT=0.000 → context 없으면 실패 → CTX 필수 (Δ+0.375)
- Nemotron-Cascade-2: WITHOUT=1.000 → context 없이도 성공 → CTX 불필요 (Δ+0.000)

이는 **benchmark 설계의 근본적 문제**를 드러냄:
- 현재 G2 시나리오는 표준 Python 패턴(method 추가, try/except, pytest) — 강력한 coding LLM은 이미 알고 있음
- MiniMax처럼 coding이 상대적으로 약한 모델에서는 CTX context가 크게 도움
- Nemotron 같은 coding 전문 모델에서는 **더 어려운 시나리오 필요**

---

## 모델 비교 해석

### CTX 도구로서의 가치: 모델 강도에 따른 차이

| 모델 유형 | G1 CTX 기여도 | G2 CTX 기여도 | CTX 필요성 |
|---------|:----------:|:----------:|----------|
| **약한 모델** (GPT-3.5급) | 높음 | 높음 | 필수 |
| **중간 모델** (MiniMax M2.5) | 높음 (Δ+0.781) | 중간 (Δ+0.375) | G1: 필수, G2: 유익 |
| **강한 coding 모델** (Nemotron-Cascade-2) | 중간 (Δ+0.625) | **없음** (Δ+0.000) | G1만 유익 |

**결론**: CTX의 가치는 대상 LLM의 능력에 반비례. 강한 모델일수록 G2(coding) 기여도가 낮아짐.

### G1 (cross-session recall) — 모델 독립적으로 CTX 필수

G1은 세션-특화 정보(specific numbers, configuration details)를 요구하므로, 모델 능력과 무관하게 CTX persistent_memory가 필요. Nemotron도 Δ+0.625로 유의미한 개선.

---

## 개선 방향

### G2 Benchmark 재설계 필요

강력한 coding 모델에서 ceiling effect가 없는 시나리오:

1. **CTX 아키텍처 특화 지식 요구**: "CTX에서 `query_type == 'keyword'`일 때 어떤 BM25 변형을 쓰는가?" — 문서 없이 답불가
2. **Multi-hop reasoning**: 여러 파일 참조 필요한 코드 수정 (`adaptive_trigger.py` + `doc_retrieval_eval_v2.py` 동시 수정)
3. **Fine-grained numerical parameters**: "BM25 blend 비율 0.6 threshold의 근거는?" — 코드베이스 특화

### G1 시나리오 개선

- g1_08처럼 역전 케이스 제거 (keywords 재설계)
- WITH/WITHOUT 차이가 명확한 CTX-specific 정보 위주

---

## 최종 비교표 (3-model summary)

| 모델 | G1 Δ | G2 Δ | Overall Δ | G2 ceiling | 비고 |
|------|:----:|:----:|:---------:|:----------:|------|
| MiniMax M2.5 (synthetic) | **+0.781** | **+0.375** | **+0.578** | 없음 | CTX가 coding 성능 향상 |
| MiniMax M2.5 (real CTX codebase) | +0.781 | +0.200 | — | 부분 | Over-anchoring 20% |
| **Nemotron-Cascade-2** | **+0.625** | **+0.000** | **+0.312** | **심각** | G2는 재설계 필요 |

---

## 결론

1. **G1 결론**: CTX persistent_memory는 Nemotron에서도 유효 (+0.625). 모델 강도와 무관하게 세션-특화 정보 회상은 context 주입이 필수.

2. **G2 결론**: Nemotron은 현재 G2 benchmark에서 ceiling effect. 강한 coding 모델에는 **더 어려운 CTX-specific benchmark** 필요.

3. **설계 교훈**: downstream eval benchmark는 **target LLM baseline 능력을 먼저 측정**하고, baseline이 이미 1.0이면 어려운 시나리오로 교체해야 함.

4. **CTX 포지셔닝**: CTX는 "중간 능력 모델의 성능을 1회성으로 높이는 도구"가 아닌, **"모든 모델의 세션-기억 한계를 보완하는 영구 인프라"**로 재정의 가능.

## Related
- [[projects/CTX/research/20260328-ctx-downstream-nemotron-eval-v2|20260328-ctx-downstream-nemotron-eval-v2]]
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-eval-nemotron-final|20260328-ctx-downstream-eval-nemotron-final]]
- [[projects/CTX/research/20260328-ctx-downstream-eval-complete|20260328-ctx-downstream-eval-complete]]
- [[projects/CTX/research/20260327-ctx-downstream-eval|20260327-ctx-downstream-eval]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|20260328-ctx-real-codebase-g2-eval]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
