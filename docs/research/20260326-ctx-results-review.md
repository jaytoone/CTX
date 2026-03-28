# [expert-research-v2] CTX 성과 평론 — 상위 논문 수준 달성 여부
**Date**: 2026-03-26  **Skill**: expert-research-v2

## Original Question
CTX 실험 결과가 상위 논문(ICSE/FSE/EMNLP) 수준인지 종합 평가

## Web Facts
- [FACT-1] ICSE/FSE 2025 acceptance rate: ~20% (novelty + rigor + reproducibility 필수)
- [FACT-2] CoIR SOTA: CodeXEmbed 7B = 67.41 NDCG@10, Voyage-Code-002 = 56.26
- [FACT-3] MemoryArena (Feb 2026): multi-session memory 전용 벤치마크 — CTX 미평가
- [FACT-4] SWE-bench: 2025-2026 코드 에이전트 평가 표준 — CTX 미평가
- [FACT-5] TES는 저자 정의 지표 — 문헌에서 미사용

## Multi-Lens Analysis

### Domain Expert (Lens 1) — 5 Key Insights

1. **IMPLICIT_CONTEXT Recall@5=1.000 (vs BM25=0.4)**: 핵심 기여. import graph BFS가 구조적 의존성을 캡처하는 실제 차별화 포인트. [GROUNDED]

2. **TES=0.776 (BM25 1.9x)**: 토큰 효율성에서 실질적 이점. BM25 대비 3.6x 토큰 절감. [REASONED — TES는 비표준 지표]

3. **실제 코드베이스 7개 통계 검증**: p=0.016, Cohen's d=-0.485. 95% CI, Wilcoxon 테스트 포함. 방법론 정직함. [GROUNDED]

4. **Cross-Session Recall**: 소규모=0.917, 실제 avg=0.166. 업계(Cursor/Copilot/Windsurf) 모두 미공개 → 비교 불가하지만 CTX가 유일하게 수치 공개. [REASONED]

5. **Hook 통합 86.7% CHR, 120ms**: 실제 배포 검증. 엔지니어링 기여. [GROUNDED — 단일 환경 측정]

### Self-Critique (Lens 2) — 4 Substantive Flaws

**Flaw 1 [OVERCONFIDENT]: 합성→실제 성능 붕괴 (0.874 → 0.166)**
- 5x 성능 차이는 "해결"이 아닌 "일반화 실패" 신호
- 어느 컴포넌트가 실제 코드베이스에서 실패하는지 분석 없음

**Flaw 2 [OVERCONFIDENT]: TES는 순환 자기홍보 지표**
- 저자가 CTX의 토큰 절감 이점을 관찰한 후 설계한 지표
- 독립 검증 없음, 문헌 미사용

**Flaw 3 [CONFLICT]: 통계 프레임 역방향**
- p=0.016은 BM25가 CTX보다 유의하게 우수함을 확인
- Cohen's d=-0.485 음수 방향 = CTX 열세
- "CTX 검증"으로 제시하는 것은 방법론적 오표현

**Flaw 4 [MISSING]: 주요 베이스라인 누락**
- SWE-bench: 코드 에이전트 평가 표준 (2025-2026) 미평가
- MemoryArena: Goal 1과 직접 일치 벤치마크 미평가
- COIR 공식 30쿼리 내부 평가 → 재현 불가, SOTA 비교 불가

### Synthesis (Lens 3) — Venue Verdict

| 베뉴 | 가능성 | 주요 이유 |
|------|--------|---------|
| ICSE/FSE Research Track | 15–25% | 합성/실제 붕괴 + TES 문제 치명적 |
| EMNLP/ACL System Track | 10–15% | COIR 공식 평가 없음 |
| **MSR / SANER / ICSME** | **45–60%** | 툴 논문 + 경험적 SE 적합 |
| **LLM4Code / NLBSE Workshop** | **75–85%** | 아이디어 강력, 평가 보완 전 |

## Final Conclusion

### 핵심 강점 (논문 기여 가치 있음)
- Import graph 기반 IMPLICIT_CONTEXT 해결 — 구조적으로 이전 시스템이 못하는 것
- 토큰 효율성 실증 (5.2% 사용)
- 7개 실제 코드베이스 + 통계 검증

### 3 Must-Fix Before Submission
1. **합성→실제 붕괴 설명**: 트리거별 실제 코드베이스 성능 분석 필수
2. **TES 대체**: 고정 토큰 예산 비교 또는 SWE-bench 같은 다운스트림 태스크 메트릭
3. **COIR 공식 평가**: 30쿼리 내부 평가 제거 또는 공식 leaderboard 제출

### Publication Readiness
- **Top-tier (ICSE/FSE)**: NOT READY — 6–12개월 추가 작업 필요
- **MSR/Workshop**: READY with minor framing revision

## Sources
- CoIR Leaderboard: https://archersama.github.io/coir/
- MemoryArena: https://memoryarena.github.io/
- SWE-bench: https://www.swebench.com/

## Related
- [[projects/CTX/research/20260324-ctx-methodology-critique-top-tier|20260324-ctx-methodology-critique-top-tier]]
