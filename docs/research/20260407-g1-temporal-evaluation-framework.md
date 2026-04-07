# [expert-research-v2] G1 시간 대비 성능 평가 방법론
**Date**: 2026-04-07  **Skill**: expert-research-v2

## Original Question
G1 (git log 기반 cross-session decision memory)의 시간 대비 성능을 어떻게 평가할 수 있는가?

## 핵심 구분: 두 가지 독립적 차원

| 차원 | 핵심 문제 | 실패 시 증상 |
|------|----------|-------------|
| **Recall decay** | 오래된 결정이 시스템에 inject되는가 | P4/P5 결정이 아예 surface되지 않음 |
| **Decision validity** | inject된 결정이 실제로 유효한가 | stale한 결정이 inject되어 LLM 혼란 유발 |

두 차원은 독립적으로 실패 가능. Recall 90%이지만 validity 50%라면 G1은 오히려 harmful.

## Web Facts
[FACT-1] LOCCO benchmark: 6-period retention rate 사용. adaptive decay λ(n) = recall frequency 기반.
[FACT-2] LongMemEval (Wu 2024): 500 queries, 5 memory abilities, temporal reasoning 포함.
[FACT-3] EvolveBench (ACL 2025): knowledge evolution 평가 — 시간에 따라 변하는 사실 처리.
[FACT-4] ZEP (Temporal KG 2025): 각 사실에 validity period 부여. 타임스탬프 기반 fact evolution.
[FACT-5] TA-ARE: temporal relevance ≠ recency. query type에 따라 granularity 다름.
[FACT-6] ECT-QA: corpus 성장 시뮬레이션으로 retrieval accuracy degradation 측정.
[FACT-7] Information aging: 사실의 expiration date는 domain마다 다름.

## 5가지 평가 방법

### Method 1: Git-Native Staleness Oracle [구현 난이도: Low]
결정 D가 파일 F를 언급할 때, `git log --after={D.date} -- F`로 이후 수정 여부 탐지.
- 결과 있으면 inject 시 "[possibly outdated]" 마킹
- Override 탐지: "revert", "replace", "switch back" 키워드 + 동일 파일
- **한계**: 파일 레벨이 coarse, 무관한 수정도 false positive 발생

### Method 2: LOCCO-style Period-Binned Recall [구현 난이도: Medium]
```
P1: 0-3일  |  P2: 4-14일  |  P3: 15-60일
P4: 61-180일  |  P5: 180일+
```
각 period에서 샘플링한 결정 k개에 대해 "관련 프롬프트" 생성 → recall@5 측정.
- 논문용 temporal decay curve 생성 가능
- **한계**: P3+ 분석은 6개월+ git history 필요

### Method 3: Decision Validity Ground Truth [구현 난이도: High]
4-class taxonomy:
```
VALID      — 현재도 그대로 적용됨
REFINED    — 방향은 맞으나 세부 구현 변경
OBSOLETE   — 해당 모듈/파일 삭제됨
INVERTED   — 명시적 반대 결정이 내려짐
```
Human annotation 30-50개 → Validity@5 = inject 상위 5결정 중 VALID 비율.

### Method 4: Temporal Contrastive Pairs [구현 난이도: Medium]
동일 파일/컴포넌트에 대한 시간 차이 있는 결정 pair (D_old, D_new) 구성.
- D_new가 D_old를 암묵적 무효화하는지 탐지
- Conflict Rate = inject된 결정 중 모순쌍 비율
- 예: "TF-IDF" 결정 (3달 전) vs "BM25로 교체" 결정 (1달 전)

### Method 5: LongMemEval-style Task-Conditioned Recall [구현 난이도: Medium]
실제 코딩 태스크 기반 쿼리 20-30개 구성 → NDCG@5로 시간 가중 순위 품질 측정.

## Implementation Roadmap

### 1주일 내
1. **Conflict Detection** (Method 4): inject_decisions.py에 conflict pair 탐지 레이어 추가 (4-6h)
2. **Staleness Flag** (Method 1 간소화): `[possibly outdated]` 마킹 (2-3h)

### 2-4주 (논문 품질)
3. **Validity Ground Truth** (Method 3): 30-50개 결정 직접 라벨링 + 분석 (5-6h)
4. **Period Recall Curve** (Method 2): 긴 history 프로젝트 사용 + decay graph 생성

## 논문 추천 지표 (우선순위 순)

| 지표 | 의미 | 방법 |
|------|------|------|
| **Validity@5** | inject 상위 5 중 VALID 비율 | Method 3 |
| **Conflict Rate** | inject 결정 중 모순쌍 비율 | Method 4 자동 |
| **Period-Recall Curve** | P1~P5 시간대별 recall decay | Method 2 |
| **Staleness-corrected Recall** | VALID 결정만 카운트한 보정 recall | Method 1+3 |

**논문 contribution 포지셔닝**: "recall 90%이지만 validity@5가 낮다면, 우리가 이 차원을 정의하고 해결한다" — weakness 발견이 contribution이 됨.

## Sources
- [Multi-Layered Memory Architectures for LLM Agents (arxiv 2603.29194)](https://arxiv.org/html/2603.29194)
- [Evaluating Very Long-Term Conversational Memory (LOCOMO)](https://snap-research.github.io/locomo/)
- [ZEP: Temporal Knowledge Graph for Agent Memory](https://blog.getzep.com/content/files/2025/01/ZEP__USING_KNOWLEDGE_GRAPHS_TO_POWER_LLM_AGENT_MEMORY_2025011700.pdf)
- [EvolveBench (ACL 2025)](https://aclanthology.org/2025.acl-long.788.pdf)
- [Time-Aware Language Models as Temporal Knowledge Bases](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00459/110012)

## Related
- [[projects/CTX/research/20260326-ctx-benchmark-validation-roadmap|20260326-ctx-benchmark-validation-roadmap]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
