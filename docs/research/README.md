
---

## 2026-03-25: MCP Tool Automation Research (신규)

**파일**:
- `MCP_AUTOMATION_RESEARCH.md` - 상세 리서치 (286줄)
- `QUICK_REFERENCE.md` - 빠른 참고표 (212줄)

**개요**:
3개 MCP(mcp__memory__, mcp__codebase-memory-mcp__, mcp__code-search__)의 자동화 방안을 리서치했다.

**핵심 발견**:
1. Hook-to-additionalContext 패턴이 기존 인프라로 충분히 지원
2. MCP 직접 호출 불가능 (subprocess 제약) → additionalContext 힌트 주입이 유일 경로
3. 성공 사례들(stream_router.py, graphprompt-augment.py, ctx_loader.py)이 명확한 패턴 제시

**결론**:
- 기술적 실현 가능성: HIGH/MEDIUM-HIGH
- 투자: 1개월 (4주)
- 기대 효과: 생산성 25-35% 향상
- 리스크: Low (기존 패턴 확대)

**다음 단계**:
Phase 1 (1주): memory-aware-router.py 구현
