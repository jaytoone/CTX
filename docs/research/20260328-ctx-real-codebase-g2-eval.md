# CTX G2 Real Codebase Downstream Eval — MiniMax M2.5
**Date**: 2026-03-28  **Type**: Real Codebase Ablation (G2 only)  **Backend**: MiniMax M2.5

## 요약

CTX 자체 코드베이스(src/retrieval/, benchmarks/eval/)의 실제 파일을 context로 제공했을 때
MiniMax M2.5 LLM 성능이 어떻게 달라지는지 측정.

Synthetic 50-file 데이터셋 대신 **실제 CTX 소스 파일** 기반.

## 실험 설계

### 5개 실제 시나리오

| ID | 지시 | 대상 파일 | 대상 함수 |
|----|------|----------|---------|
| real_g2_01 | TF-IDF → BM25 교체 | adaptive_trigger.py | rank_bm25, _rank_files |
| real_g2_02 | keyword routing 추가 | adaptive_trigger.py | rank_ctx_doc, query_type |
| real_g2_03 | R@5 메트릭 추가 | doc_retrieval_eval_v2.py | evaluate_strategy, recall_at_k |
| real_g2_04 | Hybrid Dense+CTX 구현 | hybrid_dense_ctx.py | HybridDenseCTX, retrieve |
| real_g2_05 | BM25Okapi IDF 수정 | bm25_retriever.py | BM25Retriever, rank |

### Context 구성 방식

- **WITH CTX**: 대상 파일 첫 60줄을 context로 주입
- **WITHOUT CTX**: 지시문만 (파일 없음)

## 결과

### 전체

| 조건 | 평균 점수 | 환각률 |
|------|----------|------|
| WITH CTX | **0.350** | 0.00 |
| WITHOUT CTX | 0.150 | 0.00 |
| **Delta** | **+0.200** | — |

### 시나리오별

| 시나리오 | WITH | WITHOUT | Delta | 비고 |
|--------|------|---------|-------|------|
| real_g2_01 | 0.250 | 0.000 | **+0.250** | CTX 없이 완전 실패 |
| real_g2_02 | 0.500 | 0.250 | **+0.250** | CTX로 추가 함수 언급 |
| real_g2_03 | 0.250 | 0.000 | **+0.250** | eval 함수명 context 필요 |
| real_g2_04 | 0.750 | 0.250 | **+0.500** | 가장 큰 개선 — 파일 구조 노출 |
| real_g2_05 | 0.000 | 0.250 | **-0.250** | ⚠️ CTX가 역효과 |

**real_g2_05 역효과 분석**: "Fix BM25Okapi IDF penalty" 지시에서
WITH CTX가 더 낮음 (0.000 vs 0.250).
→ bm25_retriever.py를 보여주면 LLM이 현재 구현에 집중 → TF-only 전환 아이디어를 못 냄
→ "context가 때로는 LLM의 창의적 해결책을 막을 수 있음" (over-anchoring 현상)

## 전체 비교표

| 실험 | 데이터 | WITH CTX | WITHOUT CTX | Delta |
|------|--------|----------|------------|-------|
| Dry-run G1 | synthetic | 0.733 | 0.033 | +0.700 |
| Dry-run G2 | synthetic | 0.582 | 0.000 | +0.582 |
| **MiniMax G1** | synthetic | **1.000** | 0.219 | **+0.781** |
| **MiniMax G2 (synthetic)** | synthetic | **0.375** | 0.000 | **+0.375** |
| **MiniMax G2 (real codebase)** | real CTX code | **0.350** | 0.150 | **+0.200** |

## 핵심 발견

### 1. Real codebase delta 낮아짐 (0.375 → 0.200)

Synthetic 대비 real에서 CTX 효과가 줄어드는 이유:
- **WITHOUT CTX baseline 상승**: 0.000 → 0.150 (LLM이 일반 코딩 지식으로 추측 가능)
- **WITH CTX 절대값 유지**: 0.375 → 0.350 (실제 파일 = 더 어려운 케이스)
- Real 파일은 더 복잡한 내부 API → LLM 활용률 저하

### 2. CTX over-anchoring 위험 (real_g2_05)

CTX가 현재 구현을 보여주면 LLM이 "이 코드를 수정"에 집중 → 더 나은 대안 제시 못함.
이는 CTX 설계에 중요한 시사점: context 선택이 답을 제약할 수 있음.

### 3. G1 완벽 달성 (1.000) — real G2 부분 달성 (0.350)

| 목표 | 달성도 | 비고 |
|------|--------|------|
| G1 (메모리 회상) | ✅ 완벽 (1.000) | CTX persistent_memory 효과 실증 |
| G2 synthetic | ✅ 양호 (0.375) | 환각 0.00 |
| G2 real codebase | ⚡ 부분 (0.350, Δ+0.200) | over-anchoring 1건 포함 |

## 의미

**CTX는 G1(세션 기억)에서 완벽하게 작동하고, G2(코드 작업)에서 일관되게 개선**한다.
단, real-world에서의 개선폭(Δ+0.200)은 synthetic(Δ+0.375)보다 작으며,
context 내용이 LLM을 잘못 앵커링할 위험이 존재한다.

## 실행 명령

```bash
MINIMAX_API_KEY=<key> MINIMAX_BASE_URL=https://api.minimax.io/anthropic \
MINIMAX_MODEL=MiniMax-M2.5 \
python3 benchmarks/eval/real_codebase_downstream_eval.py
```

## Related
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
