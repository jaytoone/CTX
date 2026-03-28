# [expert-research-v2] CTX vs Claude Code 내장 도구 대비 성능 비교
**Date**: 2026-03-26  **Skill**: expert-research-v2

## Original Question
CTX는 Claude Code 환경에서 Goal 1/2와 동일한 기능을 수행하는 내장 도구들 대비 성능이 어느 정도인가?
- Goal 1 (Cross-session memory): Cross-session R@10=0.567, Doc R@5=0.933, DRR@3=1.000
- Goal 2 (Instruction-grounded retrieval): AgentNode R@5=0.522, NDCG@5=0.723, TES=0.776

## Web Facts

[FACT-1] Claude Code memory = CLAUDE.md (수동, 전체 로드) + auto MEMORY.md (200-line limit, 세션 시작 시 전체 주입). 크로스 세션 파일 검색 메커니즘 없음 — 텍스트 노트만 저장.
Source: code.claude.com/docs/en/memory

[FACT-2] mcp__memory__ = 지식 그래프 MCP (entities/relations). TechnicalDecision/OpenIssue 저장. 파일 임베딩/BFS 탐색 없음 — "무엇이 결정됐나"는 알지만 "어떤 파일이 지금 유관한가"는 탐색 불가.
Source: Anthropic MCP documentation

[FACT-3] Claude Code 기본 검색 = agentic Grep/Glob/Read (벡터 인덱싱 없음). Anthropic 내부 평가: "agentic search가 RAG보다 훨씬 좋음." Amazon Science Feb 2026: 에이전틱 키워드 검색이 RAG 성능의 >90% 달성 (태스크 완료율 기준, Recall@K 아님).
Source: Amazon Science blog Feb 2026

[FACT-4] 시맨틱 검색 MCP 대안 vs 네이티브:
- mgrep/grepai: 토큰 2x 감소, 입력 토큰 97% 감소, 도구 호출 ~30% 감소
- 단: Recall@K 표준 벤치마크 수치 미발표
Source: developer blog posts, GitHub READMEs

[FACT-5] mcp__codebase-memory-mcp__: "99% fewer tokens, sub-ms queries, 64 languages" — 구조적 쿼리 (trace_call_path, architecture) 특화. 자연어→파일 시맨틱 검색에는 설계되지 않음.
Source: github.com/DeusData/codebase-memory-mcp

[FACT-6] CTX: 트리거 기반 (EXPLICIT_SYMBOL/SEMANTIC_CONCEPT/TEMPORAL_HISTORY/IMPLICIT_CONTEXT), BM25+TF-IDF+import BFS 하이브리드, LLM 호출 없음, avg RT=117ms. 코드+문서 통합 인덱싱 (154파일: 99 .py + 55 .md).

[FACT-7] CTX vs BM25: Cohen's d=0.955 (large effect), p<0.0001. RepoBench-R NDCG@10=0.646 (BM25 ~0.528, +11.8pp).

## Multi-Lens Analysis

### Domain Expert (Lens 1)

**Goal 1 — CTX는 네이티브 스택이 전혀 해결하지 않는 니치를 차지** [GROUNDED]
CLAUDE.md + MEMORY.md는 "세션 시작 시 전체 텍스트 주입" 구조로, 지식이 커질수록 S/N비 선형 하락. mcp__memory__는 결정 요약을 저장하나 파일 임베딩 없음. CTX의 DRR@3=1.000 + Doc R@5=0.933은 단일 쿼리로 코드+문서+결정 3-way join을 수행 — 네이티브 스택에서는 불가.

*Steel-man*: 전문가가 작성한 CLAUDE.md는 실제로 중요한 결정을 정확히 포함할 수 있어 precision이 높음.

**Goal 2 — CTX는 키워드 기준선 대비 검증됨, 시맨틱 MCP 대비는 미지** [GROUNDED + UNCERTAIN]
NDCG@5=0.723 (1.89x BM25), IMPLICIT_CONTEXT R@5=0.715~1.0은 실측값. 그러나 mcp__code-search__ (벡터 시맨틱 검색) 대비 head-to-head 없음. FACT-3의 "agentic search >90% RAG" 주장은 CTX vs 네이티브 에이전틱 검색 갭이 BM25 갭보다 훨씬 작을 수 있음을 시사.

**RT 117ms 결정론적 실행** [GROUNDED]
UserPromptSubmit 훅에서 LLM turn 전에 발화 → 에이전트 루프 지연 0. mcp__codebase-memory-mcp__의 "sub-ms"는 그래프 구조 탐색 (다른 문제). 단, 인터랙티브 세션에서 500ms MCP 지연은 사용자에게 무지각 수준 — 정확도가 높으면 지연 비용은 경제적으로 irrelevant.

**통합 코드+문서 인덱싱 (154파일)** [REASONED]
네이티브: Grep(코드) + Read(문서) + mcp__memory__(결정) + CLAUDE.md(수동) — 4개 시스템 분산. CTX는 단일 쿼리로 4-way 통합. import BFS로 함수→임포터→공동 문서 다중 홉 탐색 (네이티브는 3+ 순차 호출 필요).

**mcp__memory__ + CTX 보완 관계** [REASONED]
mcp__memory__: 결정 *이유*를 구조화 저장. CTX: 결정과 연결된 *파일 증거*를 서페이싱. 경쟁이 아닌 보완 — 완전한 크로스 세션 시스템은 둘 다 필요.

### Self-Critique (Lens 2)

**[OVERCONFIDENT]** "CTX가 네이티브 도구보다 우수" 주장:
1.89x BM25는 실측이지만, 네이티브 agentic Grep은 BM25가 아님 — LLM이 쿼리를 재구성하고 결과를 체이닝하는 adaptive search. FACT-3의 Amazon Science 주장이 맞다면 CTX vs 네이티브 실제 갭은 훨씬 작을 수 있음.

**[MISSING]** 벤치마크 분포 불일치:
CTX 수치는 AgentNode/CTX 코드베이스 (154파일) 내부 평가. Claude Code 평가는 다른 태스크/분포. 공유 벤치마크 head-to-head 없음 — 모든 비교는 크로스 벤치마크 외삽.

**[MISSING]** CTX 토큰 비용 미측정:
트리거당 5-10 파일 주입 시 2,000~10,000 토큰 소비 추정. 네이티브 에이전틱 검색은 reactive (필요할 때만 호출). tokens-per-correct-retrieval 메트릭 없이 효율성 주장 불완전.

**[CRITICAL]** R@10=0.567의 의미:
크로스 세션 관련 파일의 43%가 top-10에서 누락. Goal 1 핵심 메트릭으로서 이는 상당한 한계 — "연속성"을 표방하면서 43% miss rate는 peer review 공격 포인트.

### Synthesis (Lens 3)

**Goal 1**: CTX는 native에 없는 file retrieval 기능 제공, 단 R@10=0.567 한계 명시 필요. 실용 배포: CTX + mcp__memory__ 콤보 (CTX=파일 서페이싱, mcp__memory__=결정 이유).

**Goal 2**: IMPLICIT_CONTEXT 클래스에서 CTX 명확 우위 (키워드 검색 완전 실패 영역). EXPLICIT_SYMBOL 쿼리는 native Grep과 비슷하거나 native가 낮은 토큰 비용으로 매칭 가능. 최적 전략: implicit/semantic → CTX, explicit symbol → Grep.

**최대 미지수**: mcp__code-search__ (시맨틱 벡터) vs CTX head-to-head — 이것이 Goal 2 포지셔닝의 핵심 데이터 포인트.

## Final Conclusion

### 성능 비교 테이블

| 차원 | CTX | Claude Code 네이티브 스택 | 평가 |
|------|-----|--------------------------|------|
| Cross-session 파일 recall | R@10=0.567 | 해당 기능 없음 | CTX 독보적 (단, 57% 수준) |
| 결정 기억 | DRR@3=1.000 | mcp__memory__ (구조화, 비랭킹) | 상호 보완 |
| 시맨틱 파일 검색 | NDCG@5=0.723 | mcp__code-search__ (미측정) | CTX 그라운드, 경쟁자 미지 |
| 키워드 검색 | 1.89x BM25 | Agentic Grep (>90% RAG 주장) | 갭 미확인 |
| IMPLICIT_CONTEXT | R@5=0.715~1.0 | 키워드 검색 실패 영역 | CTX 명확 우위 |
| 구조/의존성 탐색 | 설계 범위 외 | mcp__codebase-memory-mcp__ (sub-ms) | Native 명확 우위 |
| 지연 (latency) | 117ms 결정론적 | 가변, 에이전트 턴 의존 | CTX 예측 가능성 우위 |
| 토큰 오버헤드 | 미측정 (eager injection) | Adaptive (reactive) | Native likely 우위 |

### 핵심 결론

1. **Goal 1**: CTX는 네이티브 스택이 전혀 제공하지 않는 기능을 채움. 단, R@10=0.567은 "57% 연속성" — 완전한 크로스 세션 해법이 아님. CTX + mcp__memory__ 조합이 현실적 최선.

2. **Goal 2**: CTX의 BM25 대비 우위는 실증됨. 그러나 네이티브 agentic Grep 또는 mcp__code-search__ 대비 우위는 미확인. IMPLICIT_CONTEXT 특화 강점은 논문 포지셔닝에 활용 가능.

3. **논문 포지셔닝 권고**: "Claude Code 네이티브 도구 대비 우수"보다 "네이티브 스택이 해결 못하는 trigger-driven 통합 retrieval 구현"으로 포지셔닝. 1.89x BM25는 cite, 네이티브 agentic 비교는 future work.

### 즉시 실행 항목

| 우선순위 | 작업 | 목적 |
|---------|------|------|
| P0 | mcp__code-search__ vs CTX head-to-head (NDCG@5) | Goal 2 최대 미지수 해소 |
| P0 | CTX 토큰 비용 측정 (tokens/query, files injected/trigger) | 효율성 주장 완성 |
| P1 | R@10=0.567 trigger-type별 분해 | Goal 1 약점 파악 |
| P2 | CoIR 제출 (pip install coir-eval) | Goal 2 외부 독립 검증 |

## Sources
- [Amazon Science blog Feb 2026 — Agentic code search](https://www.amazon.science)
- [mcp__codebase-memory-mcp__ GitHub](https://github.com/DeusData/codebase-memory-mcp)
- [CoIR benchmark (ACL 2025)](https://github.com/CoIR-team/coir)
- [Claude Code Memory docs](https://code.claude.com/docs/en/memory)
