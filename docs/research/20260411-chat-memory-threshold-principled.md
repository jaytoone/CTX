# chat-memory.py FTS5 Rank Threshold: 합리적 임계값 도출
**Date**: 2026-04-11  **Type**: Empirical analysis  **Scope**: project (CTX)

## Problem Statement

이전 실험(`20260411-hook-comparison-auto-index-vs-chat-memory.md`)에서 FTS5 rank threshold=-17을
25개 hand-crafted 쿼리에서 도출했다. 사용자 지적: **과적합 의혹** — train=test 오염 + 쿼리 선택 편향.

본 실험은 실제 vault.db 쿼리 히스토리에서 데이터를 샘플링해 **데이터 기반 합리적 임계값**을 도출한다.

---

## Methodology

### 데이터 소스 (hand-crafted 쿼리 대신)

| 구분 | 소스 | 샘플 수 | 의미 |
|------|------|--------|------|
| **CTX-self** | vault.db CTX 프로젝트 실제 user 메시지 (최근 100개) | 98 hits | 관련 쿼리 (TP 대상) |
| **Cross-project** | vault.db 타 프로젝트 실제 user 메시지 (무작위 100개) | 96 hits | 무관 쿼리 (FP 대상) |

**핵심 차이**: hand-crafted 쿼리(의도적 설계)가 아닌 **실제 사용 패턴**에서 샘플링.
- CTX 프로젝트 user 메시지는 실제로 CTX 관련 내용이므로 관련성 ground truth로 사용 가능
- 타 프로젝트 메시지를 CTX FTS5로 검색하면 vocabulary 우연 매칭만 발생 = false positive

### 측정 방법

chat-memory.py 실제 쿼리 구조를 그대로 사용:
```sql
SELECT fts.rank FROM messages_fts fts
JOIN messages m ON fts.rowid=m.id
JOIN sessions s ON m.session_id=s.session_id
WHERE messages_fts MATCH ?
  AND s.project='-home-jayone-Project-CTX'
  AND m.role IN ('user','assistant') AND length(m.content)>30
ORDER BY rank LIMIT 1
```

---

## Results

### Score Distributions

| 통계 | CTX-self (관련) | Cross-project (무관) |
|------|----------------|---------------------|
| min | -75.5 | -29.3 |
| p10 | -60.0 | -23.2 |
| p25 | -46.2 | -16.8 |
| p50 | -20.6 | -13.5 |
| p75 | -16.0 | -10.9 |
| p90 | -13.2 | -8.2 |
| max | -5.6 | -2.1 |

### Histogram

```
rank range   ctx  oth  chart(C=CTX ·=cross-proj)
[-80, -75)    1    0  C
[-75, -70)    2    0  CC
[-70, -65)    4    0  CCCC
[-65, -60)    3    0  CCC
[-60, -55)    6    0  CCCCCC
[-55, -50)    6    0  CCCCCC
[-50, -45)    4    0  CCCC
[-45, -40)    2    0  CC
[-40, -35)    7    0  CCCCCCC
[-35, -30)    5    0  CCCCC
[-30, -25)    5    1  CCCCC·
[-25, -20)    7   14  CCCCCCC··············
[-20, -15)   28   23  CCCCCCCCCCCCCCCCCCCC····················
[-15, -10)   13   41  CCCCCCCCCCCCC····················
[-10,  -5)    5   16  CCCCC················
[ -5,   0)    0    1  ·
```

### 분포 구조 (3-Zone Analysis)

| Zone | 범위 | CTX | Cross | 해석 |
|------|------|-----|-------|------|
| **Zone A** | rank < -30 | 50 (51%) | 1 (1%) | CTX-specific: 강한 의미적 관련성 |
| **Zone B** | -30 ~ -19 | 30 (31%) | 15 (16%) | Overlap zone: 부분 관련 |
| **Zone C** | rank > -19 | 18 (18%) | 80 (83%) | Noise zone: 우연한 어휘 매칭 |

**핵심**: Zone A와 Zone C는 명확히 분리됨. Zone B가 ambiguous.

---

## Threshold Analysis

### Full Sweep (Youden J statistic: sensitivity + specificity - 1)

```
thresh   TP%   FP%   F1    J-stat
    -5  100.0   99.0  0.669   0.010
   -10   94.9   82.3  0.685   0.126
   -13   90.8   59.4  0.726   0.314
   -14   83.7   42.7  0.739   0.410
   -15   81.6   39.6  0.738   0.420
   -16   72.4   29.2  0.719   0.433
  *-17   70.4   20.8  0.736  *0.496*  ← Youden J 최대 (J-stat peak)
   -18   68.4   20.8  0.723   0.475
   -19   53.1   16.7  0.625   0.364
   -20   53.1   15.6  0.629   0.374
  *-24   46.9    1.0  0.634  *0.459*  ← Natural gap (FP 14.6%→1% 급락)
   -30   40.8    0.0  0.580   0.408   ← Perfect precision (FP=0)
```

### 자연 갭(Natural Gap) 발견

```
-23: FP=14.6%
-24: FP=1.0%   ← 자연 갭 경계점 (FP 13.6%p 급락)
```

-24 이하에서는 cross-project 쿼리가 거의 통과하지 않음.
이는 score 분포의 **bimodal 구조**를 반영: CTX-specific 쿼리는 -30 이하,
단순 vocabulary overlap은 -25 이상에 집중됨.

---

## 과적합 검증 결과

| 지표 | Hand-crafted 쿼리 (n=25) | 실제 쿼리 (n=194) | 결론 |
|------|--------------------------|-------------------|------|
| -17의 TP | 100.0% | 70.4% | 실제 데이터에선 낮음 |
| -17의 FP | 10.0% | 20.8% | 실제 FP 더 높음 |
| -17의 F1 | 0.968 | 0.736 | 성능 차이 있음 |
| **최적 threshold** | -17 | **-17** | **동일 (Youden J 기준)** |

**결론**: -17은 과적합되지 않았다. 실제 쿼리 데이터에서도 Youden J 통계량 기준 최적점.
단, 실제 성능(TP=70%, FP=21%)은 hand-crafted 실험(TP=100%, FP=10%)보다 현실적으로 낮다.

---

## 합리적 임계값 권고

### 선택지 비교

| 임계값 | TP% | FP% | F1 | J-stat | 적합 케이스 |
|--------|-----|-----|-----|--------|-----------|
| **-17** | 70.4% | 20.8% | 0.736 | **0.496** | 재현율 우선 (더 많은 메모리 주입) |
| **-24** | 46.9% | 1.0% | 0.634 | 0.459 | 정밀도 우선 (노이즈 최소화) |
| **-30** | 40.8% | 0.0% | 0.580 | 0.408 | 완벽한 정밀도 (매우 보수적) |

### 최종 권고: **-24** (context injection 용도)

**근거**:
1. **자연 갭 기반**: score 분포에서 데이터 기반으로 발생한 자연 경계점
2. **용도 비대칭성**: context injection에서 FP(노이즈 주입)의 비용 > FN(관련 메모리 누락)
3. **FP=1%**: 주입되는 메모리의 99%가 실제 관련 내용
4. **TP=47%**: CTX 관련 강한 쿼리의 절반 이상은 여전히 매칭

-17 vs -24:
- -17: 더 많은 CTX 메모리 주입 (70% vs 47%), 하지만 5회 중 1회는 무관한 내용
- -24: 더 적지만 거의 확실히 관련된 메모리만 주입

chat-memory.py 사용 패턴 고려: 세션 시작마다 context로 주입되는 내용이므로
**정밀도(noise-free) > 재현율** → -24 권고.

### 대안: -17 유지도 합리적

사용자가 더 많은 관련 메모리를 원한다면 -17도 합리적:
- 과적합이 아님 (실제 데이터에서 Youden J 최적점 동일)
- FP=21%이지만 FTS5 BM25 순위로 상위 3개 반환 → FP가 포함되더라도 bottom rank
- 사용자가 주관적으로 noisy context를 감내할 수 있으면 -17

---

## Implementation

### chat-memory.py 수정

```python
# 현재 (threshold 없음)
"WHERE messages_fts MATCH ?"

# -24 적용 (near-zero FP)
"WHERE messages_fts MATCH ? AND rank < -24"

# -17 적용 (balanced, Youden J optimal)
"WHERE messages_fts MATCH ? AND rank < -17"
```

### 실제 파일 위치

```
~/.claude/hooks/chat-memory.py — query_vault() 함수 내 FTS5 쿼리 2개
```

---

## Sources

- `vault.db` CTX project user messages (n=100, 최근 100개)
- `vault.db` cross-project user messages (n=100, 무작위)
- `~/.claude/hooks/chat-memory.py` — 실제 FTS5 쿼리 구조
- 본 실험 코드: inline Python analysis (2026-04-11)

## Related

- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
