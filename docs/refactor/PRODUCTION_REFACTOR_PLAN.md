# Production Refactor Plan — CTX

| 항목 | 값 |
|---|---|
| 작성일 | 2026-05-05 |
| 작성자 | Opus 4.7 (1M context) |
| 대상 브랜치 | `refactor/production-ready` (base: `master` @ `201c810`) |
| 실행 모델 | Sonnet 4.6 (병렬 가능 작업은 single-message multi Agent call) |
| 리뷰 도구 | `codex exec` v0.122.0 (최종 1회, 필요 시 mid-checkpoint 추가) |
| 보존 대상 | `~/.claude/settings.json` 의 hook command path, stdin/stdout 프로토콜, 기존 캐시 파일 포맷 |

---

## 0. 배경

지난 리뷰(2026-05-05)에서 식별된 production-readiness 부족분 4건을 한 사이클로 해소한다.

근거: 본 plan 하단의 "참고: 코드베이스 사실 확인" 절 참조.

핵심 위험 요소
- `src/hooks/bm25-memory.py` 가 1837줄 단일 파일 — production hot path 의 god module.
- production hook 의 atomic write / 캐시 무효화 / fallback 경로에 unit test 없음.
- eval 쪽 `src/retrieval/adaptive_trigger.py` 와 production 쪽 `bm25-memory.py` 가 **별개의 BM25 토크나이저/스코어러를 보유** — 한쪽 개선이 다른 쪽으로 전파되지 않아 eval 점수와 실제 hook 품질이 표류 가능.
- `bm25-memory.py` 는 telemetry instrument 가 없음 — 본인이 한 변경의 효과를 자기 데이터로 측정 불가.

---

## 1. 스코프

### Task A — `bm25-memory.py` 모듈 분해

**목표**: 1837줄 단일 파일을 책임 단위로 분해하고 orchestrator 를 250줄 이하로 축소.

**현재 파일 내부 섹션 마커** (작성자가 이미 `# ── ... ──` 으로 명시한 경계):

| 라인 범위 | 섹션 | 분리 대상 모듈 |
|---|---|---|
| 39-300 | Tokenizer + stopwords + stem + `tokenize` + `expand_query_tokens` | `_bm25/tokenizer.py` |
| 73-301 | Semantic rerank (vec-daemon, BGE cross-encoder, synonym fusion) | `_bm25/rerank.py` |
| 84-95 | Auto-tune reader (`ctx-auto-tune.json`) | `_bm25/autotune.py` |
| 351-524 | G1 Decision Corpus (git head + build/get + cache) | `_bm25/corpus.py` |
| 526-742 | Ranker primitives (`embed_corpus_items`, `dense_rank_decisions`, `rrf_merge`, `bm25_rank_decisions`, `hybrid_rank_decisions`) | `_bm25/ranker.py` |
| 743-1009 | G2-DOCS BM25 + hybrid search | `_bm25/docs_search.py` |
| 1010-1240 | G2 code file discovery + reindex check + grep fallback + citation log | `_bm25/code_search.py` |
| 1241-1306+ | G2 hooks file BM25 search | `_bm25/hooks_search.py` |
| 나머지 | stdin parse → 분기 dispatch → 컨텍스트 조립 | `bm25-memory.py` (orchestrator) |

**불변 제약**
- `~/.claude/settings.json` 에 등록된 `bm25-memory.py` 경로는 그대로. 진입점 파일명/위치 변경 금지.
- stdin JSON 스키마 / stdout 출력 포맷 변경 금지.
- 캐시 파일 경로(`.omc/decision_corpus.json`, `.omc/docs_corpus_emb.json`) 변경 금지.
- env var 이름 변경 금지(`CTX_DISABLE_SEMANTIC_RERANK`, `CTX_CROSS_ENCODER`, `CTX_TELEMETRY` 등).

**Acceptance 기준**
- `bm25-memory.py` ≤ 300 줄.
- `_bm25/*.py` 각 파일 ≤ 400 줄.
- 골든 픽스처(Phase 0) 출력 100% 일치.
- p50/p95 latency ±10% 이내(측정 방법: Phase 0 픽스처에 시간 측정 옵션 포함).

**산출물**: `src/hooks/_bm25/__init__.py` + 8개 모듈 + thin orchestrator.

---

### Task B — Production hook 단위 테스트

**목표**: `~/.claude/settings.json` 을 직접 건드리는 쓰기 경로에 회귀 가드 깔기.

**범위**
- `tests/unit/test_settings_patcher.py`
  - atomic write (temp + os.replace)
  - 타임스탬프 backup 생성
  - idempotency (두 번 patch 시 중복 없음)
  - dry-run 동작
  - unpatch 동작
  - 손상된 JSON 입력 처리
- `tests/unit/test_install_cli.py`
  - 기존 다른 hook 보존
  - PostToolUse matcher 동일 그룹에 머지
  - 진입점 commands 정확
- `tests/unit/test_chat_memory_fallback.py`
  - vault.db 없음 → degrade 동작
  - vec-daemon socket 없음 → BM25-only fallback + `⚠ vec-daemon down` 출력
- `tests/unit/test_bm25_memory_cache.py`
  - git HEAD 변경 시 `.omc/decision_corpus.json` 재빌드
  - HEAD 동일 시 캐시 hit (재빌드 안 함)
  - corrupted cache 감지 시 안전하게 재빌드

**인프라**
- `pyproject.toml` 의 `[tool.pytest.ini_options]` 섹션 추가.
- 패키지 매핑(`ctx_retriever` ↔ `src/`) 정합성 확인 — 현재 `[tool.setuptools] packages` 와 실제 `src/` 디렉토리 구조가 어긋나 있을 가능성. 필요 시 `[tool.setuptools.packages.find]` 로 정리.
- `tests/unit/conftest.py` 에 임시 디렉토리 / mock subprocess 헬퍼.

**Acceptance 기준**
- `pytest tests/unit -q` 모두 통과.
- 위 4개 모듈 line coverage ≥ 70%.

---

### Task C — eval ↔ production BM25 통합

**목표**: 토크나이저와 BM25 스코어링을 단일 모듈에서 공유 — eval(`adaptive_trigger.py`) 과 production(`bm25-memory.py`) 양쪽이 같은 코드 경로를 사용.

**전제**: Task A 완료 후 진행 (A 산출물의 `_bm25/tokenizer.py`, `_bm25/ranker.py` 가 통합 베이스).

**작업**
1. `_bm25/tokenizer.py` 와 `_bm25/ranker.py` 의 공개 API 를 `src/retrieval/bm25_core.py` 또는 공유 위치로 승격(또는 직접 import).
2. `src/retrieval/adaptive_trigger.py` 의 `BM25Okapi` 직접 호출 부분을 공유 API 경유로 변경.
3. `adaptive_trigger.py` 내 자체 토큰 분할 로직을 공유 토크나이저로 대체(쿼리/코퍼스 양쪽).
4. `benchmarks/eval/doc_retrieval_eval_v2.py` 재실행으로 회귀 검증.

**Acceptance 기준**
- `python3 benchmarks/eval/doc_retrieval_eval_v2.py` 결과:
  - 전체 R@3 ≥ 0.852 (현재 0.862, 마진 -0.010)
  - keyword R@3 ≥ 0.714 (현재 0.724)
  - heading_paraphrase R@3 == 1.000 (회귀 0)
- 토크나이저 import 경로가 단 하나(`from src.hooks._bm25.tokenizer import tokenize` 또는 등가).

---

### Task D — `bm25-memory` telemetry instrument

**목표**: `bm25-memory.py` orchestrator 에 telemetry 이벤트 emit 추가. 자기 변경의 효과를 자기 데이터로 측정 가능하게 만든다.

**전제**: Task A 완료 후 진행(orchestrator 가 thin 해진 상태에서 instrument).

**기존 인프라 활용**
- `src/hooks/_ctx_telemetry.py` (210줄) — `chat-memory.py` 가 이미 사용 중.
- 출력: `~/.claude/ctx-retrieval-events.jsonl` <!-- ⚠ post-Phase-9 정정: 실제 구현은 `~/.claude/ctx-telemetry.jsonl` 사용. 코드(`_ctx_telemetry.py:33`)와 README 가 source of truth. -->
- 활성화: `CTX_TELEMETRY=1` env 또는 `~/.claude/ctx-telemetry.enabled` 파일 존재.
- 비활성화 시 zero overhead(early return).

**emit 이벤트 스키마** (`retrieval_event` v1.1 기존 schema 따름)
- `hook=bm25-memory`
- `query_type` (`_classify_query_type` 결과)
- `g1_top_score_bm25`, `g1_top_score_dense` (이미 `_last_retrieval_scores` 에 캡처되고 있음)
- `g2_docs_count`, `g2_code_count`, `g2_hooks_count`
- `fallback_reasons` (예: `vec_daemon_down`, `bge_daemon_down`, `mcp_db_stale`)
- `latency_ms` (전체 hook 처리 시간)

**emit 패턴**
- 비차단(파일 append, fsync 안 함).
- exception 시 silently drop — telemetry 가 hook 을 절대 죽이지 않도록.

**Acceptance 기준**
- `CTX_TELEMETRY=1 echo '{"prompt": "test"}' | python3 src/hooks/bm25-memory.py` 후 `~/.claude/ctx-retrieval-events.jsonl` 마지막 라인에 hook=bm25-memory 이벤트 존재.
- `CTX_TELEMETRY` 미설정 시 jsonl 추가 안 됨, latency 영향 ≤ 1ms.
- `tests/unit/test_bm25_memory_telemetry.py` 추가.

---

## 2. 의존 그래프 / 실행 순서

```
Phase 0 ──► Task A ──┬──► Task C
(픽스처)              ├──► Task D
                     │
            Task B ──┘ (독립, A 와 병렬)
                     │
                     ▼
                  Phase 9 (codex 리뷰, 모든 task 완료 후)
```

**Wave 분할**

| Wave | 작업 | 병렬화 | 모델 |
|---|---|---|---|
| 0 | 골든 픽스처 캡처 | — | Sonnet 1개 |
| 1 | Task A + Task B | 병렬 (file-disjoint) | Sonnet 2개 동시 |
| 2 | Task C | A 완료 후 단독 | Sonnet 1개 |
| 3 | Task D | A 완료 후 단독 (C 와 병렬 가능하나 ranker.py 동시 수정 위험 → 순차 권장) | Sonnet 1개 |
| 9 | codex 최종 리뷰 | — | codex exec |

**Wave 1 의 file-disjoint 근거**
- Task A: `src/hooks/bm25-memory.py`, `src/hooks/_bm25/*` (신규)
- Task B: `tests/unit/*` (신규), `pyproject.toml` (라인 추가만)
- 겹치는 영역 없음 → 동시 실행 안전.

**Wave 2 ↔ Wave 3 순서 결정 근거**
- C 는 `_bm25/tokenizer.py`, `_bm25/ranker.py` 를 read 하고 `adaptive_trigger.py` 를 수정.
- D 는 orchestrator(`bm25-memory.py`) 에 instrument 호출 추가, `_bm25/ranker.py` 는 read-only.
- 이론상 병렬 가능하나 `ranker.py` 시그니처 미세 변경 가능성 있어 순차 권장.

---

## 3. 회귀 가드 (안전장치)

### Phase 0: 골든 픽스처 (반드시 A 시작 전)

**산출물**: `tests/golden/bm25_memory_outputs.jsonl`

대표 prompts 10-15개에 대해 현재 `bm25-memory.py` 출력을 (deterministic 모드로) 캡처.

prompts 카테고리
- 키워드 단일 ("BM25 어디 있지?")
- 한국어 paraphrase ("의사결정 기억 어떻게 관리됨?")
- code-finding ("vec-daemon 코드 위치")
- 의미 회피 ([noctx] prefix)
- 빈 prompt / 매우 짧은 prompt

각 픽스처에 기록할 필드
- input prompt
- env (CTX_DISABLE_SEMANTIC_RERANK 강제 ON 으로 비결정성 제거)
- expected stdout
- expected exit code
- elapsed_ms (정보용)

**비결정성 제거 전략**
- vec-daemon / bge-daemon 비활성화 (`CTX_DISABLE_SEMANTIC_RERANK=1`, `CTX_CROSS_ENCODER=0`)
- git HEAD 고정(현재 `master` HEAD `201c810`)
- 캐시 강제 재빌드 후 동일 입력 2회 출력 일치 확인

A 완료 후 동일 픽스처 재실행으로 출력 비교 — diff 0 줄이 acceptance.

### 각 Task acceptance 는 §1 의 항목별 기준 따름.

### 롤백
- 모든 작업은 `refactor/production-ready` 브랜치 위. master 미변경.
- Task 별 commit 분리 → 부분 롤백 용이.
- production 사용자(`~/.claude/settings.json` wired 한 본인) 환경에는 머지 전까지 영향 없음.

---

## 4. codex 리뷰 (Phase 9)

**기본 명령**
```bash
codex exec --model gpt-5.1 \
  "Review the diff between master and refactor/production-ready. \
   Focus on: (1) bm25-memory.py 진입점/프로토콜 보존, \
   (2) atomic write 정합성, (3) 신규 _bm25/* 모듈의 SRP 준수, \
   (4) 토크나이저 통합으로 인한 eval 회귀 가능성, \
   (5) telemetry path 의 zero-overhead 보장. \
   Output: severity 별 finding 목록 + 구체적 라인 인용."
```

**리뷰 입력**
- `git diff master..refactor/production-ready` 전체.
- 본 PLAN.md 자체.
- benchmark 회귀 결과 JSON.

**리뷰 산출물**
- `docs/refactor/REVIEW_codex_<YYYYMMDD>.md` — Severity Critical/Major/Minor 분류.
- 각 finding 에 대한 (a) 수용/반려 결정 (b) 후속 action item.

**Mid-checkpoint 리뷰** (선택)
- 사용자 명시 요청 시에만 트리거.
- 기본 구성: Wave 1 종료 시점에서만 — A 의 분해가 가장 위험도가 높음.

---

## 5. 메모리에 기록할 항목 (작업 종료 후)

- `feedback` 타입: "production refactor 시 hook 진입점 경로/stdin 스키마는 절대 변경 금지 (사용자 settings.json wired)" — 향후 유사 변경에 동일 제약 적용.
- `project` 타입: "bm25-memory 분해 후 _bm25/* 패키지가 production hot path. 추후 hook 변경은 orchestrator 레이어에서만 시작."
- `reference` 타입: "production hook 회귀 가드 픽스처는 `tests/golden/bm25_memory_outputs.jsonl`."

---

## 6. 비스코프 (의도적 제외)

다음은 **이번 사이클에서 다루지 않는다** — 별도 사이클 후보.

- `src/retrieval/adaptive_trigger.py` 자체의 god object 해체 — eval 한정 영향, 외부 R@5 추가 개선 작업과 묶어서 별도 진행. (참고: iter11 재측정 기준 Mean R@5=0.595, 0.152 는 pre-fix baseline 으로 stale)
- `chat-memory.py` 분해 — 현재 529줄로 임계 미만, vault.db 통합 변경과 함께 진행.
- 외부 코드베이스 R@5 개선, AST 파서 교체, GraphRAG 통합 등 알고리즘 변경.
- 새 retrieval 전략 추가, README 갱신, packaging 변경(버전 bump 제외).

---

## 7. 참고: 코드베이스 사실 확인 (2026-05-05 기준)

| 항목 | 값 |
|---|---|
| `src/hooks/bm25-memory.py` | 1837 lines |
| `src/hooks/chat-memory.py` | 529 lines |
| `src/hooks/_ctx_telemetry.py` | 210 lines (이미 존재, chat-memory 가 사용) |
| `src/cli/install.py` | 393 lines |
| `src/cli/settings_patcher.py` | 169 lines (atomic write 구현 검증 완료) |
| `src/retrieval/adaptive_trigger.py` | 1063 lines (eval 한정, production hook 미사용 — `grep -nr AdaptiveTriggerRetriever src/hooks src/cli` → 0건) |
| 현재 `tests/` 내용 | 4 files, unit test 사실상 없음 (eval 스크립트 위주) |
| `pyproject.toml` | `pytest>=7.0` 이미 dev extra 에 포함 |

---

## 8. Task Tracker 매핑

| Plan ID | TaskList ID | Status |
|---|---|---|
| Phase 0 | #1 | pending |
| Task A | #2 | pending (blocked by #1) |
| Task B | #3 | pending |
| Task C | #4 | pending (blocked by #2) |
| Task D | #5 | pending (blocked by #2) |
| Phase 9 | #6 | pending (blocked by #2,#3,#4,#5) |
