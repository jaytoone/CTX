# Upstream sync inventory — 2026-05-08

> Trial merge 결과. master 변경 안 함 — 본 문서는 PR 작업 전략용 참고 자료.

## upstream/master 11 신규 commits

`upstream/master` (`fd84cf9`, 2026-05-08) — fork base `201c810` 이후 11 commits.

Author = **Be2Jay** (jaytoone이 GitHub username 변경 — issue 답변자 'jaytoone'과 동일인).

| Hash | Subject | 우리 작업 영향 |
|---|---|---|
| **08e262b** | `fix: Korean tokenizer gap in eval pipeline + 6 regression tests` (commit msg에 **`Related: hang-in/tunaCtx tokenizer.py confirms same pattern`**) | 🎯 **PR-1 핵심 motivation 일부 선반영** — `doc_retrieval_eval_v2.py` 만 fix됨. 우리는 4 사이트 추가 통합. |
| fd84cf9 | `docs: add CJK intent comment to production tokenize() regex` | 무관 (주석만) |
| 9cd2371 | `docs: fix HN item ID 47996700→48017090` | 무관 |
| 982c043 | `feat: market signal monitor` (`scripts/market-signals.py`) | 무관 |
| **b799aae** | `chore: batch commit accumulated session work` (benchmarks/hooks/cli/docs/plugin/hf_space) | 🔴 거대 batch — 광범위 충돌 원인 |
| ba7df3d | `fix: add sqlite-vec to deps + guard import in chat-memory.py` | 🟡 우리 fork sqlite_vec fallback과 충돌 |
| 80fe738 | `docs: restructure install section` | 🟡 README 충돌 |
| ff34059 | `feat: --reseed flag, sharing trigger, PyPI baseline` | 🟡 install 변경 |
| 3964d39 | `feat: seed vault.db with git history on install` | 🟡 install 변경 |
| 9fe7d6d | `fix: replace PID file guard with fcntl.flock in vec-daemon and bge-daemon` | 🟡 daemon 충돌 |
| 126f1d7 | `fix: update stale R@5=0.152 → 0.595 across docs` | ✅ issue#2 응답 commit — 우리도 처리 완료 |

## Trial merge 결과 — 16개 파일 conflict

worktree `/tmp/tunaCtx-trial-merge`에서 격리 실행. master 영향 없음.

| File | Hunks | 충돌 원인 |
|---|---|---|
| `.gitignore` | 1 | upstream에 `.playwright-mcp/` 등 추가, 우리는 `.omc/` 등 |
| `CLAUDE.md` | 1 | fork persona vs upstream R@5 갱신 |
| `LICENSE` | 1 | metadata (예: copyright holder line) 차이 추정 — 확인 필요 |
| `README.md` | 1 | fork persona vs upstream pip-first 재구성 |
| `benchmarks/eval/doc_retrieval_eval_v2.py` | 1 | **08e262b의 Korean tokenizer fix** vs 우리 Task C `_bm25` 통합 |
| `benchmarks/results/doc_retrieval_eval_v2.md` | 1 | 결과 갱신 차이 |
| `src/cli/install.py` | 1 | upstream `--reseed`/`vault seed` vs 우리 hash-based atomic install |
| `src/evaluator/coir_evaluator.py` | 1 | 양측 _bm25 통합 시점 차이 |
| `src/hooks/_ctx_telemetry.py` | 1 | telemetry 모듈 양측 변경 |
| `src/hooks/bge-daemon.py` | 1 | upstream `fcntl.flock` (9fe7d6d) vs 우리 PID guard |
| `src/hooks/bm25-memory.py` | 1 | upstream CJK 주석 + 통합 분해 vs 우리 1837→300 LOC orchestrator (PR-4 영역) |
| `src/hooks/chat-memory.py` | 2 | upstream sqlite-vec import guard (ba7df3d) vs 우리 fallback |
| `src/hooks/utility-rate.py` | 1 | utility-rate 양측 변경 |
| `src/hooks/vec-daemon.py` | 1 | upstream fcntl.flock vs 우리 vec-daemon 변경 |
| `src/retrieval/adaptive_trigger.py` | 1 | upstream eval 갱신 vs 우리 Task C _bm25 통합 |
| `src/retrieval/bm25_retriever.py` | 1 | 양측 _bm25 통합 시점 차이 |

`b799aae` (거대 batch commit) 가 conflict의 8할 원인. 단일 파일에 여러 변경이 한꺼번에 들어와 line-level 충돌이 광범위.

## 결론 — PR 작업 전략

**fork master ↔ upstream master 직접 머지는 비권고**. 16 conflict + 거대 batch commit 정렬 비용이 PR 가치를 초과.

**권고: upstream/master 위에서 새 브랜치 분기 + 동등한 fix를 새로 commit** (PR 별).

| PR | base | 작업 내용 |
|---|---|---|
| **PR-1** (tokenizer 통합) | `upstream/master` 위 `feat/upstream-pr1-tokenizer` | `_bm25/tokenizer.py` 신규 + 4 eval 사이트(g1_docs, g1_longterm, g2_paraphrase, bm25_retriever — bm25_retriever는 dedup 회귀로 제외) 통합. **08e262b의 doc_retrieval_eval_v2.py fix는 이미 머지됨이라 그 파일은 우리 PR에서 빠짐** |
| **PR-2** (tests) | `upstream/master` 위 `feat/upstream-pr2-tests` | 80 unit (PR-1 의존 분리) + 26 golden + golden runner |
| **PR-3** (deterministic sort) | `upstream/master` 위 `feat/upstream-pr3-determinism` | upstream의 `bm25-memory.py` monolith 안에서 sort 사이트 위치 찾아 동등 tiebreak 적용. fork의 `_bm25/ranker.py:49/79/153` ↔ upstream monolith line 매핑 필요 |

**fork master는 그대로 유지** — fork persona/실험 코드/PR-4(decomposition) prep 영역. 향후 PR-4 머지 후 upstream과 자연스럽게 합류.

## 다음 액션

- [ ] PR-1: `upstream/master` 분기 브랜치 생성, `_bm25/tokenizer.py` 추출 + eval 사이트 통합 patch
- [ ] PR-2: 80 unit + 26 golden 을 upstream monolith 호출 형태로 재작성
- [ ] PR-3: upstream `bm25-memory.py` 안의 sort 사이트(L?, L?, L?) 찾아 tiebreak patch
- [ ] issue #1 회신 본문에서 "08e262b 이미 부분 적용됨" 명시
