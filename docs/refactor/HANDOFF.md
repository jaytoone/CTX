# 핸드오프 — tunaCtx production-level refactor 사이클

| 항목 | 값 |
|---|---|
| 마지막 갱신 | 2026-05-05 |
| 작업 식별자 | Phase 0 → Task A/B/C/D → Phase 9 → Cycle-2 |
| 현재 브랜치 | `master` (= `origin/master` = `hang-in/tunaCtx:master`) |
| 마지막 commit | `2a68213 docs(refactor): annotate telemetry jsonl path discrepancy in plan` |
| 회귀 가드 상태 | golden **26/26 PASS** / pytest **105 PASS / 0 skip** |
| 원본 upstream | `https://github.com/jaytoone/CTX` (remote: `upstream`) |
| Fork remote | `https://github.com/hang-in/tunaCtx` (remote: `origin`) |
| Upstream issue | `https://github.com/jaytoone/CTX/issues/1` (fork 알림) |

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

### 현재 알려진 제약

- **system python3** (`/opt/homebrew/bin/python3` = 3.14, PEP 668 보호) 에 `rank_bm25` / `numpy` 미설치
- 결과: hook 이 BM25 fallback 경로로 실행 (G2-GREP / session-notes / world-model 만 활용, BM25 ranking quality 미발휘)
- vec-daemon / bge-daemon 은 다음 Claude Code 세션 시작 시 자동 기동되도록 구성됨 (현재 세션 검증 시점에는 down 상태 — hook output 에 `⚠ Semantic layer: vec-daemon down — BM25-only mode` 표시)

### BM25 / 의미층 활성화 (옵션 C — pipx 격리, 권장)

```bash
# 1. pipx 설치 (없으면)
brew install pipx
pipx ensurepath

# 2. ctx-retriever 격리 설치
pipx install /Users/d9ng/privateProject/_research/_util/CTX
# → ~/.local/pipx/venvs/ctx-retriever/bin/ 에 ctx-install / ctx-telemetry / python 위치

# 3. hook command 를 pipx python 으로 갱신 — 두 가지 방식:
#    (a) settings.json 직접 편집 (단순, 한 번에)
#    (b) install.py 에 --hook-python 옵션 추가 (영구적 솔루션, 사이클 추가)

# (a) 방식 예시:
# python3 $HOME/.claude/hooks/bm25-memory.py --rich
# →
# /Users/d9ng/.local/pipx/venvs/ctx-retriever/bin/python $HOME/.claude/hooks/bm25-memory.py --rich

# 4. vec-daemon / bge-daemon 도 동일하게 pipx python 사용:
nohup ~/.local/pipx/venvs/ctx-retriever/bin/python ~/.local/share/claude-vault/vec-daemon.py >/dev/null 2>&1 &
nohup ~/.local/pipx/venvs/ctx-retriever/bin/python ~/.local/share/claude-vault/bge-daemon.py >/dev/null 2>&1 &
```

### BM25 / 의미층 활성화 (옵션 B — 현재 dev venv 사용, 빠름)

```bash
# .venv-golden 가 이미 ctx-retriever editable + rank_bm25 + numpy + sklearn + networkx 설치됨
# settings.json 에서 5개 hook command 의 'python3' 를 venv python 으로 교체:
# python3 $HOME/.claude/hooks/...
# →
# /Users/d9ng/privateProject/_research/_util/CTX/.venv-golden/bin/python $HOME/.claude/hooks/...

# vec-daemon / bge-daemon 도 동일하게:
nohup /Users/d9ng/privateProject/_research/_util/CTX/.venv-golden/bin/python ~/.local/share/claude-vault/vec-daemon.py >/dev/null 2>&1 &
nohup /Users/d9ng/privateProject/_research/_util/CTX/.venv-golden/bin/python ~/.local/share/claude-vault/bge-daemon.py >/dev/null 2>&1 &
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
cd /Users/d9ng/privateProject/_research/_util/CTX

# 회귀 가드 (deterministic hook output)
python3 tests/golden/run_golden.py
# 기대: 26/26 fixtures passed

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

## 7. upstream 처리 (참고)

`https://github.com/jaytoone/CTX/issues/1` 등록됨. 응답 시 시나리오:
- **upstream 이 PR 환영** → 본 fork 의 변경을 5개 정도 작은 PR 로 분해 (Task A 분해, Task B 테스트, Task C 통합, packaging fix, telemetry instrument 별도). 각각 독립 가능하도록.
- **upstream 응답 없거나 보류** → fork 단독 운영. README 에 명시된 대로 downstream maintenance.

## 8. 다음 세션이 처음 할 행동

1. `cd /Users/d9ng/privateProject/_research/_util/CTX`
2. 본 문서 (`docs/refactor/HANDOFF.md`) 읽기
3. `git log --oneline -5` 로 최신 commit 확인 — `2a68213` 가 마지막이어야 함
4. `python3 tests/golden/run_golden.py` 로 26/26 확인
5. user 의 새 요청 들으며 본 문서의 §6 함정 회피

## 9. 의도적으로 안 한 것 (다음 세션도 따를 것)

- ✗ paper 작성, paper 관련 README 추가
- ✗ 마케팅 톤 (benchmark 자랑, "1.9x higher TES" 같은 것)
- ✗ archival benchmark 11+개의 BM25 통합
- ✗ retrieval 알고리즘 변경
- ✗ `~/.claude/settings.json` 의 hook command 를 명시적 user 승인 없이 변경
- ✗ 신규 MCP server 또는 hook event 추가
- ✗ tests/golden 픽스처 데이터의 production-coded 변경 (production behavior 변화 없는 cascade 만 `--update` 로 갱신)

## 10. 환경 메타

- macOS Darwin 25.4.0
- system python3: `/opt/homebrew/bin/python3` (3.14, PEP 668 protected, **rank_bm25 미설치**)
- dev venv: `.venv-golden/bin/python` (3.14, rank_bm25 + numpy + sklearn + networkx + ctx-retriever editable 설치됨)
- gh CLI: 인증 완료 (`dghong-d9ng` account)
- Claude Code: 본 conversation 의 hook 동작 확인됨 (UserPromptSubmit hook 이 prompt 마다 fire)
