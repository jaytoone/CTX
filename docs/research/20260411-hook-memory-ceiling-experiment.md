# 현재 Hook 아키텍처 시간/공간 기억 상한선 실험
**Date**: 2026-04-11  **Type**: Empirical benchmark  **Scope**: project (CTX)

## 실험 목적

현재 hook 아키텍처(git-memory G1 + chat-memory G2 + g2-augment)의 **실제 recall 상한선**을 측정.
"얼마나 오래된/얼마나 관련 있는 정보까지 찾을 수 있는가?"

---

## Hook 아키텍처 현황

| Hook | 이벤트 | 메커니즘 | 데이터 소스 |
|------|--------|---------|-----------|
| **git-memory.py** | UserPromptSubmit | BM25 검색 → top 7 | 211 commits (18일, 2026-03-24~) |
| **chat-memory.py** | UserPromptSubmit | FTS5+vector hybrid (rank<-17) | vault.db: 956 CTX messages (19일) |
| **g2-augment.py** | Pre/PostToolUse(Grep) | codebase-memory-mcp DB query | CTX: 2026 nodes, 3329 edges (117h stale) |

---

## G1 시간 기억 (git-memory.py) 실험

### 데이터 범위
- **커밋 수**: 211개
- **시간 범위**: 18일 (2026-03-24 ~ 2026-04-11)
- **구조적 한계**: 이 repo는 3주 역사 — 더 긴 시간축 측정 불가

### Recall@K Sweep (paraphrase queries, target-confirmed n=4)

| K | Recall | 비고 |
|---|--------|------|
| 3 | 0.250 | — |
| 5 | 0.250 | — |
| **7 (현재 설정)** | **0.500** | 현재 hook 기본값 |
| 10 | 0.500 | K 증가 효과 없음 |
| 15 | 0.500 | plateau |
| 20 | 0.500 | plateau |

**핵심 발견: K=7 이후 recall 개선 없음** — BM25 structural ceiling ≈ 0.500 (paraphrase)

### 원인 분석

K를 늘려도 recall이 오르지 않는 이유:
1. BM25가 paraphrase 쿼리에서 관련 커밋을 상위 7개에 포함 못 시키면, K를 아무리 늘려도 찾지 못함
2. 즉, **K가 아니라 BM25 자체의 semantic 한계** (키워드 다양성에 의존)
3. 기존 fair eval 결과와 일치: paraphrase Recall@7 = 0.634

### 시간 창별 커버리지

| 시간 창 | 커밋 수 | 비고 |
|--------|--------|------|
| 0-1일 | 3 | 오늘 작업 |
| 0-7일 | 32 | 최근 1주 |
| 0-14일 | 180 | 85% 커밋이 최근 2주 집중 |
| 0-18일 | 211 | 전체 (이 프로젝트의 최대) |

**G1 시간 상한**: **18일** (프로젝트 git history 전체) — 구조적으로 더 이상 없음

---

## G2 공간 기억 (chat-memory.py) 실험

### 데이터 범위
- **vault.db CTX 메시지**: 956개
- **시간 범위**: 19일 (2026-03-23 ~ 2026-04-11)
- **FTS5 threshold**: rank < -17 (오늘 적용)

### 시간창별 Hit Rate (n=15 queries per bucket)

| 시간 창 | Hit Rate | Mean Rank | 해석 |
|--------|---------|----------|-----|
| same-day (0-1일) | **40.0%** | -32.4 | 낮음: 오늘 세션은 아직 어휘 축적 부족 |
| 1-3일 전 | **60.0%** | -39.4 | 중간 |
| 3-7일 전 | **86.7%** | -42.4 | **최고**: BM25 매칭 가장 강함 |
| 7-14일 전 | **60.0%** | -30.2 | 중간 |
| 14-19일 전 | **66.7%** | -31.7 | 안정적 |

**핵심 발견: "3-7일 전" 메시지가 가장 잘 찾힘 (87%)**

원인 분석:
- **same-day 낮은 이유**: 오늘 세션은 특정 주제를 막 시작했기 때문에 관련 어휘가 vault에 충분히 축적되지 않음. 쿼리와 vault 메시지가 같은 날이어도 "아직 많은 대화가 없어" 매칭 약함.
- **3-7일 전 가장 높은 이유**: 해당 시간대의 세션들(예: BM25 구현, G1 평가, G2 개선)이 특정 주제에 집중적으로 많은 메시지를 남겼고, 관련 쿼리가 그 어휘와 잘 매칭됨.
- **오래될수록 약간 하락**: 14-19일 전은 67%로 안정적이지만, 더 오래되면 관련성이 낮아질 것으로 예상.

### G2 시간 상한

```
최대 검색 가능 기간: 19일 (vault.db 데이터 한계)
실효 hit rate: 40-87% (시간창에 따라 다름)
"temporal sweet spot": 3-7일 전 (87%)
same-day 약점: 40% — 오늘 대화는 잘 찾히지 않음
```

---

## g2-augment.py 기여도 분석

### 현재 상태

| 항목 | 값 | 평가 |
|------|-----|------|
| 메커니즘 | codebase-memory-mcp DB 쿼리 | — |
| DB 크기 | 2026 nodes, 3329 edges | 적당 |
| **DB 상태** | **117시간 stale (≈5일)** | ❌ 심각 |
| BM25 관련 노드 | 0개 | ❌ 최신 코드 미반영 |

### 실효 기여도

**현재 실질적으로 무효**.
- DB가 5일 stale → 최근 구현된 chat-memory.py, g2-augment.py 자체도 DB에 없음
- auto-index.py 제거 → 앞으로도 자동 갱신 없음
- g2-augment.py가 "try graph first" 가이드를 주입해도 DB가 오래됐으면 잘못된 결과 반환

**결론**: g2-augment.py는 DB 갱신 없이는 가치 없음. 수동으로 `index_repository()` 호출하거나 제거 고려.

---

## 통합 상한선 요약

| 컴포넌트 | 시간 상한 | 실효 Recall | 약점 |
|---------|---------|-----------|-----|
| **G1 git-memory** | 18일 (git history) | Recall@7 = 0.500~0.634 | BM25 semantic ceiling, K 증가 무효 |
| **G2 chat-memory** | 19일 (vault 범위) | Hit rate 40~87% | same-day 40%로 낮음 |
| **g2-augment** | N/A (DB 117h stale) | ≈0% 현재 | DB 갱신 없으면 무의미 |

### 전체 통합 recall 추정

```
한 세션에서 Claude에게 주입되는 정보:
  G1: top 7 results / 211 commits → coverage 3.3% (BM25 recall 50%)
  G2: top 3 messages / 956 messages → coverage 0.3% (threshold 기준 hit 60%)
  g2-augment: 현재 무효

이론적 상한:
  G1 완벽한 시스템이라면: 가장 관련된 결정 1개를 항상 top-7에 포함 → 100%
  현실: paraphrase 쿼리 기준 50%, 구조적 쿼리 기준 88%
  
  G2 완벽한 시스템이라면: 가장 관련된 과거 대화 3개를 항상 검색 → 100%
  현실: 3-7일 전 87%, same-day 40%
```

---

## 개선 포인트

### 즉시 적용 가능
1. **g2-augment.py 비활성화 또는 DB 수동 갱신**: 현재 stale DB는 노이즈만 추가
2. **same-day recall 개선**: G2 hint — 현재 세션 메시지도 vault에 즉시 인덱싱 여부 확인

### 중기 개선
3. **G1 semantic embedding**: BM25 ceiling 50% 돌파. paraphrase recall 50% → 70%+ 가능 예상
4. **G2 adaptive threshold**: same-day는 threshold 완화(-12 수준), 오래된 메시지는 강화

### 한계 (구조적)
5. **G1 시간 한계**: git history = 18일. 더 오래된 결정은 vault.db로만 보강 가능
6. **G2 coverage**: 956개 중 3개만 반환 (0.3%). recall과 noise 사이 trade-off

---

## Sources

- `~/.claude/hooks/git-memory.py`, `chat-memory.py`, `g2-augment.py`
- vault.db: 956 CTX messages (2026-03-23~04-11)
- codebase-memory-mcp DB: 2026 nodes, 117h stale
- Git log: 211 commits (2026-03-24~04-11)
- Benchmark: inline Python analysis (2026-04-11)

- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260411-chat-memory-threshold-principled|20260411-chat-memory-threshold-principled]]
- [[projects/CTX/research/20260409-g1-fulleval-sota-comparison|20260409-g1-fulleval-sota-comparison]]
- [[projects/CTX/research/20260408-g1-temporal-retention-eval|20260408-g1-temporal-retention-eval]]

## Related
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260326-ctx-final-sota-comparison|20260326-ctx-final-sota-comparison]]
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260410-g1-fair-eval-bm25-bias|20260410-g1-fair-eval-bm25-bias]]
- [[projects/CTX/research/20260326-ctx-vs-sota-comparison|20260326-ctx-vs-sota-comparison]]
- [[projects/CTX/research/20260410-vault-vector-migration-and-benchmark|20260410-vault-vector-migration-and-benchmark]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260407-g1-spiral-eval-results|20260407-g1-spiral-eval-results]]
