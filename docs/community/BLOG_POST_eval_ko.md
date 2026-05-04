# CTX × Context Mode 같이 쓸 때 무엇이 일어나는가 — 5 시나리오 × 4 상태 실측

> 2026-05-05 / Korean dev env / claude-opus-4-7 / 총 28 측정 $10.58

## 배경

Claude Code 에 hook 시스템을 두 개 동시에 깔아둔 상태로 며칠 작업하다 보니 — [`jaytoone/CTX`](https://github.com/jaytoone/CTX) (이 fork: [`hang-in/tunaCtx`](https://github.com/hang-in/tunaCtx)) 의 retrieval 기반 메모리 hook 과, [`mksglu/context-mode`](https://github.com/mksglu/context-mode) 의 sandbox/도구 압축 plugin — 한 가지 의문이 생겼다.

> 둘이 같이 켜져 있으면 시너지인가, 충돌인가?

추측하지 말고 측정하자고 결정했다. 본 글은 그 결과 공유.

## 환경

- **모델**: `claude-opus-4-7`
- **호출**: `claude -p --output-format=stream-json --no-session-persistence --setting-sources ""` (headless)
- **상태 4종**:
  - A — CTX + Context Mode 둘다 활성
  - B — CTX off, Context Mode only
  - C — CTX only, Context Mode off
  - D — 둘다 off (baseline)
- **검증 repo**: `seCall`, `tunaFlow`, `tunaCtx` (한국어 주석 + 영어 코드 혼재)
- **Judge**: `gemini -p` (Gemini 0.40.1) 로 응답 품질 ranking

각 상태는 `~/.claude/settings.json` 에서 hooks 와 `enabledPlugins.context-mode@context-mode` 를 차등 제거한 stand-alone settings 파일로 격리.

## 시나리오 5개

| # | 작업 | repo |
|---|---|---|
| 1 | 핵심 함수 분석 + 호출 흐름 + 테스트 | seCall |
| 2 | 최근 30 commit 변화 패턴 | seCall |
| 3 | 한국어 docstring 의 `Roundtable` / `RT` 검색 | tunaFlow |
| 4 | 최근 5 commit 의 진화 방향 정리 | tunaCtx |
| 5 | `.py` 파일 전체 TODO 주석 grep | tunaCtx |

## 측정 결과 — Judge 1위

| 시나리오 | 1위 | 비고 |
|---|---|---|
| 1. 코드 검색 | **A (둘다)** | 라인번호(L133, L138) 정확 + Upstream/Downstream 그래프 |
| 2. 30 commit 분석 | D (baseline) | A 가 권한 거부로 abort — 후술 |
| 3. 한국어 docstring | **A (둘다)** | Rust 코드 + 버그 히스토리까지 깊이 분석 |
| 4. compaction | **C (CTX only)** | Context Mode 의 도구 호출이 노이즈 |
| 5. TODO grep | D (baseline) | A 가 권한 거부로 4위 — 후술 |

처음에 표를 봤을 때 결론을 단순화하고 싶었다 — "Context Mode 는 충돌, CTX only 가 낫다". 그러나 그건 틀렸다. 시나리오 2, 5 의 패턴을 자세히 보니 다른 그림이 나왔다.

## 시나리오 2/5 의 "충돌" 은 권한 artifact 였다

A 상태 (둘다 활성) 의 응답 본문에 이런 문구가 박혀 있었다.

```
"Permission needed. Asking the user to grant ctx_batch_execute..."
"ctx_batch_execute 권한 거부됨. Grep tool로 진행"
```

`claude -p` headless 환경에서는 권한 prompt 가 응답 가능한 stdin 이 없다. Context Mode 의 `ctx_batch_execute` 도구를 호출하려고 했으나 권한 거부 → 작업 abort. **Context Mode 자체 결함이 아니라 headless 환경에서 권한 정책이 차단된 것**.

검증을 위해 같은 8 측정을 `--dangerously-skip-permissions` 추가로 재실행했다 ($2.57 추가).

| 시나리오 2 A 응답 head | |
|---|---|
| default permissions | `Permission needed. Asking the user to grant...` (abort) |
| `--dangerously-skip-permissions` | `## seCall 최근 30개 commit 분석... feat: 9건, fix: 6건, Merge PR: 9건...` (정상) |

| 시나리오 5 A 응답 head | |
|---|---|
| default permissions | `ctx_batch_execute 권한 거부됨. Grep tool로 진행` (부분 fallback) |
| `--dangerously-skip-permissions` | `프로젝트 .py 파일 203개 중 # TODO/FIXME/XXX/HACK 주석은 0건` (정확 + .venv-golden 노이즈 명시 필터) |

비용: skip-perm 시 +13~21%. Context Mode 의 도구 호출이 정상 진행되어 발생한 cost. quality 회복으로 정당화.

즉 **interactive Claude Code 또는 `skipDangerousModePermissionPrompt: true` 설정 환경에서는 시나리오 2/5 의 "충돌" 은 발생하지 않는다**. headless `claude -p` 자동화에서만 명시적 권한 정책 필요.

## 시나리오 4 의 "CTX only 가 1위" 는 권한과 무관

이건 다른 이야기. compaction (최근 5 commit 의 진화 방향 정리) 같은 작업에서 Context Mode 의 도구 압축 / batch 실행은 본질적으로 노이즈다 — 정리할 게 단순한 git log 1번이면 충분한데 ctx_batch_execute 까지 동원하면 응답 길이가 늘어나고 핵심 통찰이 흐려진다. 이 finding 은 권한과 별개로 신뢰성이 있다.

| 시나리오 4 (compaction) | A (둘다) | C (CTX only) |
|---|---|---|
| Judge 순위 | 2위 | **1위** |
| 비용 | $0.334 | $0.158 |
| 응답 길이 | 2003 tokens | 1829 tokens |

같은 정보를 절반 비용으로 더 충실하게 정리.

## 비용 매트릭스

5 시나리오 × 4 상태 합계 (1차 측정, 권한 default):

| 상태 | 합계 | 비고 |
|---|---:|---|
| C (CTX only) | $1.23 | 가장 저렴. 단 시나리오 3-C 는 한국어 + Grep×27 으로 timeout |
| D (baseline) | $1.89 | |
| A (둘다) | $2.30 | ctx_batch_execute 호출 비용 |
| B (CM only) | $2.59 | 가장 비쌈 — Context Mode 가 retrieval 부재를 도구 호출로 보충 |

## 추천 사용 패턴

| 환경 | 작업 | 권장 |
|---|---|---|
| Interactive Claude Code (또는 `skipDangerousModePermissionPrompt: true`) | 코드 분석 / 한국어 검색 | **둘다 ON** (시너지) |
| 동일 | Compaction / 결정 정리 | **CTX only** (Context Mode 노이즈) |
| Headless `claude -p` | 도구 집약 작업 | `--dangerously-skip-permissions` 또는 Context Mode OFF |
| 단순 채팅 | — | 둘다 OFF (overhead 회피) |

**일반 권장**: CTX 는 항상 ON. Context Mode 는 환경 + 작업 종류에 따라 토글.

## 한계 — 정직히

- **Sample size**: 시나리오마다 1 prompt × 4 상태. 응답 분산 측정 안 함. 실 production 에서는 분산이 클 수 있음.
- **Judge 1회**: Gemini -p 1번 평가. LLM-as-judge 의 일반적 편향 (선호도, 길이 편향) 가능.
- **Repo 의존성**: 한국어 + 영어 혼재 환경. 영어 전용 repo 는 다른 패턴 가능.
- **Headless ↔ interactive 동작 차이**: `claude -p` 의 sandbox 권한 동작이 interactive 와 정확히 일치한다는 보장 없음. interactive 직접 검증 미실시.
- **시나리오 3-C timeout**: 180s 한도 도달. CTX only + 한국어 광범위 grep (27회) 으로 인한 — CTX 의 G2-GREP fallback 이 한국어에서 너무 적극적일 가능성 있음.

## 데이터

- 측정 raw: `tests/golden/raw/scenario*-{A,B,C,D}.{out,err}` (gitignored, 본 fork 의 `/tmp/eval-results/` 위치에 보존)
- 종합 보고서: [`docs/refactor/EVAL_RESULTS.md`](https://github.com/hang-in/tunaCtx/blob/master/docs/refactor/EVAL_RESULTS.md)
- 본 fork: [`hang-in/tunaCtx`](https://github.com/hang-in/tunaCtx)
- 원본: [`jaytoone/CTX`](https://github.com/jaytoone/CTX)

## 마무리

처음에 데이터를 보고 단순화하고 싶었다 — "Context Mode 는 충돌이고 CTX only 가 항상 낫다". 그러나 8 측정 추가로 검증해 보니 시나리오 2/5 의 "충돌" 은 headless 환경 한정 권한 artifact 였고, interactive 환경에서는 시너지 가능성이 높다.

세 줄 요약:

1. **CTX 는 모든 환경 always-on safe**. 1위 또는 2위 안정.
2. **Context Mode 는 환경 의존**. interactive 는 시너지, headless 는 권한 정책 명시.
3. **Compaction 작업에서는 CTX only 가 항상 우월** (권한과 무관, $0.158 vs $0.334).

`claude -p` 자동화 / CI / batch 처리 환경이라면 settings.json 에 `skipDangerousModePermissionPrompt: true` 추가하거나 `--dangerously-skip-permissions` 플래그를 명시하는 게 두 hook 시너지를 살리는 가장 빠른 길이다.

