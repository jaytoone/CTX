# Empirical measurement: CTX with Context Mode in Korean dev env (5 scenarios × 4 states)

Hi jaytoone,

Following up on https://github.com/jaytoone/CTX/issues/1, I ran an empirical evaluation of CTX (this fork: `hang-in/tunaCtx`) alongside `mksglu/context-mode` plugin in a real Korean development environment. Sharing the data because the patterns surfaced in Korean prompts may be useful for upstream.

## Setup

- **Model**: claude-opus-4-7
- **Invocation**: `claude -p --output-format=stream-json --no-session-persistence` (headless)
- **States**: A=both active, B=CM only, C=CTX only, D=baseline
- **Repos**: seCall, tunaFlow, tunaCtx (mixed Korean comments / English code)
- **CTX layers active**: BM25 + vec-daemon (`multilingual-e5-small`) + bge-daemon (`bge-reranker-v2-m3`)
- **Total cost**: $8.01 across 20 measurements

## Key findings relevant to upstream

### CTX never finishes worse than 2nd place across 5 scenarios

| Scenario | CTX rank vs no-CTX | Note |
|---|---|---|
| Code-search (Korean prompt → seCall) | A=1st, C=3rd | CTX+CM synergy beats baseline |
| 30-commit analysis | C=2nd | Context Mode added cost without value here |
| Korean docstring search ("Roundtable" / "RT") | A=1st, C=4th (timeout) | CTX surfaced Rust files via G2-DOCS |
| Commit evolution analysis | **C=1st** | CTX-only beat all combos including CTX+CM |
| Production refactor TODO grep | C=2nd | CTX+CM crashed (sandbox permission) |

### Korean prompt token shape

CTX's tokenizer (`_bm25/tokenizer.tokenize`) handles Korean particles + Porter stemmer. Cumulative input/output tokens per scenario:

| Scenario | input | output | cache_read |
|---|---:|---:|---:|
| Korean docstring search (CTX+CM) | 32 | 8591 | 257K |
| Korean docstring search (CTX only, timeout) | 1* | 44* | 47K |
| Korean docstring search (baseline) | 10 | 7303 | 177K |

The CTX-only / Korean-search scenario hit a 180s timeout while doing 27× Grep. This suggests CTX's G2-GREP fallback is too aggressive when the BM25/dense layers don't surface a clear top-N — Korean tokenization may be producing too many candidate keywords.

### G2-GREP determinism (relevant to your codebase)

We added `(-count, path)` tie-break to `_bm25/code_search.py:233` (was: `count` only) to fix golden fixture flakiness. Sort is now deterministic. Upstream may want to consider the same — `tests/golden/run_golden.py` cascade was the symptom but the root cause is fragile sort.

### Fork-specific changes that might be useful upstream (no PR pressure)

- `_bm25/` package decomposition (1837 LOC orchestrator → 300 LOC + 11 sub-modules) — same retrieval algorithm, just decomposed for testability
- 105 unit tests covering hooks/install/cache/telemetry
- Hash-based hook update in `ctx-install` (handles users who modified their hook files)
- `sqlite_vec` graceful fallback in `chat-memory.py`
- `score_corpus_bm25()` as the single canonical BM25 entrypoint shared across hook + benchmark eval scripts

All in `master` of `hang-in/tunaCtx`. Happy to extract any of these as small PRs if you'd like — pick whatever's useful, ignore the rest.

## What's measured / what's not

- Measured: token usage, latency, cost, tool call counts, response text
- Judge: Gemini 1× per scenario (not multiple raters; LLM-as-judge has known biases)
- Sample size: 1 prompt × 4 states per scenario (no variance estimate)
- Not measured: interactive vs headless behavior delta (sandbox permission patterns may differ)

Full report: `docs/refactor/EVAL_RESULTS.md` in `hang-in/tunaCtx`.

If any of this is useful for the next CTX release or paper, happy to share raw data and re-run with adjusted prompts.
