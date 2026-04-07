# [expert-research-v2] 훅/스킬 강제 규칙의 CLAUDE.md 중복 기재 득실
**Date**: 2026-04-07  **Skill**: expert-research-v2

## Original Question
CLAUDE.md에서 훅(hook)이나 스킬(skill)로 이미 강제 실행되는 동작은 재언급할 필요가 없는가?
"훅/스킬로 강제되는 규칙은 CLAUDE.md에서 제거해야 하는가?"

## Web Facts
[FACT-1] Instruction budget: 150-200 instructions before compliance drops. 200줄 초과 시 규칙이 noise에 묻힘.
[FACT-2] CLAUDE.md ~80-90% compliance vs hooks 100%. 10% gap은 critical ops에서 실제 피해.
[FACT-3] Defense in depth: hook + CLAUDE.md 동시 존재 시 모델이 더 일찍 규칙을 준수. (HumanLayer/dotzlaw 2026)
[FACT-4] Decision rule: failure = money/security/compliance → hook. formatting/style → prompt. (HumanLayer)
[FACT-5] "LLM handles understanding, hook handles enforcement — neither replaces the other." (Fleek 2026)
[FACT-6] Prompt injection can override advisory instructions — security-critical = infrastructure level.
[FACT-7] "CLAUDE.md should contain as few instructions as possible." (HumanLayer)

## 핵심 구분: 유형 A vs 유형 B

| 유형 | 정의 | 예시 |
|------|------|------|
| **유형 A** | 모델이 실행할 수 있는 행동을 훅이 차단 | git commit 금지, npm run build 금지, node.exe kill 금지 |
| **유형 B** | 모델 선택과 무관하게 훅이 자동 실행 | SessionStart read_graph, graphprompt 자동 주입, auto-index |

## Multi-Lens Analysis

### Domain Expert (Lens 1)
- 유형 B: 순수 노이즈 (instruction budget 낭비). 단, 훅 실패 fallback 필요성은 케이스별 검토.
- 유형 A: Defense in depth 적용 → 제거 아닌 단축. 모델이 tool call 전에 자기억제 → 실행 비용↓
- 유형 A: 훅 없는 환경(CI, 다른 개발자 머신)에서 CLAUDE.md가 유일한 보호막
- 유형 A: 보안-critical 규칙은 훅에서 처리, CLAUDE.md는 1줄 "리마인더" 수준으로 충분

### Self-Critique (Lens 2)
- 유형 B "순수 노이즈" 판단이 과신 → 훅 실패 시 fallback 가치 있는 항목은 단축 유지 가능
- 훅 실패 모드 분석 누락: retry 로직, MCP 서버 다운 시나리오 미정량화
- FACT-5("neither replaces the other")와 유형 B 제거 권고 간 tension 해소 필요

### Synthesis (Lens 3)
**유형 B → 제거 또는 문서 이전 우선**
- 모델 행동과 무관한 자동 실행 → CLAUDE.md instruction 불필요
- 문서 목적이라면 `docs/hooks-spec.md`로 이동

**유형 A → 제거 아닌 단축 (1줄)**
- Defense in depth 가치 + 이식성 유지
- 부연 설명 제거, 핵심 금지 1줄만

## Final Conclusion

**핵심 판단**: 유형 A와 B는 다르게 처리해야 한다.

유형 B (훅이 자동 실행) → 제거 권장.
유형 A (훅이 차단) → 단축 유지 권장 (1줄로 압축).

제거/단축/유지 기준:
- 제거: 훅이 자동 실행 + 모델 선택 무관 + fallback 불필요
- 단축: defense-in-depth 가치 있음 → 1줄로 압축
- 유지: 훅 없는 환경의 유일한 보호막 or formatting/style 규칙

## Sources
- [Writing a good CLAUDE.md | HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [How Fleek Uses Git Hooks | earezki.com](https://earezki.com/ai-news/2026-04-05-beyond-prompts-how-git-hooks-steer-ai-coding-agents-in-production/)
- [Claude Code Security: Defense-in-Depth | Dotzlaw](https://www.dotzlaw.com/insights/claude-security/)
- [How to Structure CLAUDE.md | DEV Community](https://dev.to/boucle2026/how-to-structure-your-claudemd-so-claude-code-actually-follows-it-4fkh)
