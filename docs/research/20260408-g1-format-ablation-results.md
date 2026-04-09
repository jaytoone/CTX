# G1 Format Ablation — Downstream δ Measurement
**Date**: 2026-04-08  **Type**: Empirical measurement  **Script**: `benchmarks/eval/g1_format_ablation_eval.py`

---

## 실험 목적

원래 연구 질문: **"어떤 방식의 기억 주입이 LLM 장기기억에 가장 도움이 되는가?"**

5가지 G1 주입 포맷을 동일 Q&A 태스크에 적용하여 LLM 응답 품질(keyword recall) 비교.

---

## 실험 설계

| 포맷 | 설명 |
|------|------|
| `no_ctx` | 컨텍스트 없음 (baseline) |
| `random_noise` | 최근 7개 커밋 그대로 (노이즈 포함 — 구 G1 실패 모드) |
| `g1_raw` | n=20, 노이즈 필터 없음, 결정 감지만 |
| `g1_filtered` | n=30, 노이즈 필터 + topic-dedup (현재 G1) |
| `g1_g2_hybrid` | G1 filtered + 최근 수정 파일명 (G1+G2 결합) |

**태스크**: CTX 프로젝트 git 히스토리 기반 10개 사실 Q&A
**평가**: 정답 키워드 recall (required 70% + optional 30%)
**모델**: MiniMax-M2.5 (via Anthropic-compatible API)

---

## Raw 결과

| 포맷 | Mean Score | δ vs baseline | 판정 |
|------|-----------|--------------|------|
| `no_ctx` | 0.281 | — | (baseline) |
| `random_noise` | 0.523 | +0.241 | MODERATE GAIN |
| `g1_raw` | 0.438 | +0.156 | MODERATE GAIN |
| `g1_filtered` | 0.352 | +0.071 | MARGINAL GAIN |
| `g1_g2_hybrid` | 0.316 | +0.035 | MARGINAL GAIN |

---

## 데이터 품질 이슈 (중요)

Raw 결과를 액면 그대로 신뢰할 수 없는 두 가지 이유:

### 이슈 1: 키워드 인플레이션 (Question Repetition Bias)

LLM이 "정보가 없다"고 답하면서도 **질문에 포함된 키워드를 반복**하여 높은 점수를 받음.

```
t04 no_ctx 응답 (score=0.925):
"I don't have information about this... G1 git-log retrieval benchmark across
3 projects... recall results before fixes."
```

→ 질문 자체에 "3", "projects", "git-log", "recall"이 있어 LLM이 거부하면서 반복.
→ t04의 모든 포맷이 0.925 — 컨텍스트 유무와 무관.

**보정 후 유효 태스크 수**: 10 → 7 (t04, t06 일부, t08 제외)

### 이슈 2: [NO-TEXT-BLOCK] 오류

MiniMax M2.5가 2개 응답에서 텍스트 블록 없이 ThinkingBlock만 반환.
→ 해당 태스크 score=0 (정당한 0인지 오류인지 불분명).

---

## 보정 분석 (유효 태스크 7개 기준)

| 포맷 | 진짜 컨텍스트 활용 태스크 수 | 핵심 패턴 |
|------|--------------------------|----------|
| `random_noise` | t01 ✅, t07 ✅ | 최근 커밋 2개에서 직접 사실 추출 |
| `g1_raw` | t05 ✅, t06 ✅, t07 ✅ | 결정 감지로 더 광범위 커버 |
| `g1_filtered` | t03 ✅ | hooks 관련 커밋만 포착 |
| `g1_g2_hybrid` | t03 ✅, t06 ✅ | 파일명이 t06에서 추가 도움 |

**핵심 사례**:

```
t07 (G2 prefetch: 30%→65% 결과 질문):
  random_noise = 1.000  ← "G2 prefetch benchmark: 30% -> 65%" 커밋이 최근 7개에 포함
  g1_filtered  = 0.060  ← topic-dedup이 해당 커밋을 제거함
```

```
t03 (3 hooks 구조 질문):
  g1_filtered  = 0.425  ← hooks 관련 커밋을 포착
  random_noise = 0.000  ← 해당 커밋이 최근 7개 밖
```

---

## 핵심 발견

### Finding 1: CTX 프로젝트에서 g1_filtered가 random_noise보다 낮은 이유

**원인**: G1 noise filter + topic-dedup은 **PaintPoint 같은 버전 태그 다량 프로젝트**를 위해 설계됨.
CTX 프로젝트는 날짜-prefix 커밋 스타일(`20260407 G1 noise filter...`)이라 noise filter가 실질적 효과 없음.
결과적으로 topic-dedup만 작동하여 최근 관련 커밋을 교체함.

| 프로젝트 타입 | G1 filter 효과 | 권장 포맷 |
|------------|--------------|---------|
| 버전 태그 다량 (PaintPoint: NoiseRatio 100%) | 필수 — 없으면 7-cap 낭비 | g1_filtered |
| 날짜-prefix 커밋 (CTX: NoiseRatio 0%) | 역효과 가능 — dedup이 최신 커밋 교체 | g1_raw |
| 혼합형 | 중간 | g1_filtered |

### Finding 2: no_ctx baseline이 0.281로 비어있지 않은 이유

LLM이 **질문에서 키워드를 반복**하거나 **사전학습 지식**으로 일반적 사실을 언급.
→ keyword-recall 스코어링의 한계: context 유무를 완전히 분리하지 못함.

### Finding 3: G1+G2 hybrid가 G1 단독보다 나은 경우 없음

g1_g2_hybrid는 파일명 목록 추가 시 t06에서 소폭 개선되지만, 평균적으로 g1_filtered와 동등.
→ 파일명 나열 자체는 LLM에게 결정 정보를 추가 제공하지 않음.

---

## 방법론 한계 및 개선 방향

### 현재 scoring의 한계

```
현재: keyword recall → 질문 반복으로 inflation 가능
개선: "closed-book vs open-book" 설계 필요
  - Closed-book: 질문에서 키워드 제거 후 테스트
  - Open-book: 컨텍스트 제공 후 테스트
  - δ = open_book_score - closed_book_score (진짜 contribution)
```

### 더 강한 실험 설계 (미구현)

1. **Different-project hold-out**: CTX 히스토리로 Q&A 설계, 다른 프로젝트로 평가
2. **SWE-Bench-style**: 실제 버그 수정 태스크에 G1 컨텍스트 주입
3. **Temporal hold-out**: 과거 결정에 대해 질문, 정답이 context에만 존재하도록 설계

---

## 결론

**원래 연구 질문에 대한 답 (이 실험 범위)**:
- CTX 프로젝트에서는 `random_noise` (raw 최근 7개)가 가장 높은 δ (+0.241) — but this is **project-specific**
- G1 noise filter는 버전 태그 다량 프로젝트(PaintPoint)에 필수, CTX처럼 clean한 프로젝트에서는 역효과 가능
- G1+G2 hybrid는 명확한 이점 없음 (파일명 추가 효과 미미)

**중요 한계**: 이 실험은 SAME-PROJECT Q&A로, 진짜 cross-session long-term memory 평가가 아님.
완전한 답을 위해서는 SWE-Bench-style downstream eval이 필요 (미구현 상태).

---

## 관련 파일
- `benchmarks/eval/g1_format_ablation_eval.py` — 실험 스크립트
- `benchmarks/results/g1_format_ablation_20260408_103358.json` — 원시 결과
- `docs/research/20260408-original-intent-gap-analysis.md` — 연구 의도 정합성 분석

## Related
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260408-original-intent-gap-analysis|20260408-original-intent-gap-analysis]]
- [[projects/CTX/research/20260327-ctx-downstream-eval|20260327-ctx-downstream-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-eval-complete|20260328-ctx-downstream-eval-complete]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
- [[projects/CTX/research/20260407-g1-spiral-eval-results|20260407-g1-spiral-eval-results]]
