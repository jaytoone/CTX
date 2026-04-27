# [expert-research-v2] claude-vault 리서치 및 CTX 적용 방안
**Date**: 2026-04-10  **Skill**: expert-research-v2

## Original Question
claude-vault에 대해 리서치하고 Claude Code / CTX 프로젝트에 어떻게 적용할지 확인

## Web Facts

| # | Fact | Source |
|---|------|--------|
| F1 | claude-vault(MarioPadilla)는 Claude AI 대화 & Claude Code .jsonl history를 Obsidian 등 노트 앱용 Markdown으로 변환하는 CLI 도구 | [GitHub](https://github.com/MarioPadilla/claude-vault) |
| F2 | 지원 포맷: Claude Web exports(.json), Claude Code history(.jsonl), OpenCode sessions(.db) — 자동 감지 | GitHub README |
| F3 | Local-first: 모든 처리 로컬 완결, 외부 API 불필요 | GitHub README |
| F4 | AI 태깅/요약: Ollama 로컬 LLM(llama3.2:3b) 사용, keyword extraction fallback | GitHub README |
| F5 | Semantic search: 개념 기반 검색 지원 | GitHub README |
| F6 | Bi-directional sync + UUID 추적 (파일 이동/이름변경 후에도 sync 유지) | GitHub README |
| F7 | Watch mode: export 파일 변경 시 자동 sync | GitHub README |
| F8 | PII 보호: 이메일, SSN, API 키 자동 감지/리댁션 | GitHub README |
| F9 | Claude Code 통합: `claude-vault sync ~/.claude` 로 .jsonl 직접 임포트 | GitHub README |
| F10 | Obsidian용 Claude Code 스킬: /context(vault 상태 로드), /today(일일 계획+Calendar), /spark(패턴 발견) | [Medium](https://medium.com/@martk/obsidian-claude-code-the-claude-code-skills-that-make-your-vault-feel-alive-4ec05a1ec1e6) |

## Multi-Lens Analysis

### Lens 1: Domain Expert — CTX 적용 가치

**Insight 1 — .jsonl 파싱으로 G1 사각지대 보완**
CTX G1(git-memory)은 git log에서 의사결정을 추출하지만, 커밋되지 않은 세션(실험적 탐색, 기각된 방향, 중간 추론)은 소실된다. claude-vault는 `~/.claude/*.jsonl`을 직접 파싱해 이 데이터를 복원할 수 있다. G1의 핵심 목표("왜 BM25로 바꿨지?")에 더 직접적으로 기여하는 데이터 레이어다.

**Insight 2 — Ollama 태깅이 BM25 keyword 의존성 보완 가능**
현재 git-memory.py의 `_is_decision()` 함수는 rule-based 동사 매칭. claude-vault의 Ollama 태깅 패턴을 채용하면 "add/introduce/reject/abandon" 같은 동의어 결정 동사를 semantic하게 분류 가능. 단, LLM 호출이므로 hook 체인 외부에서만 사용.

**Insight 3 — /spark 패턴이 MEMORY.md 자동화에 응용 가능**
claude-vault의 /spark 스킬(여러 노트에서 패턴 발견)을 CTX에 포팅하면, G1 의사결정들에서 반복 패턴 자동 요약 → 현재 수동 유지되는 MEMORY.md 부담 감소.

**Insight 4 — PII 리댁션이 G1 보안 갭 해결**
CTX가 git log + .jsonl을 더 많이 인덱싱할수록 API 키, 개인정보 노출 위험 증가. claude-vault PII 감지 레이어가 이를 해결.

### Lens 2: Devil's Advocate

**비판 1 (핵심) — 아키텍처 충돌: Ollama 호출은 CTX determinism을 파기한다**
CTX 최대 강점 = "LLM 호출 없음, <1ms deterministic". Ollama llama3.2:3b 추론은 수백ms~수초. Hook 체인에 포함 시 이 가치 제안이 근본적으로 파기된다. claude-vault 자체도 LLM을 optional fallback으로만 사용하는 이유가 바로 이것.

**비판 2 — 한계 이익 불명확**
G1이 이미 82-100% recall(git-only)을 달성하는 상황에서 .jsonl 추가의 실제 개선 효과는 실험 전에 알 수 없다. History category(0.55)가 약하다면, .jsonl 보강이 이를 얼마나 개선하는지 ablation 필요.

**비판 3 — claude-vault 성숙도 불확실**
개인 프로젝트, Claude Code .jsonl 포맷 변경 시 파서 깨짐 위험. 장기 의존성 추가 전 안정성 검증 필요.

### Lens 3: Practical Synthesizer — 권장 적용 방안

**최선: 선택적 차용, 완전 통합 금지**

| 방안 | 구현 위치 | 효과 | 우선순위 |
|------|----------|------|---------|
| PII 리댁션 로직 차용 | git-memory.py 전처리 | 보안 강화 | 즉시 |
| .jsonl 비동기 파이프라인 | cron/세션 종료 후 별도 실행 | G1 데이터 소스 확장 | 단기 |
| /spark 스킬 포팅 | ~/.claude/skills/ | MEMORY.md 자동화 | 중기 |
| Ollama 태깅 | **hook 체인 외부만** | Semantic 분류 (선택) | 낮음 |

## Final Conclusion

**claude-vault = CTX의 비동기 G1 데이터 공급자로 활용 가능**. Hook 체인 내부가 아닌 외부에서:

1. **즉시 실행**: claude-vault의 PII regex 패턴을 git-memory.py에 직접 추가 (외부 의존성 없음)
2. **단기 실행**: `claude-vault sync ~/.claude` cron job → 변환된 Markdown을 BM25 인덱스에 추가 소스로 포함
3. **중기 실험**: /spark 류의 패턴 발견 스킬 구현 (on-demand, hook 아님)

**절대 금지**: UserPromptSubmit hook 체인에 Ollama 포함 — CTX 핵심 차별점 파기

## Sources
- [claude-vault GitHub](https://github.com/MarioPadilla/claude-vault)
- [Claude Code Skills for Obsidian — Medium](https://medium.com/@martk/obsidian-claude-code-the-claude-code-skills-that-make-your-vault-feel-alive-4ec05a1ec1e6)
- [Claude Code secrets management issue](https://github.com/anthropics/claude-code/issues/29910)

## Remaining Uncertainties
- claude-vault의 현재 Claude Code .jsonl 포맷 호환성 미검증 (`claude-vault sync ~/.claude` 실행 테스트 필요)
- .jsonl 비동기 파이프라인이 G1 History category(0.55) 실질 개선 여부 — ablation 실험 필요
- /spark 스킬 구체적 구현 코드 공개 여부 불명확
- claude-vault 마지막 커밋 날짜 및 유지보수 상태 미확인

## Related
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260412-semantic-gap-keyword-vs-contextual|20260412-semantic-gap-keyword-vs-contextual]]
- [[projects/CTX/research/20260417-ctx-semantic-search-upgrade-sota|20260417-ctx-semantic-search-upgrade-sota]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
