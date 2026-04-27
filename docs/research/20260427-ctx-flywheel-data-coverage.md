# CTX Data Flywheel — Field Coverage Map (v1.5)
**Date**: 2026-04-27  **live-inf iter 67–74**

Maps every schema v1.5 field to its flywheel role and current collection status.

---

## Flywheel Roles (4 axes)

| Axis | Question answered | Acts on |
|------|------------------|---------|
| **Quality Signal** | Is this retrieval actually useful? | utility_rate, total_cited |
| **Causal Signal** | Does retrieval quality cause citations? | top_score_bm25/dense × utility_rate |
| **Context Signal** | What environment affects quality? | vec_daemon_up, bge_daemon_up, query_type |
| **Population Signal** | Who uses CTX and how? | user_id, session aggregates |

---

## retrieval_event Coverage (per-turn, v1.5)

| Field | Flywheel Axis | Role | Collection Status |
|-------|--------------|------|-------------------|
| `schema_version` | — | versioning | ✅ every record |
| `user_id` | Population | de-identified per-user aggregation | ✅ v1.3+ |
| `ts_unix_hour` | Population | temporal trends (hourly bucket) | ✅ v1 |
| `session_id_hash` | Population | session dedup | ✅ v1 |
| `hook_source` | Context | block type (G1/G2_DOCS/CM) | ✅ v1 |
| `query_type` | Context | KEYWORD vs SEMANTIC vs TEMPORAL | ✅ v1.1+ |
| `query_char_count` | Context | query complexity proxy | ✅ v1 |
| `candidates_returned` | Quality | retrieval coverage | ✅ v1 |
| `retrieval_method` | Context | HYBRID vs BM25 path | ✅ v1 |
| `duration_ms` | Context | latency monitoring | ✅ v1 |
| `total_injected` | Quality | injection volume | ✅ v1 |
| `total_cited` | Quality | citations observed | ✅ v1 |
| `utility_rate` | Quality | cited/injected — primary flywheel metric | ✅ v1 |
| `session_turn_index` | Context | position bias control | ✅ v1.2+ |
| `vec_daemon_up` | Context | semantic layer availability | ✅ v1 |
| `bge_daemon_up` | Context | reranker availability | ✅ v1 |
| `top_score_bm25` | **Causal** | max BM25 score → causal r analysis | ✅ v1.5 (G1+G2_DOCS) |
| `top_score_dense` | **Causal** | max cosine score → causal r analysis | ✅ v1.5 (when vec-daemon up) |
| `node_type_dist` | Population | injected node type per block (`{"commit":5}`) | ✅ v1.6 |

**Coverage gaps:**
- `top_score_bm25` is null for CM (chat-memory) block — chat-memory.py uses SQLite FTS5, not BM25Okapi
- `top_score_dense` is null when vec-daemon is down (~10% of turns based on daemon health logs)
- G2-CODE block (graph search) has no top_score — graph scoring is structural not similarity-based

---

## session_aggregate Coverage (per-session, v1.5)

| Field | Flywheel Axis | Role | Collection Status |
|-------|--------------|------|-------------------|
| `schema_version` | — | versioning | ✅ v1 |
| `user_id` | Population | cross-session user identity | ✅ v1.3+ |
| `session_id_hash` | Population | session dedup | ✅ v1 |
| `ts_date` | Population | date-level temporal trends | ✅ v1 |
| `total_turns` | Quality | session depth | ✅ v1 |
| `total_injections` | Quality | total context injected | ✅ v1 |
| `mean_utility_rate` | Quality | session-level retrieval precision | ✅ v1 |
| `hook_source_hist` | Context | block mix per session | ✅ v1 |
| `retrieval_method_hist` | Context | HYBRID vs BM25 distribution | ✅ v1 |
| `session_outcome` | Population | NORMAL/SHORT session classification | ✅ v1 |
| `vault_entry_count` | Context | chat memory corpus size | ✅ v1.4+ |
| `index_staleness_hours` | Context | code-graph freshness | ✅ v1.4+ |
| `mean_top_score_bm25` | **Causal** | session-avg BM25 quality score | ✅ v1.5 iter 68 |
| `query_type_hist` | Context | KEYWORD/SEMANTIC/TEMPORAL turn counts | ✅ v1.5 iter 68 |
| `node_type_hist` | Population | commit/doc/chat/code total nodes across session | ✅ v1.6 iter 76 |

**Additions in iter 68:**
- `mean_top_score_bm25` — session average of BM25 quality scores → session-level causal analysis ✅ added
- `query_type_hist` — KEYWORD/SEMANTIC/TEMPORAL turn counts per session ✅ added

---

## Auto-Tune Output (ctx-auto-tune.json, v1)

| Field | Flywheel Axis | Role | Computed From |
|-------|--------------|------|---------------|
| `prefer_hybrid_G1` | Quality | HYBRID vs BM25 preference for G1 | HYBRID/BM25 utility delta |
| `prefer_hybrid_G2_DOCS` | Quality | HYBRID vs BM25 preference for G2-DOCS | HYBRID/BM25 utility delta |
| `temporal_utility_gap` | Context | TEMPORAL vs KEYWORD utility gap | query_type utility rates |
| `temporal_boost_hint` | Context | increase/maintain/decrease temporal weighting | temporal_utility_gap magnitude |
| `causal_r_bm25_utility` | **Causal** | Pearson r: BM25 score → citation rate | v1.5 top_score_bm25 × utility_rate |
| `hybrid_upgrade_hint` | **Causal** | likely_worthwhile / validate_first / needs_more_data | causal_r threshold |
| `project_type_hint` | Population | tech stack cluster proxy (python_ml / nextjs_react / …) | `ctx-telemetry cluster` vocab scan |
| `project_type_confidence` | Population | HIGH / MEDIUM / LOW signal clarity | winner vs runner-up frequency gap |
| `project_type_top_scores` | Population | top-3 profile fractional scores | profile keyword frequency distribution |
| `based_on_n` | — | record count at tune time | count(retrieval_events) |
| `computed_at` | — | ISO8601 timestamp | time.time() |

---

## Flywheel Loop Status

```
Data Collection (v1.5)
  ↓ utility_rate [per turn]
  ↓ top_score_bm25/dense [per turn, v1.5]

ctx-telemetry tune
  ↓ prefer_hybrid_{G1,G2_DOCS} [HYBRID worth it?]
  ↓ causal_r_bm25_utility [is quality causing citations?]
  ↓ hybrid_upgrade_hint [binary decision]
  ↓ temporal_utility_gap [query-type tuning needed?]
  → writes ctx-auto-tune.json

bm25-memory.py startup
  ↓ reads ctx-auto-tune.json
  ↓ adjusts top_k per query_type
  ↓ shows badge: > **CTX auto-tune** [n=42, hybrid✓, temporal-gap=15pp]

ctx-telemetry calibrate
  ↓ Pearson r(top_score_bm25, utility_rate)
  → PASS/MARGINAL/WARN verdict on signal quality
  → position bias detection

ctx-telemetry cluster [-p DIR]
  ↓ scans source files → BM25 term frequency against tech-stack signatures
  ↓ project_type_hint [python_ml / python_backend / nextjs_react / rust_systems / go_backend]
  ↓ project_type_confidence [HIGH / MEDIUM / LOW]
  → writes project_type_hint + top_scores to ctx-auto-tune.json

bm25-memory.py startup (also reads project_type_hint)
  ↓ python_ml → g1_top_k = 8 (longer ML decision history)
  ↓ nextjs_react → g1_top_k = 6, g2d_top_k = 6 (keyword-specific, more framework docs)
  ↓ rust_systems → g2d_top_k = 4 (precise doc matching)
  ↓ shows badge: > **CTX auto-tune** [n=42, hybrid✓, python_ml]
  → Stage 3 local loop CLOSED: cluster → apply → retrieve → collect → re-tune

Stage 2 (planned)
  ↓ k-anonymized session_aggregate → telemetry endpoint
  ↓ cross-user aggregation → global retrieval quality signal
  → shared auto-tune weights for new installs (cold-start fix)

Stage 3 (future)
  ↓ project_type_id cluster model (trained on 10k+ sessions)
  ↓ new user's project_type_hint → cluster → pre-warmed BM25 params
  → cold-start improvement: skip the first 50 sessions of sub-optimal retrieval
```

**Loop completeness**: Stage 1 local loop is **fully closed** (collect → tune → apply → collect).
Stage 2 cross-user loop is **structurally ready** (upload pipeline + k-anonymity + consent) but endpoint is not yet active.
Stage 3 cluster cold-start is **locally closed**: `ctx-telemetry cluster` writes profile hint → `bm25-memory.py` reads it and adjusts `top_k` per project type + shows hint in auto-tune badge. Full cross-user cluster model requires Stage 2 aggregate, but local adaptation works now.

---

## What Each Tool Release Enabled

| Version | New Flywheel Capability |
|---------|------------------------|
| v0.2.2 | First `ctx-telemetry` CLI: summary + last + clear |
| v0.2.3 | query_type × utility cross-tab; calibrate; tune (Stage 1 loop closes) |
| v0.2.4 | user_id; vault_entry_count + index_staleness; consent + upload |
| v0.2.5 | top_score_bm25/dense G1 causal signal; calibrate r-analysis |
| v0.2.6 | G2-DOCS top_score capture; cmd_tune hybrid_upgrade_hint |
| v0.2.7 | Schema version alignment; README hybrid_upgrade_hint docs |
| v0.2.8 | session_aggregate: mean_top_score_bm25 + query_type_hist (session-level causal) |
| v0.3.1 | Full Stage 1 implementation: all 5 flywheel recommendations completed |
| v0.3.2 | ctx-telemetry cluster: local project type fingerprint (Stage 3 prerequisite) |
| v0.3.3 | bm25-memory profile-aware top_k + badge: Stage 3 local loop closes |

---
- [20260427-ctx-user-data-flywheel-strategy.md](20260427-ctx-user-data-flywheel-strategy.md) — full strategy
- [20260427-ctx-telemetry-implementation.md](20260427-ctx-telemetry-implementation.md) — implementation log

## Related
- [[projects/CTX/research/20260427-ctx-user-data-flywheel-strategy|20260427-ctx-user-data-flywheel-strategy]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|20260426-g1-hybrid-rrf-dense-retrieval]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260407-g1-temporal-evaluation-framework|20260407-g1-temporal-evaluation-framework]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
- [[projects/CTX/research/20260411-chat-memory-threshold-principled|20260411-chat-memory-threshold-principled]]
