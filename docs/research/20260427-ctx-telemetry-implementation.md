# CTX Telemetry Stage 1 Implementation
**Date**: 2026-04-27  **live-inf iters 50–72**  **Released: v0.3.1**

## What Was Built

Stage 1 of the data flywheel (per [20260427-ctx-user-data-flywheel-strategy.md](20260427-ctx-user-data-flywheel-strategy.md)):
local structured logging of `retrieval_event` and `session_aggregate` records — numeric + categorical only, no content.

Schema evolution: v1 (iters 50-53) → v1.1 (iter 54: query_type) → v1.2 (iter 55: session_turn_index + calibrate) → v1.3 (iter 56: user_id) → v1.4 (iters 57-58: vault_entry_count, index_staleness_hours, consent command) → v1.5 (iters 64-68: top_score_bm25/dense, G2-DOCS capture, session_aggregate mean_top_score_bm25 + query_type_hist)

---

## retrieval_event Schema (schema_version: "v1.5")

Written by `utility-rate.py` (Stop hook) to `~/.claude/ctx-retrieval-events.jsonl`.
One record per active hook block per session turn.

| Field | Type | Source | Added |
|-------|------|--------|-------|
| `schema_version` | `"v1.5"` | constant | v1 |
| `user_id` | str(16) | SHA256(machine_id + install_month)[:16] | v1.3 |
| `ts_unix_hour` | int | `int(time.time() / 3600)` | v1 |
| `session_id_hash` | str(16) | SHA256(session_id)[:16] | v1 |
| `hook_source` | enum[G1, G2_DOCS, G2_CODE, CM] | block name | v1 |
| `query_type` | enum[KEYWORD, SEMANTIC, TEMPORAL, UNKNOWN] | `_classify_query_type(prompt)` | v1.1 |
| `query_char_count` | int | `prompt_len` from injection | v1 |
| `candidates_returned` | int\|null | from `last-retrieval-meta.json` | v1 |
| `retrieval_method` | enum[HYBRID, BM25, UNKNOWN] | from `last-retrieval-meta.json` | v1 |
| `duration_ms` | int\|null | per-block retrieval time | v1 |
| `total_injected` | int | items in this block | v1 |
| `total_cited` | int | items referenced by AI | v1 |
| `utility_rate` | float | cited / injected | v1 |
| `session_turn_index` | int | turn count from ctx-session-state.json | v1.2 |
| `vec_daemon_up` | bool | socket existence check | v1 |
| `bge_daemon_up` | bool | socket existence check | v1 |
| `top_score_bm25` | float\|null | max BM25 score from `bm25_rank_decisions()` | v1.5 |
| `top_score_dense` | float\|null | max cosine score from `dense_rank_decisions()` | v1.5 |

**v1.5 causal signal**: `top_score_bm25` × `utility_rate` Pearson r identifies whether retrieval quality causally predicts citations (r>0.30 = healthy flywheel) vs. position/recency bias (r<0.10 = citation regardless of quality). Run `ctx-telemetry calibrate` once ≥10 v1.5 records accumulate.

## session_aggregate Schema (schema_version: "v1.5")

Written to `~/.claude/ctx-session-aggregates.jsonl` when session_id changes.
One record per completed session.

| Field | Type | Notes | Added |
|-------|------|-------|-------|
| `schema_version` | str | "v1.5" | v1 |
| `user_id` | str(16) | SHA256(machine_id + install_month)[:16] | v1.3 |
| `session_id_hash` | str(16) | SHA256 of previous session_id | v1 |
| `ts_date` | str | "YYYY-MM-DD" | v1 |
| `total_turns` | int | — | v1 |
| `total_injections` | int | across all blocks | v1 |
| `mean_utility_rate` | float | avg across turns | v1 |
| `hook_source_hist` | json | `{"G1": 4, "G2_DOCS": 3}` | v1 |
| `retrieval_method_hist` | json | `{"HYBRID": 7}` | v1 |
| `session_outcome` | enum | NORMAL (>2 turns) / SHORT | v1 |
| `vault_entry_count` | int\|null | chat vault.db row count at flush | v1.4 |
| `index_staleness_hours` | int\|null | code-graph.db age in hours | v1.4 |
| `mean_top_score_bm25` | float\|null | session avg of BM25 quality scores | v1.5 iter 68 |
| `query_type_hist` | json\|null | `{"KEYWORD":5,"SEMANTIC":3}` turn counts | v1.5 iter 68 |

**v1.5 session causal signal**: `mean_top_score_bm25` × `mean_utility_rate` Pearson r (cross-session view, n≥5 sessions) cross-validates per-turn causal r. Available via `ctx-telemetry tune` and `ctx-telemetry calibrate`.

## Retrieval Metadata Pipeline

```
bm25-memory.py (UserPromptSubmit)
  → writes ~/.claude/last-retrieval-meta.json
    { blocks: { g1_decisions: { candidates, returned, retrieval_method, duration_ms }, ... },
      vec_daemon_up, bge_daemon_up, query_char_count, session_id }

utility-rate.py (Stop)
  → reads last-retrieval-meta.json
  → writes one retrieval_event per block → ctx-retrieval-events.jsonl
  → accumulates session state → ctx-session-aggregates.jsonl (on session flush)
```

## ctx-telemetry CLI (v1.5)

```bash
ctx-telemetry                   # summary: avg utility% per block + flywheel health verdict
ctx-telemetry last [-n N]       # last N events (default 10)
ctx-telemetry calibrate         # citation bias + causal r analysis (v1.5)
ctx-telemetry tune              # compute auto-tune params → ctx-auto-tune.json
ctx-telemetry consent           # Stage 2 consent status
ctx-telemetry consent grant     # opt-in to k-anonymized upload (interactive preview)
ctx-telemetry consent revoke    # revoke consent
ctx-telemetry upload [--send]   # Stage 2 dry-run preview (--send when endpoint active)
ctx-telemetry clear             # delete all local telemetry logs
```

Sample output (v0.3.0):
```
CTX Retrieval Telemetry — 42 session-turn records (schema v1.5)
Log: /home/user/.claude/ctx-retrieval-events.jsonl
Semantic layer: vec-daemon up 40/42 | bge-daemon up 38/42

Block          Turns  Avg Util%     Cited   Injected
G1                28      52.0%        73        140
G2_DOCS           14      38.5%        27         70

Retrieval method distribution:
  HYBRID          42  (100.0%)

Query type × utility_rate (moat metric):
  QueryType        Turns  Avg Util%
  --------------------------------
  KEYWORD             18      58.1%
  SEMANTIC            15      48.0%
  TEMPORAL             9      38.7%

Session aggregates: 8 sessions | avg turns=5.3 | avg utility=47.2%

Flywheel health [n=42]: causal-r=+0.35 | upgrade=✓ HYBRID | session-r=+0.28 | kw=43%
  Run `ctx-telemetry tune` to refresh | `ctx-telemetry calibrate` for full analysis
```

## Privacy Contract

- ❌ No query text, response text, commit messages, file names, code content
- ✅ Numeric + categorical only (counts, rates, method names, duration)
- ✅ SHA256 session hashes (non-reversible, no email/device info)
- ✅ Date truncated to hour (ts_unix_hour), not minute
- ✅ Local-only (`~/.claude/`); no network; no upload in Stage 1

## Stage 2 (not yet implemented)

Opt-in upload pipeline: HTTPS POST of k-anonymized `session_aggregate` rows.
k-anonymity gate: suppress rows where `ts_date` has <5 users in aggregation window.
Requires: `ctx telemetry consent` command + DPA/GDPR review.

- [20260427-ctx-user-data-flywheel-strategy.md](20260427-ctx-user-data-flywheel-strategy.md) — full flywheel design
- [20260426-citation-probe-v1.md](20260426-citation-probe-v1.md) — citation probe (feeds `utility_rate` signal)

## Related
- [[projects/CTX/research/20260427-ctx-user-data-flywheel-strategy|20260427-ctx-user-data-flywheel-strategy]]
- [[projects/CTX/research/20260426-citation-probe-v1|20260426-citation-probe-v1]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260417-ctx-semantic-search-upgrade-sota|20260417-ctx-semantic-search-upgrade-sota]]
- [[projects/CTX/research/20260412-semantic-gap-keyword-vs-contextual|20260412-semantic-gap-keyword-vs-contextual]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
