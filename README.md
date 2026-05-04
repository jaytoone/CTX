# tunaCtx

원본 [jaytoone/CTX](https://github.com/jaytoone/CTX) 를 production-level 로 리팩토링/보강한 fork.
retrieval 알고리즘은 원본 그대로 유지. Claude Code hook 구현이 실제 사용 환경에서 안전하게 운영되도록 모듈 분해, 패키징/설치 정합성, 회귀 가드, 텔레메트리만 손봤음.

## 어디에 어떻게 쓰는가

- **환경**: Claude Code (CLI / IDE / web).
- **트리거**: 사용자가 프롬프트 보낼 때마다 실행되는 `UserPromptSubmit` hook.
- **역할**: 프롬프트에 관련된 과거 의사결정(G1) + 관련 docs/코드(G2) 를 자동으로 context 에 주입.
- **외부 의존성**: LLM API 호출 없음. 로컬 BM25 + (옵션) vec-daemon (multilingual-e5-small) + (옵션) BGE cross-encoder.

### 설치

```bash
git clone https://github.com/hang-in/tunaCtx
cd tunaCtx
pip install -e .
ctx-install
```

`ctx-install` 동작:
1. `~/.claude/hooks/` 에 hook 파일 + `_bm25/` sub-package 복사 (atomic write + 타임스탬프 backup)
2. `~/.claude/settings.json` 에 hook command 등록 (기존 다른 도구 hook 보존, 멱등 — 재실행해도 중복 추가 없음)
3. 기존 hook 파일이 있으면 hash 비교 → 다르면 자동 update + `.backup_<TS>.py` 생성

플래그:

| 플래그 | 동작 |
|---|---|
| `--dry-run` | 실제 변경 없이 미리보기 |
| `--force-hooks` | hash 비교 없이 강제 덮어쓰기 |
| `--no-update-hooks` | 기존 파일 무조건 skip (사용자 수정 보존) |
| `--uninstall` | settings.json 의 hook 등록 제거 |
| `status` (positional) | 설치 상태 점검 |

### 텔레메트리 (opt-in, 로컬)

```bash
export CTX_TELEMETRY=1                          # 현재 셸만
# 또는: touch ~/.claude/ctx-telemetry.enabled    # 영구
```

활성화 시 `~/.claude/ctx-telemetry.jsonl` 에 retrieval event 기록 (network upload 없음).
비활성 시 zero-cost early return — orchestrator 모듈 로드 시 gate 1 회 평가 + 호출당 bool 체크 (≈ 0.01µs).

이벤트 종류: `hook_complete`, `prompt_received`, `g1_done`, `g2_docs_done`, `g2_code_done`, `g2_hooks_done`, `hook_invoked`. 스키마 명세는 `docs/refactor/TELEMETRY_SCHEMA.md`.

### 제어 태그

| 태그 | 효과 |
|---|---|
| `[noctx]` | 해당 프롬프트에서 CTX context 주입 disable |
| `[fix]` | anti-anchoring 모드 — 기존 구현을 그대로 베끼지 않도록 reminder 추가 |

`[fix]` 는 prompt 가 `fix:` / `bug:` / `refactor:` / `replace:` 로 시작할 때도 자동 트리거.

## 이 fork 에서 한 작업

원본 CTX 의 retrieval 알고리즘 변경 없음. production readiness 만 보강.

### 모듈 분해

`src/hooks/bm25-memory.py` (1837 줄 단일 파일) → orchestrator 300 줄 + `src/hooks/_bm25/` 11 개 모듈:

```
_bm25/
  tokenizer.py     # 한국어 조사 strip + Porter stemmer + stopword
  rerank.py        # vec-daemon bi-encoder + BGE cross-encoder
  autotune.py      # ctx-auto-tune.json 파라미터 reader
  corpus.py        # G1 decision corpus (git HEAD 키 캐시)
  ranker.py        # BM25 ranking primitives (canonical)
  docs_search.py   # G2-DOCS BM25 + hybrid
  code_search.py   # G2 code 파일 검색 + grep fallback
  hooks_search.py  # ~/.claude/hooks/*.py BM25 검색
  session.py       # 세션 로컬 상태 헬퍼
  injection.py     # P1 utility tracking
  output.py        # stdout/stderr 헤더 emit
```

각 모듈 ≤ 400 줄. stdin JSON 스키마, stdout 출력 포맷, 캐시 파일 경로(`.omc/decision_corpus.json`, `.omc/docs_corpus_emb.json`), 환경 변수 이름 모두 원본과 동일.

### eval ↔ production BM25 통합

- 단일 토크나이저: `_bm25/tokenizer.tokenize`
- 단일 BM25 ranking primitive: `_bm25/ranker.score_corpus_bm25`
- 통합된 caller:
  - `src/retrieval/adaptive_trigger.py`
  - `benchmarks/eval/doc_retrieval_eval_v2.py`
  - `src/retrieval/bm25_retriever.py`
  - `src/evaluator/coir_evaluator.py`
- archival 성격의 benchmark 스크립트(11+ 개)는 의도적으로 자체 구현 유지 — 과거 A/B 비교의 의미 보존

### 패키징 / 설치 정합성

- `_bm25/` sub-package 가 wheel 에 정상 포함되도록 `pyproject.toml` 의 `[tool.setuptools] packages` + `package-data` 수정
- `ctx-install` 이 `_bm25/` 디렉토리도 재귀 복사하도록 변경
- 기존 hook 파일에 대한 hash 기반 자동 update 정책 + `--force-hooks` / `--no-update-hooks` 플래그
- `_save_atomic`: temp 파일 + `os.replace` + 타임스탬프 backup. 신규 파일 생성 시 backup 반환값 정확성 보장.

### 안전성 보강

- `chat-memory.py:import sqlite_vec` 무방어 → `try/except ImportError` + graceful fallback (sqlite_vec 부재 환경에서도 hook 죽지 않음)
- `_bm25/code_search.py` G2-GREP 정렬: 동점 score 의 비결정성 제거 (`count` → `(-count, path)`)
- Telemetry path: 활성/비활성 gate 캐싱 + lazy import (비활성 시 hook latency 영향 없음)

## 테스트

### 회귀 가드 (deterministic hook output)

```bash
python3 tests/golden/run_golden.py
# → 26/26 fixtures passed
```

26 개 픽스처는 deterministic 모드(`CTX_DISABLE_SEMANTIC_RERANK=1`, `CTX_CROSS_ENCODER=0`)로 캡처된 hook stdout 의 byte-level 비교. G2-GREP 블록은 file list drift 방지를 위해 normalize 비교 (헤더 / count / "Start with" 형식만 검증).

카테고리 (각 카테고리는 fallback 경로 + BM25 경로 양쪽 캡처):
- keyword_single (3+3)
- korean_paraphrase (2+2)
- english_code (2+2)
- avoidance / `[noctx]` / `fix:` (2+2)
- empty / 매우 짧은 prompt (3+2)
- hooks_keyword (2+2)

### 단위 테스트

```bash
.venv-golden/bin/python -m pytest tests/unit -q
# → 82 passed in <2s
```

| 파일 | 테스트 수 | 영역 |
|---|---|---|
| `test_settings_patcher.py` | 22 | atomic write, backup, idempotency, dry-run, unpatch, corrupted JSON |
| `test_install_cli.py` | 32 | hook 복사 / hash update / force flag / no-update flag, settings merge |
| `test_chat_memory_fallback.py` | 9 | vault.db 없음, vec-daemon down, sqlite_vec 부재, invalid stdin |
| `test_bm25_memory_cache.py` | 7 | HEAD-keyed cache invalidation, corrupted cache 복구 |
| `test_bm25_memory_telemetry.py` | 6 | 활성/비활성 latency, fallback reason capture, exception 시 graceful |
| `test_code_search_sort.py` | 6 | `(-count, path)` deterministic sort |

커버리지: `settings_patcher.py` 93%, `install.py` 73%.

### BM25 통합 검증

```bash
.venv-golden/bin/python scripts/verify_bm25_unified.py
# → ALL CHECKS PASSED
```

`tokenize` import / `score_corpus_bm25` 동작 / `AdaptiveTriggerRetriever` corpus build 가 모두 통합된 `_bm25/` 경로를 통과하는지 검증.

## 알려진 후속 항목

- `tests/golden/run_golden.py` 가 stderr 비교 미실시 — `emit_output()` 의 stderr regression 가드 없음 (다음 사이클)
- `ctx-install --uninstall` 이 hook 파일 자체와 `_bm25/` 디렉토리 cleanup 안 함 (settings.json 등록만 제거)
- `_bm25/__init__.py` 의 public re-export 문서와 실제 구현 mismatch (현재 callers 가 submodule 직접 import 라 동작 문제는 아님)

## 디렉토리 구조

```
tunaCtx/
  src/
    hooks/
      bm25-memory.py        # orchestrator (300 lines)
      _bm25/                # 분해된 11 개 sub-module (canonical)
      chat-memory.py
      memory-keyword-trigger.py
      g2-fallback.py
      _ctx_telemetry.py
    retrieval/              # 원본 retrieval strategy (8 종)
    cli/
      install.py            # ctx-install
      settings_patcher.py   # atomic settings.json patcher
      telemetry.py          # ctx-telemetry
  tests/
    golden/                 # hook output 회귀 가드 (26 fixtures)
    unit/                   # 단위 테스트 (82)
  benchmarks/
    eval/
    results/
  docs/
    refactor/
      PRODUCTION_REFACTOR_PLAN.md   # 본 사이클 plan 문서
      TELEMETRY_SCHEMA.md           # 텔레메트리 이벤트 스키마
  scripts/
    verify_bm25_unified.py  # BM25 통합 sanity check
```

## 라이선스

MIT. 원본 [jaytoone/CTX](https://github.com/jaytoone/CTX) (MIT) 의 copyright 와 함께 명시. `LICENSE` 참조.
