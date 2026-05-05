# 핸드오프 — tunaCtx production-level refactor 사이클

| 항목 | 값 |
|---|---|
| 마지막 갱신 | 2026-05-05 (Cycle-3.5 — Windows TCP fallback PR 머지 + upstream 협업 라운드 1 종료) |
| 작업 식별자 | Phase 0 → Task A/B/C/D → Phase 9 → Cycle-2 → Cycle-3 (docs hygiene) → Cycle-3.5 (PR #1 merge + upstream coordination) |
| 작업 디렉토리 | `/Users/d9ng/privateProject/tunaCtx` (clone 후 fork remote 로 운영, 정식 GitHub fork 아님) |
| 현재 브랜치 | `master` (= `origin/master` = `hang-in/tunaCtx:master`) |
| 마지막 commit | `29f241c feat(hooks): Windows TCP loopback fallback for AF_UNIX-less CPython (#1)` |
| 회귀 가드 상태 | golden **15/26 PASS** (11 fallback drift, §6-1 함정 — production 회귀 아님) / pytest **105 PASS / 0 skip** |
| 원본 upstream | `https://github.com/jaytoone/CTX` (remote: `upstream`) |
| Fork remote | `https://github.com/hang-in/tunaCtx` (remote: `origin`) |
| Upstream issues | #1 fork 알림 (2026-05-04, jaytoone 답변 + 우리 reply 발행, **응답 대기**) / #2 docs R@5 정합성 정정 (2026-05-05, jaytoone fix 적용 + **CLOSED**) |
| Fork PR | #1 Windows TCP fallback (2026-05-05, gemini 5건 반영, **MERGED** `29f241c`) |

## 1. 이 fork 의 정체

**원본**: `jaytoone/CTX` — Trigger-Driven Dynamic Context Loading for Code-Aware LLM Agents.

**fork 가 한 일**: retrieval **알고리즘은 변경하지 않음**. Claude Code hook 구현이 실제 사용 환경에서 안전하게 운영되도록 production readiness 만 손봄.

**fork 가 안 한 일**: paper 작성, 새 retrieval strategy 추가, 알고리즘 변경, README 의 마케팅 톤. 이런 것 다음 세션에서도 추가하지 말 것 — 명시적 user 요청 없는 한.

## 2. 작업 history (시간순)

| 단계 | 산출 | 회귀 검증 |
|---|---|---|
| **Phase 0** | `tests/golden/` 픽스처 26개 캡처 (deterministic 모드) — fallback 14 + BM25-path 12 | 26/26 PASS 베이스라인 |
| **Task A** | `bm25-memory.py` 1837줄 → orchestrator 300줄 + `src/hooks/_bm25/` 11 모듈 | 26/26 유지 |
| **Task B** | `tests/unit/` 64개 단위 테스트 신설 | pytest 64/0 |
| **Wave 1 후속** (codex Critical+Major) | `_bm25/` packaging 누락 fix, cache fixture fix, sqlite_vec guard | 64/0 유지 |
| **Task C** | tokenizer + ranker 단일 canonical (`_bm25/tokenizer.tokenize`, `_bm25/ranker.score_corpus_bm25`) — `adaptive_trigger.py`, `doc_retrieval_eval_v2.py`, `bm25_retriever.py`, `coir_evaluator.py` 모두 통합 | 26/26 + benchmark delta=0 |
| **Task D** | `bm25-memory` orchestrator telemetry instrument (7 events, lazy gate) | pytest 70/0 |
| **Phase 9** (codex 최종 리뷰) | Critical 1 + Major 4 + Minor 3 + golden 옵션 B 권고 | — |
| **Phase 9 후속** | Critical (`ctx-install` hash-based update) + Major #1/#2/#4 + Minor #1 + golden 옵션 B (G2-GREP normalize) | golden 25→26/26 회복 |
| **Cycle-2** | golden runner stderr 가드 (옵션), atomic write 실 filesystem 검증, `_bm25/__init__.py` 17함수 re-export, `--uninstall` cleanup, plan footer | pytest 82→105/0 |
| **Cycle-3 (docs hygiene)** | (a) README 검색 stack bullet 추가 — "BM25 만" 커뮤니티 오해 정정 / (b) R@5=0.152 stale 인용 갱신 (CLAUDE.md L91·L197, PRODUCTION_REFACTOR_PLAN.md L263) — iter11 재측정 Mean R@5=0.595 인용 / (c) README 에 외부 codebase 측정값 (참고) bullet 추가 + upstream issue 링크 / (d) upstream issue #2 발행 (docs R@5 정합성) | pytest 105/0 / golden 15/26 (fallback drift §6-1) |
| **Cycle-3.5 (PR merge + upstream coord)** | (a) PR #1 Windows TCP fallback 머지 (`29f241c`) — gemini 5건 반영 (`socket` import top-level 정리, `SO_REUSEADDR` Windows 가드) / (b) upstream issue #2 jaytoone fix 후 close + 우리 감사 댓글 / (c) upstream issue #1 jaytoone 질문 3개 + PR shape 답변 발행 (Q1 tokenizer canonical, Q2 sqlite_vec graceful, Q3 install hash-based, PR 분해 5단계 + subtoken splitter 별도 사이클 명시) | pytest 105/0 / golden 15/26 (drift 동일) |

## 3. 현재 코드 상태

### 디렉토리 구조 (요점)

```
src/
  hooks/
    bm25-memory.py         # orchestrator (300 lines)
    _bm25/                 # 11 모듈 (canonical BM25 구현)
      __init__.py          # 17 public 함수 re-export
      tokenizer.py         # 한국어 조사 + Porter + stopword
      ranker.py            # score_corpus_bm25 + bm25_rank_decisions + ...
      corpus.py            # G1 decision corpus (git HEAD-keyed cache)
      rerank.py            # vec-daemon + BGE cross-encoder
      autotune.py          # ctx-auto-tune.json reader
      docs_search.py       # G2-DOCS BM25 + hybrid
      code_search.py       # G2 code grep + reindex (deterministic sort)
      hooks_search.py      # ~/.claude/hooks/*.py BM25
      session.py / injection.py / output.py
    chat-memory.py         # vault.db FTS5 + vec0 (sqlite_vec guard 추가됨)
    memory-keyword-trigger.py
    g2-fallback.py
    utility-rate.py
    _ctx_telemetry.py
  cli/
    install.py             # ctx-install (hash-based update + --force-hooks/--no-update-hooks/--uninstall)
    settings_patcher.py    # atomic write + timestamped backup
    telemetry.py           # ctx-telemetry
  retrieval/
    adaptive_trigger.py    # 통합된 _bm25 토크나이저/스코어러 사용. 단 self.bm25 = BM25Okapi(...) 잔존 (persistent 객체 재사용 — 정당)
    bm25_retriever.py
    ... (그 외 7 strategy)
  evaluator/
    coir_evaluator.py      # _bm25 통합됨

tests/
  golden/
    bm25_memory_outputs.jsonl       # 26 픽스처 (fallback 14 + bm25path 12)
    bm25_path_corpus_frozen.json    # 결정성 보장용 frozen G1 corpus
    run_golden.py                   # G2-GREP normalize + expected_stderr 옵션
  unit/                             # 105 tests
    test_settings_patcher.py        # 22 (atomic, idempotency, real fs rename)
    test_install_cli.py             # 32 (hash update, force, no-update flags)
    test_chat_memory_fallback.py    # 9 (subprocess 기반)
    test_bm25_memory_cache.py       # 7 (HEAD invalidation)
    test_bm25_memory_telemetry.py   # 6 (gate, fallback reason, exception)
    test_code_search_sort.py        # 6 ((-count, path) deterministic)
    test_bm25_init_reexport.py      # 10 (callable, no circular, state 비노출)
    test_uninstall_cleanup.py       # 10 (hash 보존, force, dry-run)
    conftest.py                     # tmp_home / tmp_project fixtures

docs/refactor/
  PRODUCTION_REFACTOR_PLAN.md       # 본 사이클 plan (footer 정정 포함)
  TELEMETRY_SCHEMA.md               # 7 이벤트 스키마 명세
  HANDOFF.md                        # 이 문서

scripts/
  verify_bm25_unified.py            # BM25 통합 sanity check
```

### 잔존 BM25Okapi (의도적)

`grep -rE "BM25Okapi" src/`:
- `src/hooks/_bm25/{ranker,docs_search,hooks_search}.py` — canonical 위치 (3 사이트)
- `src/retrieval/adaptive_trigger.py` — persistent 객체 재사용 패턴 (성능 우선, codex 도 정당화 인정)
- archival benchmark (`benchmarks/eval/*.py`) 11+ 개 — 의도적 보류 (A/B 실험 의미 보존)

다음 세션에서 이걸 더 정리하려는 욕심은 **하지 말 것**. ROI 낮고 회귀 risk 높음.

## 4. 적용 상태 (2026-05-05 06:32)

### ctx-install 실행 완료

```bash
.venv-golden/bin/ctx-install
```

결과:
- `~/.claude/hooks/` 에 18 파일 복사 (5 hook + 11 `_bm25/*` + `_ctx_telemetry.py` + `utility-rate.py`)
- `~/.local/share/claude-vault/` 에 vec-daemon + bge-daemon 2개 복사
- `~/.claude/settings.json` 에 5 hook 등록:
  - UserPromptSubmit: chat-memory, bm25-memory --rich, memory-keyword-trigger
  - PostToolUse(Grep): g2-fallback
  - Stop: utility-rate
- backup: `~/.claude/settings.backup_20260505_063258.json`

### 현재 알려진 제약 (Cycle-3 시점 갱신, 2026-05-05 기준)

이전 HANDOFF 의 "fallback 모드 / daemon down" 기술은 **Cycle-3 시점에 모두 해소됨**. 실측 결과:

- ✅ **hook command 가 pipx python 사용 중**: `~/.claude/settings.json` 의 5개 hook command 모두 `/Users/d9ng/.local/pipx/venvs/ctx-retriever/bin/python` 경로 — system python3 fallback 아님
- ✅ **pipx venv 패키지 정상**: `rank_bm25`, `numpy 2.4.4`, `sklearn 1.8.0`, `networkx 3.6.1` 모두 설치됨
- ✅ **vec-daemon running** (PID 24808 — 검증 시점, socket active)
- ✅ **bge-daemon running** (PID 25006 — `BAAI/bge-reranker-v2-m3` 모델 로드 완료, socket active)
- → 옵션 C (pipx 격리) 가 적용 완료된 상태로 운영 중. 옵션 B / 옵션 C 활성화 가이드 (아래 §4-1, §4-2) 는 재설치 시 참고용으로만 보존

### §4-1. BM25 / 의미층 활성화 (옵션 C — pipx 격리, 권장 — **현재 적용된 옵션**)

```bash
# 1. pipx 설치 (없으면)
brew install pipx
pipx ensurepath

# 2. ctx-retriever 격리 설치 (작업 디렉토리 = 현재 tunaCtx clone)
pipx install /Users/d9ng/privateProject/tunaCtx
# → ~/.local/pipx/venvs/ctx-retriever/bin/ 에 ctx-install / ctx-telemetry / python 위치

# 3. settings.json 의 hook command 의 python 경로를 pipx python 으로:
# python3 $HOME/.claude/hooks/bm25-memory.py --rich
# →
# /Users/d9ng/.local/pipx/venvs/ctx-retriever/bin/python $HOME/.claude/hooks/bm25-memory.py --rich

# 4. vec-daemon / bge-daemon 도 동일하게 pipx python 사용:
nohup ~/.local/pipx/venvs/ctx-retriever/bin/python ~/.local/share/claude-vault/vec-daemon.py >/dev/null 2>&1 &
nohup ~/.local/pipx/venvs/ctx-retriever/bin/python ~/.local/share/claude-vault/bge-daemon.py >/dev/null 2>&1 &
```

### §4-2. BM25 / 의미층 활성화 (옵션 B — 현재 dev venv 사용, 빠름)

```bash
# .venv-golden 가 이미 ctx-retriever editable + rank_bm25 + numpy + sklearn + networkx 설치됨
# settings.json 에서 hook command 의 'python3' 를 venv python 으로 교체:
# python3 $HOME/.claude/hooks/...
# →
# /Users/d9ng/privateProject/tunaCtx/.venv-golden/bin/python $HOME/.claude/hooks/...

# vec-daemon / bge-daemon 도 동일하게:
nohup /Users/d9ng/privateProject/tunaCtx/.venv-golden/bin/python ~/.local/share/claude-vault/vec-daemon.py >/dev/null 2>&1 &
nohup /Users/d9ng/privateProject/tunaCtx/.venv-golden/bin/python ~/.local/share/claude-vault/bge-daemon.py >/dev/null 2>&1 &
```

옵션 B 는 이 dev 머신에 한정. 다른 머신/사용자 재현 시 옵션 C 권장.

### 롤백 (필요 시)

```bash
# settings.json 만 되돌리기:
cp ~/.claude/settings.backup_20260505_063258.json ~/.claude/settings.json

# hook 파일까지 정리:
.venv-golden/bin/ctx-install --uninstall          # 사용자 수정 보존
.venv-golden/bin/ctx-install --uninstall --force  # 강제 모두 제거
```

## 5. 검증 명령 (다음 세션에서 sanity check)

```bash
cd /Users/d9ng/privateProject/tunaCtx

# 회귀 가드 (deterministic hook output)
.venv-golden/bin/python tests/golden/run_golden.py
# 기대: 15/26 fixtures passed (Cycle-3 시점)
# — 11 fallback variant 가 git log drift 영향으로 FAIL 중. §6-1 참조.
# — bm25path variant 12/12 PASS — frozen corpus 메커니즘 정상.
# — fixture refresh 가 필요한 경우: --update 후 production 동작 변화 없는지 확인 후 commit

# 단위 테스트
.venv-golden/bin/python -m pytest tests/unit -q
# 기대: 105 passed

# BM25 통합 sanity
.venv-golden/bin/python scripts/verify_bm25_unified.py
# 기대: ALL CHECKS PASSED

# install 상태 점검
.venv-golden/bin/ctx-install status
```

## 6. 다음 세션이 알아야 할 함정

### 6-1. Golden fixture 의 git history 의존성

`tests/golden/bm25_memory_outputs.jsonl` 의 BM25-path 픽스처는 G1 (decision corpus) 상위 ranking 을 stdout 에 포함. **새 commit 이 추가되면 corpus 가 진화하면서 ranking 이 변동 → fixture drift**.

`tests/golden/bm25_path_corpus_frozen.json` 가 frozen corpus 메커니즘 일부 제공하지만 완벽하지 않음 — 현재 매 사이클 끝에 다음 명령으로 fixture refresh 필요:

```bash
python3 tests/golden/run_golden.py --update
# 단, 이 갱신이 production 동작 변화 없는지 확인 후 수용
```

drift 가 발생하는 것은 production 회귀가 아니라 입력 데이터(git log) 의 자연 진화. fixture 의 expected_stdout 을 갱신하는 게 정상 패턴.

장기적으로 frozen corpus 메커니즘 강화하려면:
- runner 가 BM25-path fixture 실행 시 git log 를 무시하고 frozen corpus 만 사용하도록 강제
- 현재 `run_golden.py:75 _inject_frozen_corpus()` 가 부분 구현. 이게 모든 BM25 경로에 적용되는지 검증 필요.

### 6-2. Telemetry zero-cost gate

`src/hooks/bm25-memory.py:64` 부근의 `_TELEMETRY_ENABLED` 모듈 수준 gate + `_log_event_impl = None` lazy import. 이 패턴이 깨지면 telemetry 비활성 시에도 latency 가 발생함.

다음 세션에서 bm25-memory.py orchestrator 를 만질 때 이 패턴을 보존할 것. 검증:
```bash
.venv-golden/bin/python -m pytest tests/unit/test_bm25_memory_telemetry.py -v
# test_telemetry_latency_overhead_under_5ms 가 PASS 해야 함
```

### 6-3. `_bm25/` 의 cross-package import

`src/retrieval/adaptive_trigger.py` 가 `from src.hooks._bm25 import tokenize, score_corpus_bm25` 로 cross-package import. architectural purity 관점에서는 어색하지만 (`retrieval` 이 `hooks` 를 의존), 실용적 trade-off. 향후 깔끔하게 정리하려면 `src/_shared/bm25/` neutral 위치로 이동 + 양쪽이 거기서 import. 단 이건 본 사이클 명시 보류 항목.

### 6-4. `chat-memory.py` 의 sqlite_vec import

`src/hooks/chat-memory.py:16` 는 `try/except ImportError` 로 `sqlite_vec` 무방어 import 보강됨. 단 `chat-memory.py` 자체는 본 사이클에서 분해하지 않음 — 529줄. 다음 사이클 후보. 분해 시 `_bm25/` 와 동일 패턴 적용.

### 6-5. archival benchmark 11+개

`benchmarks/eval/g1_*.py`, `g2_*.py`, `mab_*.py`, `nemotron_*.py`, `retrieve_ctx_v2.py` 등이 자체 BM25Okapi 구현. **통합 시 paper headline 결과 (MAB N=50 ctx_v3=0.880 등) 가 변할 수 있음** — 즉 frozen 결과의 회귀 risk. 통합 욕심 내지 말 것.

### 6-6. 외부 codebase R@5 수치의 다중성 (Cycle-3 발견)

upstream / fork docs 에 외부 codebase R@5 가 **여러 시점 측정값으로 공존** —
- `0.152`: 가장 옛날 baseline (`docs/research/20260326-ctx-methodology-comparison.md` L70 — pre-fix, 자체 텍스트에서 stale 인정)
- `0.495`: SEMANTIC trigger fix 후 (commits `727b5c3`)
- `0.595`: iter11 재측정 (`benchmarks/results/reeval_external_iter11.json` — Mean R@5 = 0.595, Flask 0.6462 / FastAPI 0.3870 / Requests 0.7526). **canonical 확정 (jaytoone 답변 in issue #2)**.
- `0.744`: `docs/benchmark/g1_g2_publication_framework.md` 의 다른 평가 framework — **superseded by iter11** (jaytoone 명시).

Cycle-3 에서 fork 내부 인용은 0.595 로 통일 + Cycle-3.5 에서 jaytoone 답변으로 canonical 확정. 다음 세션부터 R@5 인용은 **0.595 = canonical** 로 단정 가능.

또한 `benchmarks/eval/reeval_external.py` 를 직접 재실행하려면 입력 query JSON (`benchmark_real_eval_*.json`) 이 repo 에 없음 (`find` 결과 0건) — git history 복원 또는 upstream 문의 선행 필요.

### 6-7. README.md 의 upstream PR 제외 (Cycle-3.5 결정)

**README.md 는 upstream PR scope 에 포함하지 않음** — fork 와 upstream 의 방향성이 다르기 때문:
- upstream README: paper / benchmark 헤드라인 / academic 톤
- fork README: production hook 운영 / 설치 / 적용 가이드 / `검색 stack` 명시 / 외부 codebase 측정값 참고 / Empirical eval (Context Mode) 등

향후 upstream PR 분해 진행 시 (issue #1 의 5단계 plan):
- Tokenizer unification / sqlite_vec graceful / install hash-update / bm25-memory 분해 / telemetry instrumentation — 모두 **README 수정 없이** 코드/테스트만 cherry-pick
- README 갱신은 fork 단독 유지 — 두 repo 의 사용자 페르소나가 다르다는 인정

## 7. upstream 처리 (참고)

upstream issues:
- `#1` (2026-05-04): fork 알림 → jaytoone 답변 (3 questions + PR 환영) → 우리 reply 발행 (Cycle-3.5) — **응답 대기 중** (어느 PR shape 로 진행할지)
- `#2` (2026-05-05): docs R@5 정합성 정정 권고 → jaytoone 즉시 fix push + canonical 0.595 확정 → 우리 감사 댓글 + close — **CLOSED**

PR shape 응답 시 시나리오:
- **upstream 이 5단계 분해 환영** → issue #1 reply 의 순서대로 진행:
  1. Tokenizer unification (가장 작고 안전)
  2. sqlite_vec graceful degradation
  3. install.py hash-based update + atomic settings_patcher
  4. bm25-memory.py 11 sub-module 분해 (의존: 1 land 후)
  5. Telemetry instrumentation
  6. **(별도)** subtoken splitter — 우리도 미구현, 아직 fork 에 없음. jaytoone 의지에 따라 협업
- **upstream 이 bundled PR 선호** → 한 번에 큰 PR. 단 회귀 가드는 동일 (golden + 105 unit)
- **upstream 응답 없거나 보류** → fork 단독 운영 (downstream maintenance)

PR 분해 시 **README 수정은 절대 포함 X** (§6-7 참조).

## 8. 다음 세션이 처음 할 행동

1. `cd /Users/d9ng/privateProject/tunaCtx`
2. 본 문서 (`docs/refactor/HANDOFF.md`) 읽기
3. `git log --oneline -5` 로 최신 commit 확인 — `29f241c` 가 마지막이어야 함
4. `.venv-golden/bin/python tests/golden/run_golden.py` 로 15/26 확인 (11 fallback drift 는 §6-1 함정으로 알려진 상태)
5. `.venv-golden/bin/python -m pytest tests/unit -q` 로 105/0 확인
6. upstream issue #1 의 jaytoone 응답 확인 — `gh issue view 1 --repo jaytoone/CTX --comments` (PR shape 결정 후 5단계 분해 첫 PR 시작 가능)
7. user 의 새 요청 들으며 본 문서의 §6 함정 회피

## 9. 의도적으로 안 한 것 (다음 세션도 따를 것)

- ✗ paper 작성, paper 관련 README 추가
- ✗ 마케팅 톤 (benchmark 자랑, "1.9x higher TES" 같은 것)
- ✗ **upstream PR 에 README.md 포함** (Cycle-3.5 결정, §6-7 참조 — fork 와 upstream 의 사용자 페르소나 다름)
- ✗ archival benchmark 11+개의 BM25 통합
- ✗ retrieval 알고리즘 변경
- ✗ `~/.claude/settings.json` 의 hook command 를 명시적 user 승인 없이 변경
- ✗ 신규 MCP server 또는 hook event 추가
- ✗ tests/golden 픽스처 데이터의 production-coded 변경 (production behavior 변화 없는 cascade 만 `--update` 로 갱신)

## 10. 환경 메타

- macOS Darwin 25.4.0
- 작업 디렉토리: `/Users/d9ng/privateProject/tunaCtx` (clone 후 `origin = hang-in/tunaCtx` 추가, GitHub 정식 fork 아님)
- system python3: `/opt/homebrew/bin/python3` (3.14, PEP 668 protected, **rank_bm25 미설치**)
- dev venv: `.venv-golden/bin/python` (3.14, rank_bm25 + numpy + sklearn + networkx + ctx-retriever editable 설치됨)
- pipx venv: `~/.local/pipx/venvs/ctx-retriever/bin/python` (3.14, 동일 패키지 + 격리 — **현재 hook command 가 사용 중인 python**)
- vec-daemon / bge-daemon: pipx python 으로 기동 중 (Cycle-3 검증 시점 PID 24808 / 25006)
- gh CLI: 인증 완료 (`dghong-d9ng` account)
- Claude Code: 본 conversation 의 hook 동작 확인됨 (UserPromptSubmit hook 이 prompt 마다 fire)
