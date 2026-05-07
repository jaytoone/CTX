Hey jaytoone — thanks for the detailed triage. Here's a status update with PRs opened (Draft) and four points worth flagging from the audit cycle that produced them.

## Three Draft PRs opened

| PR | Mapping to your priorities |
|---|---|
| #3 — `[Tokenizer]` Unify `_bm25.tokenizer` canonical entry across eval pipeline | P0 (the one you wanted most) |
| #4 — `[Docs Search]` Dedup root `README`/`CLAUDE`/`MEMORY` against same-name `docs/research/` files | P1 audit + an unrelated production-hook bug discovered along the way |
| #5 — `[Determinism]` Explicit tiebreak on 3 `ranker.py` sort sites | P2 (the "subtle non-determinism bug" you flagged) |

All three are **Draft** because the change sites live inside the `_bm25/` package layout (PR-4 territory, awaiting your boundary review). Once you've had a chance to look at the boundaries, I can either (a) cherry-pick onto the merged decomposition branch, or (b) re-author each change directly inside the upstream monolith and discard these Drafts. Either path is fine on my end.

I dropped `sqlite_vec fallback` from the original 5-stage plan since it's already in 0.3.14 (`ba7df3d`).

## Four findings worth flagging from the audit

### 1. Your `08e262b` already covers part of PR-1

Your `fix: Korean tokenizer gap in eval pipeline + 6 regression tests` (with the `Related: hang-in/tunaCtx tokenizer.py` attribution — appreciated) already addressed `doc_retrieval_eval_v2.py`. PR #3 covers the remaining three sites we found in the eval pipeline (`g1_docs_bm25_eval.py`, `g1_longterm_baseline_eval.py`, `g2_docs_paraphrase_eval.py`). Two further sites (`src/cli/telemetry.py`, `src/retrieval/bm25_retriever.py`) are intentionally kept divergent — rationale annotated inline (telemetry is identifier-frequency stats not BM25 ranking; `bm25_retriever` needs raw TF on code identifiers, and canonical's `dict.fromkeys()` dedup would flatten that).

### 2. Test count was 82, audit settled it at 80 + 26 golden

I quoted "82 unit tests + 26 golden" in the original issue body. After classifying tests for upstream relevance:

- **80** unit tests (upstream-ready: `test_trigger_classifier_ko.py` 45, `test_ast_improvements.py` 19, `test_chat_memory_fallback.py` 9, `test_code_search_sort.py` 7)
- **23** unit tests gated on PR-4 decomposition (`test_bm25_init_reexport.py`, `test_bm25_memory_cache.py`, `test_bm25_memory_telemetry.py`)
- **66** unit tests fork-only (atomic install machinery — `test_install_cli.py`, `test_settings_patcher.py`, `test_uninstall_cleanup.py`)

So the test-suite PR (when it comes) ships **80 + 26 golden**, not 82 + 26. Apologies for the ±2 drift in the original number.

### 3. PR #4 carries an unrelated production-hook bug fix

While re-running the golden suite I caught a real bug: `build_docs_bm25` indexes `docs/research/*.md` **and** root extras (`CLAUDE.md`, `README.md`, `MEMORY.md`) without name-collision dedup. When `docs/research/README.md` exists alongside root `README.md`, both get indexed under the same `name`, and the path that returns `bm_filtered[:top_k]` without rerank can emit both — surfaces as a duplicate `> README.md` line in the G2-DOCS output. The fix in PR #4 switches corpus build to a name-keyed dict with root extras winning on collision. Originally PR-2 was just the test suite; this audit finding got bundled in.

### 4. PR #5 ships 5 regression cases for determinism

The three `ranker.py` sort sites previously relied on CPython's stable-sort guarantee for equal-key ordering. PR #5 adds explicit tiebreak keys (matching the existing pattern at `code_search.py:233`) plus `tests/regression/test_pr3_deterministic_sort.py` covering: idempotency, equal-rank tiebreak independent of input order, equal-score tiebreak by hash, no-emb sanity, index tiebreak.

## Co-maintain — yes, happy to

I use CTX daily so the maintenance overhead is already paid on my end. Concretely I can take:

- Issue triage on weekday afternoons KST
- Hook reviews (BM25 / tokenizer / install machinery / golden fixtures)
- Release notes + version bumps in coordination with you

I'd defer to you on retrieval algorithm direction, paper alignment, and anything benchmark-facing — those are your design decisions and I'd like to keep upstream's voice intact. If a `MAINTAINERS.md` with explicit areas of ownership works for you, I can draft one as a follow-up after the boundary discussion settles.

## Order of operations I'd suggest

1. You take a look at the `_bm25/` boundary in PR #3 (or any of the three — same `_bm25/` layout) and let me know whether it's broadly OK or needs redrawing.
2. Once boundaries are agreed, I either land PR-4 (decomposition) first and the three Drafts become clean diffs, or I re-author each into the upstream monolith and close the Drafts.
3. Subtoken splitting stays out of all four PRs (separate cycle, as agreed earlier in this thread).

Let me know if the order or scope needs adjusting.
