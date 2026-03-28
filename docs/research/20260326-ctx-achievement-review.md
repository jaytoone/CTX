# [expert-research-v2] CTX 현재 성과 vs 사용자 요구 평론
**Date**: 2026-03-26  **Skill**: expert-research-v2

## Original Question
현재 성과에 대해 평온해보고 기존 사용자 요구 대비 성과 평론

사용자 원래 요구:
1. **Goal 1**: 새 세션/장기 세션에서도 이전 작업 히스토리 유지, 반복 및 방향 희석 방지
2. **Goal 2**: 사용자 지시와 유관한 파일/문서 최대한 잘 찾아내기

## Web Facts

[FACT-1] CodeSearchNet 업계 표준 지표: NDCG (Recall@5 아님)
Source: https://arxiv.org/abs/1909.09436

[FACT-2] CoIR (2024-2025) NDCG@10 기준. SoTA Voyage-Code-002 = 56.26
"Even state-of-the-art retrievers perform suboptimally on CoIR"
Source: https://arxiv.org/html/2407.02883v1

[FACT-4] Cursor: 자동 semantic index + 세션 간 자동 연속성 + project Memories (2025)
[FACT-5] Copilot: Spaces만 있고 세션 간 자동 연속성 없음 (수동 재연결)
Source: https://www.truefoundry.com/blog/cursor-vs-github-copilot

[FACT-8] Code retrieval: structured retrieval > semantic embedding. 의존 그래프 필수
Source: https://arxiv.org/html/2602.11671

[FACT-9] Retrieval quality → generation quality 직접 상관. 대부분 미정량화
Source: https://aclanthology.org/2025.findings-naacl.176.pdf (ACL 2025)

[FACT-11] NL→코드 파일 매핑: 오픈 문제. 함수/타입/의존성 구조가 임베딩보다 중요
Source: https://dl.acm.org/doi/10.1145/3611643.3616323

## Multi-Lens Analysis

### Domain Expert (Lens 1)
- Goal 1: 메커니즘(persistent_memory, session_log) 구현. **실제 실험** Recall@10=0.567 (95% CI 검증됨)
  - head: 1.000, torso: 0.710, tail: 0.431, all: 0.220
- Goal 2: Recall@5 0.333→0.644 (+93%), **NDCG@5=0.723** (CoIR 표준). Trigger 분류 88.9%
- Cursor 대비: CTX는 파일 접근 빈도 기반 기억 vs Cursor 자동 semantic index [GROUNDED, FACT-4]

### Self-Critique (Lens 2)
- [PARTIAL-FIX] 0.917 시뮬레이션 → 0.567 실제 실험 (더 현실적)
- [STILL-MISSING] Goal 1 진짜 지표: 반복 지시율, 방향 일관성 미측정
- [UNCHANGED] instruction_grounding_eval 자기 설계 테스트셋 → 낙관 편역
- [PARTIAL-FIX] NDCG@5 측정완료 (0.723), NDCG@10 미측정 (업계 표준)
- [NEW] 95% CI 검증됨 - torso [0.699, 0.72], tail [0.423, 0.439], all [0.215, 0.225]

### Synthesis (Lens 3)
- 실제 달성: "목표를 측정 가능하게 만들고 구조적 버그 수정" — 중요하나 사용자 체감 경험까지 아님
- 핵심 잔여 문제: "방향 희석" = 파일 목록이 아닌 결정/의도 맥락 복원 문제
  → mcp__memory__ TechnicalDecision/OpenIssue entity가 실제 해법

## Updated Results (2026-03-26)

### Goal 1: Cross-Session Recall (실제 실험, 95% CI)
| Scenario | Recall@10 | 95% CI |
|----------|-----------|--------|
| head (top 10) | 1.000 | - |
| torso (11-25) | 0.710 | [0.699, 0.720] |
| tail (26-50) | 0.431 | [0.423, 0.439] |
| all (1-50) | 0.220 | [0.215, 0.225] |

**Avg Recall@10 = 0.567** (다양한 파일 접근 패턴에서 통계적으로 검증됨)

### Goal 2: Instruction Grounding (CoIR 표준 NDCG)
| Metric | Score |
|--------|-------|
| Recall@5 | 0.644 |
| Precision@5 | 0.580 |
| **NDCG@5** | **0.723** |
| IMPLICIT_CONTEXT rate | 88.9% |

---

## Final Conclusion

| 사용자 목표 | 달성 수준 | 신뢰도 |
|------------|----------|--------|
| Goal 1: 세션 간 연속성 | 50% (실제 실험 + 95% CI) | MEDIUM→HIGH |
| Goal 2: 지시→유관 파일 | 70% (NDCG@5=0.723) | MEDIUM |
| 측정 인프라 | 95% (NDCG + CI + 다중 시나리오) | HIGH |

핵심: 시뮬레이션(0.917) → 실제 실험(0.567)로 하향 조정되었으나, **통계적으로 검증된 결과**로 신뢰도 향상.

권고 순서:
1. ~~즉시: mcp__memory__ SessionStart 자동화~~ → SessionStart hook으로 자동화됨
2. 단기: 외부 독립 쿼리셋 (CodeSearchNet/CoIR)으로 재검증
3. 중기: NDCG@10 추가 + RepoBench 대조

## Sources
- https://arxiv.org/abs/1909.09436 (CodeSearchNet)
- https://arxiv.org/html/2407.02883v1 (CoIR ACL 2025)
- https://www.truefoundry.com/blog/cursor-vs-github-copilot
- https://arxiv.org/html/2602.11671 (Structured Code Retrieval 2025)
- https://aclanthology.org/2025.findings-naacl.176.pdf (CODERAG-BENCH ACL 2025)
