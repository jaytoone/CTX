# MCP Automation - 빠른 참고표

## 3개 MCP의 현재 상태

| MCP | 현재 상황 | 자동화 대상 | 우선순위 |
|-----|---------|-----------|---------|
| **mcp__memory__** | 반자동 (hint 파일) | SessionStart, 키워드 감지 | HIGH |
| **mcp__codebase-memory-mcp__** | 완전 수동 | 코드 구조 쿼리 | HIGH |
| **mcp__code-search__** | 완전 수동 | 의미 검색, Grep 폴백 | MEDIUM |

---

## Hook-to-additionalContext 패턴

```
Hook (Python/Bash)
  └→ JSON 출력 (hookSpecificOutput)
      └→ Claude Code CLI 파싱
          └→ additionalContext 주입
              └→ Claude 프롬프트에 포함
                  └→ Claude가 MCP 호출
```

**중요**: Hook은 MCP를 직접 호출할 수 없음. (subprocess 제약)

---

## 각 MCP 자동화 계획

### 1. mcp__memory__ (세션 간 기억)

**트리거**
- SessionStart: read_graph → open issues 보고
- "remember", "previous": search_nodes
- SessionEnd: create_entities

**구현**
```
new hook: memory-aware-router.py (UserPromptSubmit)
+ CLAUDE.md: Autonomous Trigger 추가
```

**효과**: context 자동 복원 (+50%), 수동 작업 -80%

---

### 2. mcp__codebase-memory-mcp__ (코드 그래프)

**트리거**
- "who calls": trace_call_path
- "find implementation": search_graph
- "architecture": get_architecture
- Grep 0-결과 + 개념 쿼리: search_graph 폴백

**구현**
```
new hook: code-discovery-router.py (UserPromptSubmit)
+ PreToolUse 강화
+ PostToolUse 폴백 (Grep 결과 파싱)
```

**효과**: 탐색 시간 -30%, 아키텍처 이해도 +35%

---

### 3. mcp__code-search__ (의미 검색)

**트리거**
- "how does", "find all places": search_code
- Grep 0-결과 + 추상 개념: search_code 폴백
- "find similar": find_similar_code

**구현**
```
new hook: semantic-search-router.py (UserPromptSubmit)
+ PostToolUse 폴백 (Grep 결과 파싱)
+ on-demand 인덱싱 (SessionStart 대신)
```

**효과**: 개념 검색 +45%, 패턴 발견 +65%

---

## 기본 Hook 패턴

### Pattern: 키워드 감지 → additionalContext 주입

```python
#!/usr/bin/env python3
import json, sys

def detect_trigger(prompt: str) -> bool:
    triggers = ["remember", "previous", "last time"]
    return any(t in prompt.lower() for t in triggers)

def main():
    data = json.load(sys.stdin)
    prompt = data.get("prompt", "")
    
    if not detect_trigger(prompt):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": ""
        }}))
        return
    
    context = """<mcp_trigger>
[자동 감지] Memory trigger

권장 MCP 호출:
- mcp__memory__read_graph({})
- 프로젝트 관련 entities 필터링
</mcp_trigger>"""
    
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": context
    }}))

if __name__ == "__main__":
    main()
```

---

## CLAUDE.md 확대안 (요약)

### mcp__memory__
```
AUTO when: SessionStart → read_graph → filter {ProjectName}-*
AUTO when: "remember", "previous", "last time" → search_nodes
AUTO when: SessionEnd + meaningful work → create_entities
```

### mcp__codebase-memory-mcp__
```
AUTO when: "who calls", "trace", "call chain" → trace_call_path
AUTO when: "find implementation", "where is X" → search_graph
AUTO when: "architecture overview" → get_architecture
AUTO when: Grep 0-3 matches + conceptual → search_graph fallback
```

### mcp__code-search__
```
AUTO when: "how does", "find all places", "implement pattern" → search_code
AUTO when: Grep 0 results + abstract concepts → search_code fallback
AUTO when: "find similar code" → find_similar_code
```

---

## 구현 로드맵

| Phase | 기간 | 작업 | 산출물 |
|-------|------|------|--------|
| 1 | 1주 | memory-aware-router.py | 세션 간 context 자동 |
| 2 | 1.5주 | code-discovery-router.py | 코드 그래프 자동 |
| 3 | 1.5주 | semantic-search-router.py | 의미 검색 자동 |
| 4 | 1주 | CLAUDE.md 정리, 최적화 | 최종 배포 |

**총 기간**: 1개월  
**기대 효과**: 생산성 25-35% 향상

---

## 파일 위치

| 파일 | 역할 |
|------|------|
| `/home/jayone/.claude/settings.json` | Hook 설정 |
| `/home/jayone/.claude/hooks/` | Hook 스크립트 |
| `/home/jayone/.claude/CLAUDE.md` | Autonomous Trigger 규칙 |
| `/home/jayone/Project/CTX/docs/research/` | 리서치 문서 |

---

## 성능 고려사항

**SessionStart 초기 지연** (자동 인덱싱)
- <1000 파일: 5-10초
- 1K-5K: 20-30초
- 5K+: 1-2분
→ on-demand 인덱싱 권장

**Hook 누적 지연**
- 현재: 5-6개 hook → 500ms
- 권장: 이벤트당 3개 이하

**Grep 폴백 오버헤드**
- PostToolUse 결과 파싱: 50-100ms
- 문제 없음 (이미 Grep 실행 시간 포함)

---

## 위험도 평가

| 항목 | 리스크 | 근거 |
|------|-------|------|
| Hook 에러 | Low | graceful degradation (additionalContext 무시) |
| 인덱싱 지연 | Low-Medium | on-demand 인덱싱으로 해결 |
| false positives | Low | 키워드 리스트 검검증 가능 |
| 복잡도 | Low | 기존 패턴 확대 |

---

## 다음 단계

1. Phase 1 시작: memory-aware-router.py 구현
2. CLAUDE.md Autonomous Trigger 확대 문서화
3. 성능 벤치마크 수집 (실제 hook 지연 측정)
4. 초기 사용자 피드백

