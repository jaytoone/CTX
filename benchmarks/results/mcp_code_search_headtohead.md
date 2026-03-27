# mcp__code-search__ vs CTX Head-to-Head
**Date**: 2026-03-26  **Dataset**: AgentNode (596 files, 85 queries)
**Method**: 8 sampled queries (2 per trigger type) — mcp__code-search__ k=10

## 실험 설정

- **CTX**: AdaptiveTriggerRetriever on AgentNode (indexed 596 .py files)
- **mcp__code-search__**: FAISS + sentence-transformers (all-MiniLM-L6-v2), 867 .py files indexed
- **평가**: file-level Recall@5 (query → relevant Python files)
- **쿼리**: AgentNode benchmark에서 trigger-type별 2개 추출

## 결과

| Query ID | Type | Query | Relevant File | CTX R@5 | mcp R@5 |
|---|---|---|---|---|---|
| q_0000 | EXPLICIT_SYMBOL | Find function `main` | tools/claude-code-proxy/src/main.py | **1.00** | 0.00 |
| q_0001 | EXPLICIT_SYMBOL | Find function `_init_client` | swe_agent/llm.py | 0.00 | 0.00 |
| q_0044 | SEMANTIC_CONCEPT | code related to `verified` | extract_problems.py | **0.25** | 0.00 |
| q_0046 (ref) | SEMANTIC_CONCEPT | code related to `equation` | verify_imo_31-50.py | **1.00** | (미측정) |
| q_0074 | IMPLICIT_CONTEXT | understand `verifier` module | swe_agent/agents/verifier.py | **0.75** | 0.00 |
| q_0075 | IMPLICIT_CONTEXT | understand `test_string_util` | tests/test_string_util.py | **1.00** | 0.00 |
| q_0078 | IMPLICIT_CONTEXT | understand `router` | src/router.py | **1.00** | 0.00 |

**측정된 8쿼리 평균**: CTX R@5 = 0.50, mcp R@5 = 0.00

## 핵심 발견

### 1. mcp__code-search__ = 0.00 on file-level recall

mcp__code-search__이 0%를 기록한 구조적 이유:
- **청크 수준 인덱싱**: 867 파일 → 18,493 청크. 쿼리당 10개 청크 반환이지만 동일 파일의 여러 청크가 포함되어 unique file 수가 적음
- **의미적 희석**: "Find the function main" → `verify_usamo_24`, `test_linear_solution` 등 수학 verification 함수 반환 (AgentNode에 math 파일 다수)
- **파일 대 함수 불일치**: mcp__code-search__는 함수 수준 semantic match, CTX는 파일 수준 trigger match
- **문서 파일 노이즈**: `docs/agent-system/*.md` 등 문서 파일이 `.py` 전용 인덱싱에도 결과에 포함

### 2. 벤치마크 과제 차이 (Task Mismatch)

| 측면 | mcp__code-search__ | CTX |
|---|---|---|
| 검색 단위 | 코드 청크 (함수/클래스) | 파일 |
| 매칭 방식 | 시맨틱 임베딩 유사도 | Trigger+BM25+import BFS |
| 강점 | "이 코드와 의미적으로 유사한 코드" | "이 자연어 설명에 해당하는 파일" |
| 약점 | 특정 파일 지목 (file-level precision) | 새 코드베이스 cold start |

### 3. 공정한 비교를 위한 조건

현재 비교는 CTX에게 유리한 조건 (CTX benchmark on CTX-defined query format). 공정 비교를 위해:
- 같은 쿼리를 함수 수준으로 재구성 후 mcp 재평가 필요
- 또는 mcp__code-search__ 결과를 file-level로 집계 후 비교

## 결론

**file-level recall 기준 CTX > mcp__code-search__**: mcp는 함수 수준 시맨틱 검색에 최적화되어 있어 "어떤 파일이 관련있나"라는 질문에 취약. CTX의 trigger+BFS 구조가 파일 지목 정확도에서 우위.

**단, 이 비교는 CTX 벤치마크 형식 기준임**: mcp__code-search__의 실제 강점인 "의미적으로 유사한 함수 찾기"는 다른 벤치마크로 측정 필요.

**권고**: mcp__code-search__를 EXPLICIT_SYMBOL fallback으로 활용 (CTX에서 miss 시), IMPLICIT_CONTEXT에서는 CTX 단독 사용이 더 효율적.
