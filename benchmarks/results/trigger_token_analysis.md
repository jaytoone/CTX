# CTX Trigger-Type 분석 — Recall 분해 + 토큰 비용
**Date**: 2026-03-26  **Source**: 7 real datasets, 682 queries (adaptive_trigger)

## SG3: Cross-Session R@10 — Trigger-Type 분해

### 데이터 요약

| Trigger Type | N | R@1 | R@5 | R@10 | NDCG@5 | TES |
|---|---|---|---|---|---|---|
| EXPLICIT_SYMBOL | 325 | 0.489 | 0.554 | **0.566** | 0.525 | 0.378 |
| SEMANTIC_CONCEPT | 192 | 0.383 | 0.815 | **0.880** | 0.802 | 0.424 |
| TEMPORAL_HISTORY | 70 | 0.100 | 0.371 | **0.500** | 0.240 | 0.264 |
| IMPLICIT_CONTEXT | 95 | 0.187 | 0.404 | **0.424** | 0.591 | 0.298 |
| **OVERALL** | **682** | | | **0.628** | | |

> Note: multi_dataset_cross_session_eval의 0.567은 AgentNode/GraphPrompt/OneViral 실제 코드베이스 가중 평균 (small 포함 시 0.628).

### 핵심 발견

1. **SEMANTIC_CONCEPT 최강** (R@10=0.880): 자연어 개념어 검색 — TF-IDF가 가장 효과적
2. **TEMPORAL_HISTORY 최약** (R@10=0.500): "show the module we discussed about X" 패턴. 비결정적 참조로 ambiguous
3. **IMPLICIT_CONTEXT 두 번째 약점** (R@10=0.424): import BFS 탐색이 596파일 대형 코드베이스에서 희석
4. **EXPLICIT_SYMBOL 중간** (R@10=0.566): exact match는 높으나 동명 함수 충돌 (main, init) 취약

### 개선 우선순위

- **TEMPORAL_HISTORY**: 쿼리에서 핵심 키워드만 추출 후 BM25 → TF-IDF augmentation 필요
- **IMPLICIT_CONTEXT**: import BFS depth 증가 + relevance score decay 조정 검토

---

## SG2: CTX 토큰 비용 측정

### Trigger별 평균 컨텍스트 비용

| Trigger Type | Files/query | Tokens/query | Tok/file (avg) |
|---|---|---|---|
| EXPLICIT_SYMBOL | 4.6 | 8,659 | ~1,891 |
| SEMANTIC_CONCEPT | 7.8 | 19,822 | ~2,546 |
| TEMPORAL_HISTORY | 8.1 | **40,302** | ~4,967 |
| IMPLICIT_CONTEXT | 4.0 | 6,044 | ~1,511 |

### 분석

- **TEMPORAL_HISTORY 토큰 급등**: 파일당 ~5,000 토큰 — 모듈 docstring 포함 대형 파일 우선 검색
  - 개선: 토큰 예산 cap (max 20,000 tokens/query) + 파일 분할 검색
- **IMPLICIT_CONTEXT 최저비용**: import BFS가 핵심 파일만 추려 효율적 (avg 4파일, 6K 토큰)
- **전체 평균**: 약 18,707 tokens/query (가중 평균, trigger distribution 기준)

### 네이티브 agentic search 대비

| 지표 | CTX | Native Grep (추정) |
|---|---|---|
| 평균 tokens/query | ~18,707 | Adaptive (필요시만) |
| 결정론적 | Yes (117ms) | No (agent turn) |
| 병렬 실행 | Yes (hook-based) | No |

> **미확인**: Native agentic search의 tokens/correct-retrieval 비율 — 직접 측정 필요

---

## 결론

- Cross-session R@10=0.567 (multi-dataset 가중 평균) 분해:
  - 강점: SEMANTIC_CONCEPT (0.880), EXPLICIT_SYMBOL (0.566)
  - 약점: TEMPORAL_HISTORY (0.500), IMPLICIT_CONTEXT (0.424)
- TEMPORAL_HISTORY의 고비용(40K tok/q) + 저성능(R@10=0.5) = P0 개선 타깃
- IMPLICIT_CONTEXT의 저비용(6K tok/q) + 수용 성능 = 효율적 트리거
