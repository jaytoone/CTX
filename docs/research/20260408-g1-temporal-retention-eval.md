# G1 Temporal Retention — Recall Decay Curve
**Date**: 2026-04-08  **Type**: Empirical measurement  **Script**: `benchmarks/eval/g1_temporal_retention_eval.py`

---

## 실험 목적

**원래 연구 질문 재초점**: Format ablation (20260408) 이후 핵심 문제 발견 — 기존 벤치는 "지금 이 순간 어떤 포맷이 답을 갖고 있는가"를 측정했을 뿐, 실제 목적인 "시간이 지남에 따라 각 포맷이 오래된 결정을 얼마나 잘 보존하는가"를 측정하지 않았다.

**Temporal hold-out 설계**:
- Age N = HEAD에서 N번째 이전 커밋 (target decision)
- 각 포맷의 context: 현재 HEAD 기준으로 빌드 (present-time view)
- LLM에게 age N 커밋의 결정 내용을 물어봄
- 측정: 포맷별 keyword recall → retention_curve[age][format]

**가설**: `g1_filtered`는 topic-dedup으로 7 슬롯을 다양한 토픽에 분산 → 오래된 결정도 슬롯을 받아 더 오래 보존. `random_noise` (window=7)는 age > 7에서 완전 붕괴.

---

## 실험 설계

| 파라미터 | 값 |
|---------|---|
| Ages | [3, 7, 15, 30] commits from HEAD |
| Formats | no_ctx, random_noise, g1_raw, g1_filtered, g1_g2_hybrid |
| 평가 | 타겟 커밋 subject의 핵심 키워드 recall |
| 모델 | MiniMax-M2.5 |
| 총 API 호출 | 4 ages × 5 formats = 20 calls |

**타겟 커밋 (age별)**:

| Age | Hash | Date | Commit Subject | Keywords |
|-----|------|------|----------------|---------|
| 3 | c7070218 | 2026-04-07 | git-memory: universal decision detection... | memory, universal, decision, detection |
| 7 | ebd429f1 | 2026-04-06 | Old CTX remnants fully removed | CTX |
| 15 | 9279b569 | 2026-04-03 | COIR standard benchmark: BM25 Hit@5=0.780 on CodeSearchNet | 0.780, COIR, BM25 |
| 30 | 471065f8 | 2026-04-02 | 2015 live-inf: save state for next session | live, save, state, next |

**포맷별 이론적 윈도우**:
- `random_noise`: n=7 (age > 6 는 구조적으로 포함 불가)
- `g1_raw`: n=20 (age > 19 는 포함 불가)
- `g1_filtered`: n=30, topic-dedup (age > 29 는 포함 불가, dedup으로 일부 제거 가능)

---

## Raw 결과

### 포맷별 in-window 여부 (실제 substring 검사)

| Age | no_ctx | random_noise | g1_raw | g1_filtered | g1_g2_hybrid |
|-----|--------|-------------|--------|-------------|-------------|
| 3 | OUT | **IN** | **IN** | **IN** | **IN** |
| 7 | OUT | OUT | OUT | OUT | OUT |
| 15 | OUT | OUT | **IN** | OUT | OUT |
| 30 | OUT | OUT | OUT | OUT | OUT |

> Age=7: 모든 포맷 OUT — "Old CTX remnants fully removed"가 어떤 포맷에도 포함되지 않음
> Age=15: `g1_raw`만 IN — COIR 커밋이 n=20 윈도우 내에 포함됨. `g1_filtered`는 topic-dedup으로 제외됨.

### Keyword Recall Scores

| Age | no_ctx | random_noise | g1_raw | g1_filtered | g1_g2_hybrid |
|-----|--------|-------------|--------|-------------|-------------|
| 3 | 1.000* | 1.000 | 1.000 | 1.000 | 1.000 |
| 7 | 1.000* | 1.000* | 1.000* | 1.000* | 1.000* |
| 15 | 0.667* | 0.333* | **1.000** | 0.667* | 0.667* |
| 30 | 1.000* | 1.000* | 0.000* | 0.000* | 0.000* |

*(* = 커밋이 포맷 윈도우 밖)*

---

## 데이터 품질 이슈 (중요)

### 이슈 1: 키워드 인플레이션 (Generic Keywords)

Age=3, 7, 30의 키워드가 너무 일반적:
- `['memory', 'universal', 'decision', 'detection']` — LLM 응답 어디서나 등장
- `['CTX']` — 프로젝트명이라 모든 응답에 포함
- `['live', 'save', 'state', 'next']` — 프로그래밍 용어라 no_ctx도 1.000

결과: age=3, 7은 측정 자체가 불가능. age=30은 역설적으로 no_ctx=1.000 > g1_raw=0.000 (아래 이슈 3 참조).

### 이슈 2: Training Data Effect

no_ctx=0.667 @ age=15 — LLM이 COIR와 BM25의 관계를 훈련 데이터에서 알고 있어 context 없이도 recall.

`0.780`이라는 구체적 숫자만이 진짜 context-dependent 키워드 (no_ctx는 이 숫자를 맞추지 못함).

### 이슈 3: Context Anchoring Effect (역설)

Age=30에서 `g1_raw=0.000`, `g1_filtered=0.000`이지만 `no_ctx=1.000`.
- Context가 있을 때: LLM이 "이 커밋에 대한 정보가 context에 없습니다"라고 정직하게 답변 → generic 키워드 미포함
- Context 없을 때: LLM이 hallucinate/ramble하며 generic 단어 사용 → 우연히 키워드 적중

이 현상은 관련 없는 context를 주입하면 오히려 LLM 응답 품질을 저하시킬 수 있음을 보여준다.

---

## 핵심 발견

### Finding 1: Age=15만이 유의미한 분화 제공

| 포맷 | Score | Window | 해석 |
|------|-------|--------|------|
| g1_raw | 1.000 | IN | n=20 내에 COIR 커밋 포함 → 3개 키워드 모두 recall |
| g1_filtered | 0.667 | OUT | n=30이지만 topic-dedup이 age=15 커밋 대신 age=14 COIR 커밋 선택 → BM25/COIR 부분 recall |
| random_noise | 0.333 | OUT | n=7 초과 → 훈련 데이터로만 부분 recall |
| no_ctx | 0.667 | OUT | COIR/BM25 훈련 데이터 지식 (단, 0.780은 맞추지 못함) |

### Finding 2: g1_filtered의 "Topic Substitution" 현상

Age=15 커밋 (COIR standard, 0.780)은 topic-dedup에 의해 제외됨. 대신 age=14 커밋 (COIR full corpus, 0.640)이 선택됨.

결과:
- `g1_filtered`가 정확한 커밋은 없지만, 동일 토픽의 인접 커밋을 통해 부분적 recall (0.667)
- 이는 "temporal retention"이 아니라 "topic coverage"를 통한 간접 recall
- g1_filtered의 진짜 강점은 시간이 아닌 **토픽 다양성 보존**

### Finding 3: 가설 부분 확인

```
Age 15: random_noise=0.333 vs g1_filtered=0.667 → δ=+0.333 (g1_filtered BETTER)
```

단, 이 차이의 원인이 "오래된 결정 보존"이 아닌 "인접 토픽 커밋 포함"임을 구별해야 함.

Age=30에서는 오히려 random_noise=1.000 > g1_filtered=0.000 — 다만 이건 키워드 인플레이션 때문.

---

## 방법론 한계 및 개선 방향

### 현재 키워드 추출의 한계

```
나쁜 키워드: 'memory', 'CTX', 'live', 'save', 'state', 'next'
  → 범용 단어, training data에서도 등장
  
좋은 키워드: '0.780', '0.640', '65%', '30%'
  → 구체적 숫자, context 없으면 맞추기 어려움
```

**개선**: 숫자/비율/버전문자열만 키워드로 추출. 일반 명사 제외.

### 개선된 측정 설계 (미구현)

1. **Numeric-only keywords**: 정확한 숫자/비율만 측정 지표로 사용
2. **Closed-book control**: 질문에서 힌트 제거 후 no_ctx baseline 재측정
3. **Delta measurement**: open_book(with context) - closed_book(without context) = true contribution
4. **Multi-commit per age**: 1개 커밋만 테스트하면 운이 개입 → 각 age에 3개 커밋 사용

---

## 결론

**가설 검증 결과 (이 실험 범위)**:
- CTX 프로젝트에서 age=15 (COIR 커밋)이 유일하게 의미있는 temporal differentiation 제공
- g1_filtered (0.667) > random_noise (0.333) at age=15 — 지지됨
- 단, 이 차이는 "오래된 결정 직접 보존"이 아닌 "동일 토픽 인접 커밋 포함"이 원인

**핵심 발견**: 
- 신뢰성 있는 측정을 위해 specific numeric keywords 필수
- Context anchoring effect: 무관한 context가 있으면 LLM이 더 보수적으로 답변
- g1_filtered의 진짜 강점은 시간적 retention이 아닌 topic diversity coverage

**다음 단계**: 숫자 키워드 전용 버전으로 재실험 (3개 이상 numeric commit at each age level).

---

## 관련 파일
- `benchmarks/eval/g1_temporal_retention_eval.py` — 실험 스크립트
- `benchmarks/results/g1_temporal_retention_20260408_125811.json` — 원시 결과
- `docs/research/20260408-g1-format-ablation-results.md` — 선행 실험

## Related
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260408-g1-format-ablation-results|20260408-g1-format-ablation-results]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260407-g1-spiral-eval-results|20260407-g1-spiral-eval-results]]
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
