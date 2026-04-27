# CTX Telemetry Stage 1 Implementation
**Date**: 2026-04-27  **live-inf iters 50–51**

## What Was Built

Stage 1 of the data flywheel (per [20260427-ctx-user-data-flywheel-strategy.md](20260427-ctx-user-data-flywheel-strategy.md)):
local structured logging of `retrieval_event` and `session_aggregate` records — numeric + categorical only, no content.

---

## retrieval_event Schema (schema_version: "v1")

Written by `utility-rate.py` (Stop hook) to `~/.claude/ctx-retrieval-events.jsonl`.
One record per active hook block per session turn.

| Field | Type | Source |
|-------|------|--------|
| `schema_version` | `"v1"` | constant |
| `ts_unix_hour` | int | `int(time.time() / 3600)` |
| `session_id_hash` | str(16) | SHA256(session_id)[:16] |
| `hook_source` | enum[G1, G2_DOCS, G2_CODE, CM] | block name |
| `query_char_count` | int | `prompt_len` from injection |
| `candidates_returned` | int\|null | from `last-retrieval-meta.json` |
| `retrieval_method` | enum[HYBRID, BM25, UNKNOWN] | from `last-retrieval-meta.json` |
| `duration_ms` | int\|null | per-block retrieval time |
| `total_injected` | int | items in this block |
| `total_cited` | int | items referenced by AI |
| `utility_rate` | float | cited / injected |
| `vec_daemon_up` | bool | socket existence check |
| `bge_daemon_up` | bool | socket existence check |

## session_aggregate Schema (schema_version: "v1")

Written to `~/.claude/ctx-session-aggregates.jsonl` when session_id changes.
One record per completed session.

| Field | Type | Notes |
|-------|------|-------|
| `session_id_hash` | str(16) | SHA256 of previous session_id |
| `ts_date` | str | "YYYY-MM-DD" |
| `total_turns` | int | — |
| `total_injections` | int | across all blocks |
| `mean_utility_rate` | float | avg across turns |
| `hook_source_hist` | json | `{"G1": 4, "G2_DOCS": 3}` |
| `retrieval_method_hist` | json | `{"HYBRID": 7}` |
| `session_outcome` | enum | NORMAL (>2 turns) / SHORT |

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

## ctx-telemetry Preview CLI

```bash
ctx-telemetry          # summary: avg utility% per block, method distribution
ctx-telemetry --last   # last 10 events
ctx-telemetry --clear  # delete log
```

Sample output:
```
CTX Retrieval Telemetry — 12 session-turn records
Block           Turns  Avg Util%  Total Cited  Total Injected
G1                  8      48.0%           19              40
G2_DOCS             4      33.3%            4              12
Retrieval method distribution:
  HYBRID          12  (100.0%)
Session aggregates: 3 sessions | avg turns=4.0 | avg utility=42.5%
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

## Related

- [20260427-ctx-user-data-flywheel-strategy.md](20260427-ctx-user-data-flywheel-strategy.md) — full flywheel design
- [20260426-citation-probe-v1.md](20260426-citation-probe-v1.md) — citation probe (feeds `utility_rate` signal)
