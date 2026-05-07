# Upstream issue #1 — reply draft (response to jaytoone comment 2026-05-07)

목적: jaytoone 의 P0/P1/P2 우선순위 + boundary design 우려 + co-maintain 제안에 대한 회신.

## Reply body (English, paste into https://github.com/jaytoone/CTX/issues/1)

---

Hey jaytoone — thanks for the detailed triage. Reordering my plan to match your priorities. sqlite_vec is dropped (already in 0.3.14), and the four pieces below map 1:1 to what you flagged.

### Revised PR plan (4 stages)

| Order | Piece | Maps to your ask | Risk |
|---|---|---|---|
| **PR-1** | Tokenizer unification (`_bm25/tokenizer.tokenize` as single canonical entry; eval + production both call it) | P0 (you wanted this most) | Lowest — token stream byte-identical, BM25 score delta = 0 on regression suite |
| **PR-2** | Test suite: 82 unit tests under `tests/unit/` + 26 golden fixtures under `tests/golden/` | P1 (CI gap) | None — additive |
| **PR-3** | Deterministic sort in `_bm25/code_search.py:233` (`scored.sort(key=lambda x: (-x[0], x[1]))` — score desc + path tiebreak) plus the `_bm25/ranker.py` sort sites at L49/L79/L153 | P2 (the non-determinism bug you mentioned) | Low — pure ordering fix |
| **PR-4** | 11-module decomposition under `src/hooks/_bm25/` | Pending boundary discussion (this comment) | Medium — depends on your boundary review |

I can hold PR-4 until the boundaries below pass your review. PR-1 → PR-2 → PR-3 are independent and can land in any order.

### Boundary design (re: "single-file is a deliberate tradeoff")

Your point on copy/audit ergonomics is valid — I want to address it head-on. The decomposition is **not** a generic "split by file size" refactor. Each module owns one role with no cyclic imports; the orchestrator (`bm25-memory.py`, ~300 LOC) wires them together. Module map:

| Module | LOC | Role | Imports from |
|---|---|---|---|
| `tokenizer.py` | 230 | Canonical `tokenize()` (Korean particle strip + Porter stem + stopword) | stdlib only |
| `corpus.py` | 240 | Decision corpus build + `_classify_query_type` | tokenizer |
| `ranker.py` | 270 | `score_corpus_bm25`, `hybrid_rank_decisions`, `last_retrieval_scores` | tokenizer, corpus |
| `docs_search.py` | 320 | `build_docs_bm25`, `hybrid_search_docs` (G2-DOCS) | tokenizer, ranker |
| `code_search.py` | 310 | Codebase graph + grep fallback (G2-CODE) | tokenizer |
| `hooks_search.py` | 100 | `~/.claude/hooks/*.py` BM25 (G2-HOOKS) | tokenizer, ranker |
| `rerank.py` | 240 | vec-daemon / cross-encoder rerank (optional) | stdlib + socket |
| `session.py` | 95 | World model + pending decisions snapshot | stdlib |
| `injection.py` | 170 | Final injection record writer | stdlib |
| `output.py` | 90 | Header lines + emit | stdlib |
| `autotune.py` | 70 | Top-K constants + flags | stdlib |
| `__init__.py` | 55 | Re-exports for orchestrator | (above) |

Properties:

- **No cycles** — DAG: `tokenizer → corpus → ranker → {docs_search, code_search, hooks_search}`; `rerank`, `session`, `injection`, `output`, `autotune` are leaves.
- **Single-file copy/audit preserved**: the orchestrator (`bm25-memory.py`) is still installable as one entry; the `_bm25/` package sits next to it. Users who copy the hook copy a directory of ≤320-LOC files instead of a 1837-LOC monolith — but each file is independently readable. If you'd prefer keeping the install footprint as a single concatenated `bm25-memory.py` (with the modules as dev-only sources), I can produce a build step that emits a flattened single-file artifact for distribution while keeping the modular sources for tests.
- **Each module has a focused unit-test file** under `tests/unit/` — no test reaches across two boundaries except the orchestrator-level ones.
- **Backward-compatible call sites**: `from _bm25.* import …` is the only change inside the orchestrator; external callers (Claude Code's hook contract) see no surface change.

If any boundary feels wrong (e.g., `injection`/`output` could fold, `hooks_search` could merge into `code_search`), I'm happy to redraw before the PR. The split I'd defend hardest is `tokenizer` and `ranker` — those are the two pieces that previously diverged between eval and production paths and caused the misleading benchmark numbers you mentioned.

### Co-maintain — yes, happy to

I use CTX daily, so the maintenance overhead is already paid on my end. Concretely I can take:

- Issue triage on weekday afternoons KST
- Hook reviews (BM25 / tokenizer / install machinery / golden fixtures)
- Release notes + version bumps in coordination with you

I'd defer to you on retrieval algorithm direction, paper alignment, and anything benchmark-facing — those are your design decisions and I want to keep upstream's voice intact. If a `MAINTAINERS.md` with explicit areas of ownership works for you, I can draft one as part of PR-2.

### Order of operations I'd suggest

1. I open **PR-1 (tokenizer)** this week — small, self-contained, validates the workflow.
2. After PR-1 lands, **PR-2 (tests)** — needs PR-1's tokenizer to be the import target.
3. **PR-3 (deterministic sort)** in parallel with PR-2 — independent.
4. We discuss PR-4 (decomposition) once 1-3 are in; I'll redraw boundaries based on your feedback above.

Let me know if the order or scope needs adjusting. Subtoken splitting stays out of all four PRs (separate cycle as agreed).

---

## Internal notes (do not paste)

### 우리 측 메시지 의도

| 항목 | 의도 |
|---|---|
| sqlite_vec drop | jaytoone 이 0.3.14 에서 자체 처리한 것 인정 (중복 PR 회피) |
| PR-1 ~ PR-3 순서 | jaytoone 우선순위(P0=tokenizer / P1=tests / P2=deterministic sort) 그대로 반영 |
| Boundary 표 | "deliberate tradeoff" 우려에 module-by-module 정량 답변 — DAG 무사이클 + LOC 분포 + 단위 테스트 1:1 매핑 |
| Flattened single-file 옵션 | jaytoone 의 "single-file is easier to copy/audit" 명시 수용 — build step 으로 양립 가능 제시 |
| Co-maintain | 수락 + 영역 분담 명시 (algorithm/paper = jaytoone, hook/install/test = us) — boundary 의 정치적 명료화 |
| Subtoken 명시 제외 | 이전 라운드 합의 ("separate cycle, not in fork yet") 재확인 |

### 발행 전 체크

- [ ] 위 본문에서 LOC 수치 (230, 240, 270 …) 는 추정치 — 실제 값으로 갱신 필요. 현재 `ls -la _bm25/` 결과(byte 단위)에서 도출 가능
- [ ] `code_search.py:233` 라인 번호 PR-3 시점에 master 와 일치하는지 확인 (drift 가능)
- [ ] PR-1 시동 시점에 issue 본문에서 5-stage → 4-stage 로 plan 갱신했음을 cross-link

### 후속 액션

1. 본 draft 사용자 검토 → 수정 후 issue 코멘트 발행
2. PR-1 (tokenizer) 브랜치 시작 — `feat/upstream-pr1-tokenizer`
3. HANDOFF.md §7 (upstream) 의 5-stage plan 을 4-stage 로 갱신 + sqlite_vec dropped 사유 기록
