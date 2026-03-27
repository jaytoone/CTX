# CTX Downstream LLM Evaluation — MiniMax M2.5 실제 실행 결과
**Date**: 2026-03-28  **Type**: Ablation Study (Real LLM Calls)  **Backend**: MiniMax M2.5

## 요약

CTX with/without context ablation을 **MiniMax M2.5 실제 API 호출**로 실행.
이전 dry-run 시뮬레이션 대비 실제 LLM 품질 차이를 측정.

## 실험 조건

```
Backend:  MiniMax M2.5 (Anthropic-compatible API at api.minimax.io/anthropic)
Scenarios: G1=8, G2=6
Dataset:  small (50 synthetic files)
Mode:     Real API calls (no simulation)
```

## 결과

### G1: Cross-Session Memory Recall

| 조건 | 평균 점수 | 표준편차 |
|------|----------|---------|
| WITH CTX | **1.000** | ±0.000 |
| WITHOUT CTX | 0.219 | ±0.131 |
| **Delta** | **+0.781** | 4.57x |

**G1 WITH CTX = 1.000** (완벽): CTX가 persistent_memory를 주입하면 MiniMax M2.5는 모든 과거 파일을 정확히 회상.

**G1 WITHOUT CTX = 0.219** (> dry-run 0.033): MiniMax M2.5가 dry-run 시뮬레이션보다 컨텍스트 없이도 더 잘 추측함. 단, CTX와의 gap은 여전히 크게 존재.

### G2: Instruction-Grounded Coding

| 조건 | 평균 점수 | 표준편차 | 환각률(/응답) |
|------|----------|---------|------------|
| WITH CTX | **0.375** | ±0.185 | **0.00** |
| WITHOUT CTX | 0.000 | ±0.000 | **0.17** |
| **Delta** | **+0.375** | ∞x | 0.17→0.00 |

**G2 WITH CTX = 0.375** (< dry-run 0.582): 실제 LLM이 dry-run 시뮬레이션보다 낮음. 파일 참조를 완전히 하지 못하는 케이스 존재.
**G2 환각률 0.17→0.00**: CTX context 제공 시 환각 완전 제거.

### Overall

| 측정 | 값 |
|------|-----|
| OVERALL WITH CTX | **0.688** |
| OVERALL WITHOUT CTX | 0.109 |
| **OVERALL DELTA** | **+0.578** |
| Verdict | **CTX STRONGLY IMPROVES LLM QUALITY** |

## Dry-Run vs Real LLM 비교

| 측정 | Dry-Run (시뮬레이션) | Real MiniMax M2.5 | 차이 |
|------|---------------------|------------------|------|
| G1 WITH | 0.733 | **1.000** | +0.267 (real이 더 좋음) |
| G1 WITHOUT | 0.033 | 0.219 | +0.186 (real LLM이 더 잘 추측) |
| G1 Delta | +0.700 | **+0.781** | +0.081 |
| G2 WITH | 0.582 | 0.375 | -0.207 (real이 더 낮음) |
| G2 WITHOUT | 0.000 | 0.000 | 0 |
| G2 Delta | +0.582 | +0.375 | -0.207 |
| G2 Hallu/resp | 2.00→0.00 | **0.17→0.00** | 환각 기본값도 낮음 |
| Overall Delta | +0.641 | **+0.578** | -0.063 |

### 인사이트

1. **G1은 dry-run보다 실제가 더 좋음**: CTX context 완벽 활용 (1.000), WITHOUT도 0.219로 시뮬레이션보다 높음
2. **G2는 dry-run보다 실제가 낮음**: 파일 참조 정확도 0.582→0.375 하락. MiniMax M2.5가 파일명 정확 언급을 덜 함
3. **환각은 실제에서 더 적음**: dry-run WITHOUT=2.00 vs real WITHOUT=0.17. MiniMax M2.5가 실제로는 덜 환각
4. **전체 CTX 효과는 실증됨**: Δ+0.578로 여전히 "STRONGLY IMPROVES"

## 주목할 점: G1 Perfect Score

G1 WITH CTX = 1.000 (완벽)의 의미:
- CTX persistent_memory가 주입되면 MiniMax M2.5는 **예외 없이** 과거 파일 회상
- 이는 CTX G1(cross-session memory)의 핵심 가치 실증
- WITHOUT CTX = 0.219: LLM 자체 추측도 일부 가능하지만 불완전

## R@K → Downstream 상관관계 업데이트

이전 가설 (dry-run 기반):
```
G2: 0.582 ≈ 0.862 (R@3) × 0.675 (utilization)
```

실제 MiniMax M2.5:
```
G2: 0.375 ≈ 0.862 (R@3) × 0.435 (utilization)
```

→ MiniMax M2.5의 context 활용률 ~43.5% (dry-run 추정 67.5%보다 낮음)
→ 실제 LLM은 시뮬레이션보다 파일 컨텍스트를 덜 활용 — G2 개선 여지 존재

## 실행 명령

```bash
# MiniMax M2.5로 실행
MINIMAX_API_KEY=<key> MINIMAX_BASE_URL=https://api.minimax.io/anthropic \
MINIMAX_MODEL=MiniMax-M2.5 \
python3 benchmarks/eval/downstream_llm_eval.py --n-scenarios 8
```

## 결과 파일

- `benchmarks/results/downstream_llm_eval_20260328_002607.json`

## Related
- [[projects/CTX/research/20260327-ctx-downstream-eval|20260327-ctx-downstream-eval]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
