# [expert-research-v2] auto-index.py 필요성 분석
**Date**: 2026-04-11  **Skill**: expert-research-v2

## Original Question
auto-index.py (~/.claude/hooks/auto-index.py) 의 기능과 필요성 분석.
현재 CTX hook 아키텍처(bm25-memory.py가 G1+G2 담당) 맥락에서 auto-index.py가 실제로 필요한지, 중복인지, 제거 가능한지.

## Findings

### 기능
- SessionStart: codebase-memory-mcp DB가 없거나 >24h old면 `additionalContext`에 재인덱싱 힌트 주입
- PostToolUse(git commit*): 항상 --force 힌트 주입
- 출력: `mcp__codebase-memory-mcp__index_repository(repo_path=..., mode="fast")` 실행 요청

### 실증적 증거
- DB 현황: home-jayone-Project-CTX.db, 3.7MB, **116h old** (4.8일)
- 최근 커밋 10회 이상에도 DB 갱신 안 됨 → 힌트가 실행되지 않음
- DB 내용: 2,026 nodes (284 functions, 178 methods), 3,329 edges — 유효 데이터 있음

### 의존성 체계
```
auto-index.py → (hint) → Claude → mcp__codebase-memory-mcp__index_repository
                                        ↓
bm25-memory.py G2b → search_graph_for_prompt() [DB 있을 때]
                   → search_files_by_grep()     [fallback, 항상 동작]
```

## Final Conclusion

**auto-index.py = vestigial hook** — 힌트를 출력하지만 Claude가 대부분 무시함.
DB가 4.8일 stale임에도 자동 갱신 불가 (구조적 한계: hooks는 MCP 직접 호출 불가).

**권고**: 제거해도 G2b git grep fallback으로 커버. DB가 있을 때의 graph search 가치는 실재하나,
힌트 방식으로는 freshness 보장 불가. 세션 시작 토큰 오버헤드 절약 목적으로 제거 권고.

## Sources
- `/home/jayone/.claude/hooks/auto-index.py` (직접 분석)
- `/home/jayone/.claude/settings.json` (hook 연결 구조)
- `~/.cache/codebase-memory-mcp/home-jayone-Project-CTX.db` (실증 데이터)
- `/home/jayone/.claude/hooks/bm25-memory.py` (G2b 의존성 구조)

## Related
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
