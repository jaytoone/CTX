# [expert-research] CTX Hook Semantic Gap 분석
**Date**: 2026-04-12  **Skill**: expert-research

## Original Question
키워드 위주인건가? 맥락에 대해서는 어떠한가? 즉, 직접적인 키워드 매칭이 없더라도 중요한 내용일 수 있잖아.

## 핵심 답변

**Yes — 현재 시스템은 키워드 위주이고, 맥락 손실이 측정됨.**
그러나 그 크기와 영향은 쿼리 타입에 따라 매우 다르다.

---

## CTX 실측 데이터 (내부 실험 기반)

### G1 git-memory (BM25 only)
| 쿼리 타입 | Recall@7 | 해석 |
|----------|---------|------|
| Exact/structured | ~0.88 | 키워드 직접 매칭 — gap 거의 없음 |
| Paraphrase (자유형) | **0.634** | 어휘 mismatch → 11%p 손실 |
| 전체 (fair eval) | 0.746 | BM25 편향 0.373 포함 |

**K 증가 효과 없음**: K=7 이후 recall plateau. BM25 semantic ceiling = 구조적 한계.

### CM chat-memory (FTS5 + vector hybrid)
| 시간 창 | Hit Rate |
|--------|---------|
| Same-day (0-1일) | **40%** |
| 3-7일 전 | **87%** (최고) |
| 7-19일 전 | 60-67% |

Vector embedding (multilingual-e5-small) 추가 결과:
- TP rate: 100% (관련 쿼리 전부 검색됨)
- FP rate: 100% (무관 쿼리도 전부 검색됨 — threshold 전)
- → Threshold rank < -17 적용 후 precision 복원

---

## 어디서 맥락을 놓치는가

### 1. 자유형 paraphrase — 가장 큰 손실 (~11%p)
```
쿼리: "랭킹 알고리즘 교체했을 때 어떻게 됐어?"
커밋: "feat: replace TF-IDF with BM25 in AdaptiveTrigger"
→ BM25가 "랭킹", "알고리즘", "교체"를 "BM25", "TF-IDF", "replace"로 매핑 실패
```

### 2. Same-day 40% — semantic gap이 아니라 희소 코퍼스 문제
같은 날 커밋 1-2개 → IDF 불안정 → BM25 자체 문제.
Vector를 추가해도 해결 안 됨 (vector도 희소 코퍼스에서 불안정).

### 3. Synonym map으로 이미 일부 해소
iter 4에서 수동 synonym map 도입 → +13% (0.661→0.746):
```python
_SYNONYM_MAP = {"BM25": ["okapi","ranking"], "G1": ["git-memory","decision"], ...}
```
**이것이 핵심**: vector embedding 없이 curated synonym으로 comparable gain 달성.

---

## Vector Hybrid의 실질적 역할 (CM)

Vector embedding이 하는 일:
- BM25가 못 잡는 paraphrase 커버 → TP rate 100%
- 그러나 noise도 함께 확대 → FP rate 100%
- Threshold (rank < -17)가 noise 필터 역할

즉, **"semantic gap 해소"가 아니라 "recall 최대화 후 threshold로 precision 복원"** 구조.

---

## 아키텍처별 semantic 능력 정리

| 컴포넌트 | Keyword 매칭 | Semantic 이해 | 맥락 손실 크기 |
|---------|------------|-------------|------------|
| G1 git-memory | BM25 only | synonym map (수동) | paraphrase ~11%p |
| CM chat-memory | FTS5 | vector hybrid (α=0.5) | same-day 60%, old queries ~30% |
| G2 prefetch | BM25 + git grep | 없음 | keyword 없으면 0% |

---

## 개선 우선순위 (비용/효과 기준)

| 방법 | 예상 gain | 비용 | CTX 적합성 |
|------|---------|------|---------|
| Synonym map 확장 (동의어 추가) | +5-8%p | 매우 낮음 | ✅ 즉시 가능 |
| Query expansion (동사 패턴 추가) | +3-5%p | 낮음 | ✅ 즉시 가능 |
| Vector hybrid G1 도입 | +8-15%p | 중간 (5-20ms) | ❌ <1ms constraint 위반 |
| LLM query expansion | +10-15%p | 높음 (LLM call) | ❌ latency |
| Two-stage BM25→rerank | +8-12%p | 중간 | 조건부 (latency 허용 시) |

---

## 결론

1. **키워드 위주가 맞다** — G1/G2 모두 lexical matching 기반
2. **맥락 손실 규모**: paraphrase 쿼리에서 ~11%p, same-day 60%p
3. **Vector (CM)는 이미 추가됨** — 그러나 semantic 이해가 아닌 recall 부스트 + threshold 구조
4. **당장 할 수 있는 개선**: synonym map 확장 (동사 패턴 — "replace with", "switch to", "roll back") — vector 없이 comparable gain 가능
5. **구조적 한계**: K 증가, vector 추가 모두 same-day희소 코퍼스 문제는 해결 못 함

## Confidence: MEDIUM
- 구조적 분석은 HIGH
- Threshold 후 CM F1 수치 미공개로 hybrid net benefit 정량화 불완전

## Related
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260410-g1-fair-eval-bm25-bias|20260410-g1-fair-eval-bm25-bias]]
- [[projects/CTX/research/20260411-hook-memory-ceiling-experiment|20260411-hook-memory-ceiling-experiment]]
- [[projects/CTX/research/20260411-chat-memory-threshold-principled|20260411-chat-memory-threshold-principled]]
- [[projects/CTX/research/20260424-memory-experiential-eval-protocol|20260424-memory-experiential-eval-protocol]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
