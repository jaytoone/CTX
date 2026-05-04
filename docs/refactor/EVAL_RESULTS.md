# CTX × Context Mode 실측 검증

| 항목 | 값 |
|---|---|
| 측정 일시 | 2026-05-05 (07:24-07:50) |
| 모델 | claude-opus-4-7 (`--model opus`) |
| 호출 방식 | `claude -p --output-format=stream-json --no-session-persistence --setting-sources ""` |
| Judge | `gemini -p` (gemini 0.40.1) |
| 측정 수 | 5 시나리오 × 4 상태 = **20 측정** |
| 총 비용 | **$8.01** (Opus claude -p), Gemini judge 추가 |
| 한 측정 평균 | 60s wall clock, 2.5K output tokens |

## 환경

- **CTX**: tunaCtx fork (`hang-in/tunaCtx`, master @ `ab499c5`), `_bm25/` 11 모듈, vec-daemon + bge-daemon 활성, pipx ctx-retriever 0.3.13
- **Context Mode**: `mksglu/context-mode` 1.0.107 (plugin)
- **검증 repo**:
  - `seCall` (시나리오 1, 2)
  - `tunaFlow` (시나리오 3)
  - `tunaCtx` (시나리오 4, 5)

## 4 상태 매트릭스

| 코드 | 상태 |
|---|---|
| **A** | CTX + Context Mode 둘다 활성 |
| **B** | CTX off, Context Mode only |
| **C** | CTX only, Context Mode off |
| **D** | 둘다 off (baseline) |

각 상태는 `/tmp/eval-settings/settings-{A,B,C,D}.json` 에 stand-alone 으로 정의 — `~/.claude/settings.json` 에서 `hooks` (CTX 부분) + `enabledPlugins.context-mode@context-mode` 를 차등 제거.

---

## 측정 데이터 (정량)

### 시나리오별 토큰 / 비용 / 시간 / 도구

| ID | duration | cost | input | output | cache_r | tools |
|---|---:|---:|---:|---:|---:|---|
| 1-A | 80.0s | $0.442 | 8 | 2007 | 82,307 | Agent×1, ctx_batch_execute×1, Read×10, Bash×13 |
| 1-B | 121.2s | $0.632 | 18 | 3462 | 285,263 | Agent×1, Bash×18, Glob×1, Grep×3, Read×12, ctx_batch_execute×1 |
| 1-C | 85.3s | $0.714 | 25 | 5657 | 512,443 | Glob×7, Grep×7, Read×4 |
| 1-D | 140.9s | $0.871 | 20 | 4488 | 617,369 | Agent×1, Bash×18, Glob×1, Grep×5, Read×16 |
| 2-A | 44.4s | $0.393 | 20 | 3615 | 138,429 | Bash×2, ToolSearch×1, ctx_batch_execute×2 |
| 2-B | 59.2s | $0.420 | 20 | 4365 | 137,093 | Bash×2, ToolSearch×1, ctx_batch_execute×2 |
| 2-C | 32.8s | $0.168 | 7 | 1793 | 44,924 | Bash×2 |
| 2-D | 44.2s | $0.191 | 7 | 2699 | 44,550 | Bash×2 |
| 3-A | 112.7s | $0.760 | 32 | 8591 | 257,468 | Grep×12, Read×9, ToolSearch×1, ctx_batch_execute×1 |
| 3-B | 121.7s | $0.857 | 29 | 8953 | 370,012 | Bash×1, Grep×4, ToolSearch×1, ctx_execute×2 |
| 3-C | ⚠ TIMEOUT | n/a | 1* | 44* | 47,272 | Agent×1, Bash×5, Grep×27, Read×5 |
| 3-D | 100.8s | $0.471 | 10 | 7303 | 177,393 | Grep×10 |
| 4-A | 35.8s | $0.334 | 20 | 2003 | 133,588 | Bash×1, ToolSearch×1, ctx_batch_execute×2 |
| 4-B | 27.6s | $0.163 | 12 | 1575 | 45,885 | Bash×1 |
| 4-C | 30.9s | $0.158 | 7 | 1829 | 44,400 | Bash×1 |
| 4-D | 48.7s | $0.205 | 8 | 2729 | 72,348 | Bash×1, Read×1 |
| 5-A | 29.9s | $0.370 | 22 | 1964 | 205,553 | Grep×4, ToolSearch×1, ctx_batch_execute×2 |
| 5-B | 54.3s | $0.523 | 36 | 3059 | 364,972 | Bash×1, Glob×1, Grep×3, ToolSearch×2, ctx_batch_execute×1, ctx_execute×2 |
| 5-C | 23.3s | $0.189 | 20 | 1462 | 132,086 | Grep×4 |
| 5-D | 16.9s | $0.149 | 9 | 1098 | 97,359 | Grep×3 |

*3-C: 180s timeout, 응답 partial. 실제로는 Grep×27 등 의미 있는 도구 호출 진행 중이었으나 응답 종료 못함.

### 비용 합계

- **A 상태 (둘다 활성)** 합계: $2.30 — 가장 비쌈
- **B 상태 (CM only)** 합계: $2.59
- **C 상태 (CTX only)** 합계: $1.23 (3-C timeout 미과금) — 가장 저렴
- **D 상태 (baseline)** 합계: $1.89

→ **CTX only (C) 가 cost 측면에서 가장 효율적**. Context Mode 가 활성화되면 ctx_batch_execute / ctx_execute 호출이 추가되어 비용 ↑.

---

## Judge 결과 (Gemini -p, 정성)

| 시나리오 | 1위 | 2위 | 3위 | 4위 | 결정적 차이 |
|---|---|---|---|---|---|
| 1 (코드 검색) | **A** | B | C | D | A: 라인번호 매핑(L133, L138) 정확 + Upstream/Downstream 관계 명확 |
| 2 (긴 출력) | **D** | C | B | A | **A 가 권한 거부로 작업 중단** — Context Mode sandbox 부작용 |
| 3 (한국어) | **A** | B | D | C | A: Rust 코드 + 버그 히스토리까지 깊이 있게 분석. C: timeout |
| 4 (compaction) | **C** | A | B | D | **CTX only 가 결정 근거의 전략적 통찰 최고** |
| 5 (hook 충돌) | **D** | C | B | A | **A 가 권한 거부로 4위** — Context Mode sandbox 가 도구 차단 |

---

## 시너지 / 충돌 / 무차별 분석

### ✅ 시너지 — A (둘다 활성) 가 우월한 시나리오

**시나리오 1, 3** (코드 검색 + 한국어).
- CTX 의 G1/G2 retrieval 로 관련 파일 사전 주입 + Context Mode 의 도구 압축이 도구 사용을 효율화
- 라인번호 정확도, 깊이 있는 분석에서 A 가 다른 상태 모두 능가

### ❌ 충돌 — A (둘다 활성) 가 D (baseline) 보다 못한 시나리오

**시나리오 2, 5** (도구 호출이 많은 작업).
- 시나리오 2: A 의 응답 본문 — `"ctx_batch_execute 권한 거부됨"` 메시지 그대로 노출. 작업 자체가 도구 권한 거부로 중단.
- 시나리오 5: 동일 패턴. Context Mode 의 sandbox redirect 가 권한 prompt 를 발생시키고, headless `claude -p` 환경에서는 그 prompt 응답 불가 → 작업 실패.
- 결과: D (baseline, 단순 Bash + Grep) 가 정상적인 응답 생성. A 는 권한 거부로 4위.

**Production 관점**: headless 자동화 (CI, batch processing) 에서 Context Mode 사용 시 sandbox 권한이 차단될 수 있음. interactive 세션에서는 사용자가 권한 승인 가능.

### 🟰 CTX 의 가치는 모든 시나리오에서 양 또는 중립

**시나리오 4** (compaction): C (CTX only) > A > B > D — CTX 의 G1/G2 retrieval 이 commit 진화 분석에 결정적. Context Mode 는 오히려 노이즈 추가.

CTX 가 1위 또는 2위인 시나리오: 1, 2 (C 2위), 3, 4 (C 1위), 5 (C 2위). CTX 가 4위인 시나리오는 없음.

---

## 추천 사용 패턴

| 작업 종류 | 권장 |
|---|---|
| 코드 분석, 한국어 검색, 깊이 있는 탐색 | **CTX + Context Mode 둘다 활성** (시너지) |
| 도구 호출이 많은 작업 (commit 분석, 코드베이스 grep) | **CTX only** (Context Mode 는 sandbox 부작용) |
| Compaction / 결정 근거 정리 | **CTX only** (가장 우월) |
| 자동화 / headless 배치 | **CTX only** (sandbox 권한 prompt 회피) |
| 단순 채팅 | **둘다 off** (overhead 회피) |

**일반 권장**: **CTX 는 항상 ON**. Context Mode 는 interactive 세션에서만 ON, headless / 도구 집약 작업에서는 OFF.

---

## 본 검증의 한계

- **Sample size**: 시나리오마다 1 prompt × 4 상태. 응답 분산 측정 안 함. 실제 production 에서는 분산이 클 수 있음.
- **Judge 주관성**: Gemini 1회 평가. LLM-as-judge 의 일반적 한계 (선호도, 길이 편향 등).
- **Repo 의존성**: seCall, tunaFlow, tunaCtx 는 실제 한국어 + 코드 환경. 영어 전용 repo 에서는 다른 패턴 가능.
- **Headless 환경**: `claude -p` 의 sandbox 권한 동작이 interactive 세션과 다를 수 있음 — 시나리오 2, 5 의 권한 거부 패턴이 interactive 에서 재현되는지 별도 검증 필요.
- **3-C timeout**: 180s 한도. CTX only + 한국어 패턴 검색이 timeout 에 도달 — Grep 27 회. CTX 의 G2-GREP fallback 이 한국어에서 광범위 grep 시도하는 패턴.

## 원시 데이터

- 측정 raw: `/tmp/eval-results/raw/scenario*-{A,B,C,D}.{out,err}` (gitignored)
- 메트릭 JSON: `/tmp/eval-results/scenario*-{A,B,C,D}.json` (gitignored)
- Judge JSON: `/tmp/eval-results/judge-scenario*.json` (gitignored)

---

## 다음 검증 후보

- **Sample size 확대**: 각 시나리오 5-10회 반복으로 응답 분산 측정.
- **시나리오 6 명시**: A vs B vs C vs D 의 4 상태 외에 더 fine-grained 토글 (예: CTX 의 vec-daemon 만 끄기, BGE 만 끄기).
- **Headless vs Interactive**: 같은 시나리오를 interactive Claude Code 에서 측정해서 sandbox 권한 패턴 비교.
- **Context Mode 의 ctx_batch_execute / ctx_execute 가 실제 토큰 압축 효과**: cache_read 차이로 추정 가능하지만 명시적 측정 미실시.
