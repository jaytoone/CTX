# MemoryAgentBench Failure Analysis — Recency + Tokenization Gap

**Date**: 2026-04-24
**Scope**: CTX conflict-resolution benchmark (MAB Competency 4)
**Status**: Empirical finding from live-inf iter 7–8

## Setup

10-session synthetic haystack per test case. Initial fact in session 0;
reversal in session N-1 (last). Query asks about current state.
Expected: LLM answers with reversal-era content.

## Finding

MAB accuracy N=5:
- `none`: 0.0 (baseline)
- `ctx`: 0.2 (1/5 correct)

## Two distinct failure modes

### 1. Tokenization gap — the dominant failure (4/5 cases)

On Query "Where do logs go now?":
- Initial session: "Logs stream to stdout only." → BM25=1.68
- Reversal session: "Added structured JSONL logging to .omc/live-progress.log alongside stdout." → BM25=0.00

The reversal session scores **zero** on BM25 because the query uses "logs"
but the reversal uses "logging" + "stdout" — different surface tokens.
No amount of recency boost (1.0x to 5.6x tested) can rescue a zero score.

BGE cross-encoder CAN rerank candidates, but only candidates BM25 returned.
Since the reversal never enters the candidate pool, BGE doesn't see it.

### 2. First-fact-wins — the architectural failure the benchmark tests (1/5 cases)

On case 3 (frontend framework):
- CTX retrieved 2 memories (both about the framework)
- LLM answered "vanilla JavaScript" — CORRECT

But on case 4 (log sink):
- CTX retrieved 1 memory
- Memory was the INITIAL session, LLM answered "stdout only" — WRONG

This is claude-mem's predicted failure extended to CTX: even when retrieval
surfaces relevant content, the LLM follows the FIRST mention.

## Remediation paths

| Fix                                  | Effort | Expected lift     |
|--------------------------------------|--------|-------------------|
| Add Porter stemming to BM25 tokenize | 30 min | 2–3 / 5 (out of 5) |
| Dense candidate generation (vec-daemon) | 2 h   | 3–4 / 5          |
| Recency-ordered injection block       | 15 min | +0.5 / 5 (tie-breaker after stemming) |
| LLM system prompt: "most recent wins" | 5 min  | +1 / 5 (complementary) |

**Priority ordering**: stemming first (fundamental), then dense-candidate,
then recency ordering of injection, then system-prompt hint.

## Implication for paper §6

This is the KEY architectural claim MERIDIAN §6 makes: BM25-only systems
(CTX baseline) WILL fail conflict-resolution when reversal vocabulary
differs from initial. Adding semantic retrieval (bge-daemon) is necessary
but NOT SUFFICIENT for candidate-generation failures — only rescuing
ranking issues, not missing-candidate issues.

claude-mem's dense-retrieval is predicted to handle tokenization gaps
BETTER than CTX (because embeddings bridge "logs" ↔ "logging"), but
LOSE MORE on the first-fact-wins mode (because LLM summary averages pre-
and post-reversal state into a single observation).

Next step: run real LongMemEval where these failure modes appear in natural
language and measure the two failure rates independently.

## Files

- `benchmarks/eval/tier1_memoryagentbench.py` — the harness
- `benchmarks/eval/recency_rerank.py` — experimental recency booster (not wired)
- `benchmarks/results/tier1_memoryagentbench.json` — N=5 data
