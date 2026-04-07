# [expert-research-v2] 전역 CLAUDE.md 비판적 평론
**Date**: 2026-04-07  **Skill**: expert-research-v2

## Original Question
현재 전역 CLAUDE.md (~/.claude/CLAUDE.md)의 효율성, 정확성, 중복성, 실용성에 대한 날카로운 비판적 평론.
무엇이 잘 작동하는지, 무엇이 과잉/중복/모순인지, 무엇을 제거해야 하는지 구체적으로 분석.

## Web Facts
[FACT-1] CLAUDE.md에는 약 150-200개 instruction budget 제한이 있으며, system prompt가 이미 ~50개를 사용. 이 한도 초과 시 준수율 급락. (source: HumanLayer Blog)
[FACT-2] CLAUDE.md는 advisory — Claude가 ~80%만 따름. 100% 준수가 필요한 규칙은 Hook으로 구현해야 함. (source: HumanLayer Blog)
[FACT-3] "Claude 없이 잘못하지 않을 모든 줄은 노이즈다" — 필요한 줄만 남겨야 중요한 규칙이 희석되지 않음. (source: HumanLayer/uxplanet)
[FACT-4] 파일 크기 <200줄 권장. 도메인별 가이드는 별도 파일로 분리 후 링크만 포함. (source: uxplanet)
[FACT-5] Skills는 관련 작업 시에만 로드 — context를 lean하게 유지. (source: Official Claude Code Docs)
[FACT-6] 더 많은 context ≠ 더 좋은 결과. 과도한 context는 오히려 모델을 산만하게 만들어 목표 이탈 유발. (source: DEV community)

## Multi-Lens Analysis

### Domain Expert (Lens 1)

**1. 규칙 번호 중복 버그 (HIGH)**
Prohibited Patterns에서 번호 7이 두 번 사용됨 (Node.js 프로세스 금지 + git commit 금지).
실제 항목 수는 11개이나 10번까지만 표기. 규칙 참조 모호성 + 문서 품질 신뢰도 저하.

**2. 훅으로 강제 가능한 규칙이 advisory로만 존재 (HIGH)**
`npm run build` 금지, git commit 무승인 금지, Korean/multibyte filename 금지 —
모두 PreToolUse/PostToolUse 훅으로 100% 강제 가능. 현재는 CLAUDE.md advisory(80% 준수).
나머지 20%에서 위반 시 실제 피해 발생 (의도치 않은 커밋, 빌드 충돌).

**3. Dev Server Restart 규칙과 Prohibited Patterns 7번 충돌 (HIGH)**
Prohibited Patterns 7번: "포트 충돌 시 다른 포트 사용 또는 사용자에게 알리라"
Dev Server Restart 섹션: `lsof -ti:<port> | xargs kill` (무승인 프로세스 종료)
두 규칙이 동시에 만족 불가 — 모델의 비결정적 판단에 위임됨.

**4. 파일 규모 250줄+ (MEDIUM)**
[FACT-4] 200줄 권장 대비 초과. Supabase Checklist(~50줄), Vercel Checklist(~20줄),
API Key Store(~20줄)는 도메인별 외부 파일로 분리 가능한 내용.

**5. git-memory 섹션 언어 혼재 (MEDIUM)**
전체 문서 중 유일하게 한국어로 작성된 섹션. 문서 내 언어 일관성 훼손.

### Self-Critique (Lens 2)

- [OVERCONFIDENT] 섹션 순서/중요도 가중치 효과 — 실증 데이터 없는 추론
- [MISSING] 훅-CLAUDE.md 중복은 fallback 안전망으로서 긍정적 측면도 있음 (훅 실패 시)
- [CONFLICT] API Key/Supabase 섹션이 이미 일부 외부 파일 링크로 분리 시도 중
- [MISSING] "Auto-check Routine"의 placeholder (`PGPASSWORD="..."`)는 실제 실행 불가 상태

### Synthesis (Lens 3)

P0 즉시 수정, P1 단기, P2 중기 권고 사항은 아래 Final Conclusion 참조.

유지 권장 섹션: MCP Tool Hierarchy (T4 banned list가 실제 오류 기반),
UTF-8 Safety (실제 Rust 버그 기반), Browser RPA (세션 fallback 로직 구체적),
Autonomous Tool Triggers (deterministic signal 명확히 구분됨).

## Final Conclusion

### P0 — 즉시 수정 (모순/버그)

1. **번호 중복**: 두 번째 "7"을 "8"로 변경, 이후 8→9, 9→10, 10→11로 재번호
2. **규칙 충돌 해소**: Dev Server Restart 섹션에 단서 추가:
   `lsof -ti:<port> | xargs kill  # 사용자 승인 후 실행, Node.js 프로세스 포함 시 명시적 확인`

### P1 — 단기 개선 (준수율 80% → 100%)

3. 훅으로 이전할 규칙 3개:
   - `npm run build` 금지 → PreToolUse(Bash) 훅 패턴 매칭
   - git commit 무승인 금지 → 이미 훅 구조가 있으므로 통합
   - CLAUDE.md에서 삭제 또는 "(훅으로 강제됨)"으로 대체

4. git-memory 섹션 영어로 번역 (언어 일관성)

### P2 — 중기 개선 (파일 크기 200줄 이하로 압축)

5. `Centralized API Key Store` → `~/.claude/env/README.md`로 이동 (20줄 → 1줄 링크)
6. `Supabase/Vercel Checklist` → `~/.claude/tool-hints/external-services.md`로 분리 (50줄 → 2줄 링크)
7. `Auto-check Routine` placeholder 수정 또는 섹션 삭제 (현재 실행 불가 상태)

### 유지 (변경 불필요)

- MCP Tool Hierarchy (T4 banned list는 실제 오류 기반 — 높은 신호 밀도)
- UTF-8 & Multibyte Safety (실제 Rust 버그 유래)
- Browser RPA & Playwright Rules (4개 세션 fallback 로직 구체적)
- Autonomous Tool Triggers ([GREP-FALLBACK] deterministic signal 명확)

## Sources
- [Writing a good CLAUDE.md | HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [CLAUDE.md Best Practices | UX Planet](https://uxplanet.org/claude-md-best-practices-1ef4f861ce7c)
- [Best Practices for Claude Code - Official Docs](https://code.claude.com/docs/en/best-practices)
- [AI Coding Prompts Best Practices 2026 | DEV Community](https://dev.to/albertsalgueda/best-ai-prompts-for-developers-in-2026-the-complete-guide-to-ai-assisted-coding-38h0)
