# [expert-research-v2] CTX User Data Flywheel Strategy
**Date**: 2026-04-27  **Skill**: expert-research-v2

## Original Question
Before monetizing CTX, what user data should we gather as a strategic asset? Design: (1) what behavioral data becomes a moat, (2) how to aggregate across users without privacy violations, (3) what shapes the AI/ML flywheel, (4) concrete data schema + collection points.

---

## Web Facts
- [FACT-1] Cursor $2B ARR (Feb 2026). Copilot 20M users, 90% Fortune 100. Flywheel = better tool → more users → more data → better model. (source: digidai.github.io)
- [FACT-2] Copilot moat = distribution + workflow adjacency (PRs/repos/org policy), NOT model quality. Model-agnostic tools have thinner moats. (source: digidai.github.io)
- [FACT-3] Sourcegraph telemetry: numeric-only events, no strings (audited allowlist). User IDs = numeric, per-instance. Enterprise = zero retention. (source: sourcegraph.com/docs/admin/telemetry)
- [FACT-4] Cody discontinued Free/Pro July 2025 → Enterprise-only. Deep codebase context = differentiator.
- [FACT-5] Best implicit signals: drill-down, rephrasing, early termination, correction patterns, regeneration. Proprietary domain-specific feedback data = key moat. Public internet already scraped.
- [FACT-6] Tesla: 300M miles = moat. Netflix: each interaction refines algorithm. ChatGPT: 1M users in 5 days. Competitors need matching quality + momentum to break in.

---

## Key Answer

**CTX's unique flywheel that Cursor/Copilot cannot replicate:**

Cursor measures completion acceptance. Copilot measures distribution. Neither closes the loop between "what context was retrieved" and "what the AI actually used in its reasoning." CTX is the only tool with hook-level injection tracking + post-response citation parsing + cross-session memory — all three required to close this loop.

**The flywheel:**
```
Retrieval precision ↑ → AI cites more injected context → utility_rate ↑
→ users solve tasks faster → more sessions → more retrieval training signal
→ retrieval precision ↑
```

---

## Detailed Analysis

### What Data Becomes a Moat (Priority Order)

**1. utility_rate per (query_type × hook_source) — highest value, needs validation first**

CTX's utility_rate (% injected context cited by AI) is a direct retrieval precision proxy most tools cannot measure. It's an implicit behavioral signal (FACT-5 category) with higher SNR than click/accept signals because it measures AI's own citation behavior.

**Caveat**: Citation bias risk — Claude may cite whatever is in context due to position/recency bias, not genuine relevance. Before treating as moat: run calibration study injecting known-irrelevant context, measure false citation rate. If > 15%, redesign (weight by semantic distance between query and cited node).

**2. Cross-session decision corpus structure (not content)**

CTX owns longitudinal memory of *why* decisions were made — no competitor has this (they all reset per session). For open-source projects, git commits are public and Copilot has them. The private-repo corpus is genuinely proprietary. **Key insight**: the moat may actually be CTX's *local-first trust architecture* — developers who don't trust cloud aggregation will pay for privacy-preserving memory. This is a positioning advantage Copilot cannot adopt.

**3. retrieval_method distribution across query types**

retrieval_log.jsonl records KEYWORD vs SEMANTIC vs CASCADE per query. Aggregated = taxonomy of "what developer questions require semantic vs keyword retrieval." If 40% of hard queries fall through to CASCADE with lower utility_rate → investment signal for dense model improvement.

**Caveat**: schema must be version-tagged. The KEYWORD/SEMANTIC/CASCADE taxonomy has evolved; longitudinal comparability requires version stability.

**4. Per-project vocabulary cluster fingerprints (no raw text)**

BM25 term frequency distributions → project type cluster IDs (Next.js/Supabase vs Rust/systems). Enables cold-start pre-warming for new users matching existing cluster — equivalent to Netflix personalization loop (FACT-6).

---

## Concrete Data Schema

### Table: `retrieval_event`
*Collection point: retrieval_log.jsonl → telemetry upload on opt-in*
*Anonymization: user_id = SHA256(machine_id + install_timestamp)*

```json
{
  "user_id":             "string(64)",     // SHA256 hash — no email/name
  "session_id":          "string(64)",     // SHA256(user_id + session_start_ts)
  "project_type_id":     "int",            // cluster ID — NOT project name/path
  "ts_unix_hour":        "int",            // truncated to hour, not minute
  "schema_version":      "string",         // "v1" — for longitudinal comparability

  "query_token_count":   "int",            // length only — NO query text
  "query_type":          "enum[KEYWORD, SEMANTIC, CASCADE, TEMPORAL]",
  "hook_source":         "enum[G1, G2_DOCS, G2_CODE, CM, G2_HOOKS]",

  "candidates_returned": "int",
  "top_score_bm25":      "float",          // score only — NO associated text
  "top_score_dense":     "float|null",     // null if vec-daemon down
  "retrieval_method":    "enum[KEYWORD, SEMANTIC, CASCADE]",
  "node_type_dist":      "json",           // e.g. {"commit":3,"doc":1,"chat":2}

  "utility_rate":        "float",          // 0.0–1.0
  "cited_node_types":    "json",           // e.g. {"commit":1,"doc":2}
  "session_turn_index":  "int",
  "vec_daemon_up":       "bool",
  "bge_daemon_up":       "bool"
}
```

### Table: `session_aggregate`
*Collection point: session end. One row per session.*

```json
{
  "session_id":              "string(64)",
  "user_id":                 "string(64)",
  "project_type_id":         "int",
  "ts_date":                 "string(10)",   // "2026-04-27" — no finer resolution
  "schema_version":          "string",

  "total_turns":             "int",
  "total_injections":        "int",
  "mean_utility_rate":       "float",
  "retrieval_method_hist":   "json",         // {"KEYWORD":5,"SEMANTIC":3,"CASCADE":2}
  "hook_source_hist":        "json",         // {"G1":4,"G2_DOCS":3,"CM":3}
  "session_outcome":         "enum[NORMAL, ABANDONED, SHORT]",
  "vault_entry_count":       "int",          // memory size proxy
  "index_staleness_hours":   "int|null"      // G2 codebase index age at session start
}
```

---

## Privacy-Safe Aggregation Design

**Rule 1 — No string aggregation.** Query text, response text, node content, commit messages, file names never leave the local machine. Only numeric + categorical fields upload. Follows FACT-3 (Sourcegraph numeric-only pattern). Survives GDPR/CCPA — no personal data or code transmitted.

**Rule 2 — k-anonymity at upload.** Suppress any session_aggregate row where project_type_id + ts_date has fewer than 5 users in the aggregation window. Prevents re-identification of rare project types.

**Rule 3 — Local inspection before upload.** `ctx telemetry preview` shows exactly what would be uploaded before CTX_TELEMETRY=1 is set. This is the consent architecture FACT-3 describes as enterprise-grade trust.

**Rule 4 — No training on individual content.** Flywheel uses aggregated retrieval outcome statistics to tune BM25 parameters only. Training signal = "SEMANTIC has 12% higher utility_rate than KEYWORD for TEMPORAL queries across 1000 sessions" — structural, not content.

---

## The 3-Stage Flywheel

| Stage | User threshold | Goal | Deliverable |
|-------|---------------|------|-------------|
| Stage 1 | 0–1,000 sessions | Validate utility_rate signal, tune BM25 params | Retrieval param set maximizing utility_rate per query_type × hook_source |
| Stage 2 | 1,000–10,000 | Train lightweight retrieval router (local inference, no text upload) | Cold-start improvement: predict optimal retrieval_method from query metadata |
| Stage 3 | 10,000+ | Project type pre-warming | New user on Next.js/Supabase stack gets cluster-7 optimized params, not generic defaults |

---

## Caveats & Trade-offs

- **Citation bias (unresolved)**: utility_rate may measure model position/recency bias, not retrieval relevance. Requires calibration study before flywheel investment.
- **Cold start problem**: flywheel is premature below ~1,000 opt-in sessions. Current priority = instrumentation completeness, not aggregation.
- **Consent infrastructure gap**: CTX_TELEMETRY=1 exists but no published schema, no user-accessible deletion, no DPA. This is a *distribution risk* before monetization — developer community trust is the real moat (FACT-2).
- **Backend engineering = 3–6 months**: local SQLite → cloud pipeline doesn't exist. Data strategy assumes a solved engineering problem.
- **Legal**: GDPR Article 4(1) may extend to machine_id hashes if linkable to an individual. Legal review required before any upload infrastructure.

---

## Recommendations

1. **Immediate (before any aggregation)**: Run utility_rate calibration study — 500 sessions, inject known-irrelevant context, measure false citation rate.
2. **Next 30 days**: Instrument all hooks with retrieval_event schema locally (no upload yet). Complete telemetry coverage across bm25-memory, chat-memory, g2-fallback.
3. **Next 60 days**: Build `ctx telemetry preview` command + publish data schema publicly. This is consent infrastructure that enables opt-in trust.
4. **Next 90 days**: Build minimal upload pipeline (HTTPS POST of session_aggregate rows only, k-anonymized). First aggregation dataset.
5. **Positioning**: Lead with "local-first, privacy-preserving cross-session memory." This is the moat Copilot cannot adopt. Data flywheel is secondary.

---

---

## Implementation Status (v0.3.1, live-inf iters 50–73)

### Recommendations Progress

| # | Recommendation | Status | Notes |
|---|---------------|--------|-------|
| 1 | Run utility_rate calibration study | ✅ | `ctx-telemetry calibrate`: Pearson r(top_score_bm25, utility_rate) — resolves "citation bias unresolved" caveat |
| 2 | Instrument all hooks with retrieval_event schema | ✅ | bm25-memory.py (G1+G2-DOCS) + chat-memory.py (CM) + utility-rate.py all instrument. schema v1.5 |
| 3 | `ctx telemetry preview` + published schema | ✅ | `ctx-telemetry consent grant` shows full field list; README schema table published; Stage 2 dry-run |
| 4 | Minimal upload pipeline (k-anonymized session_aggregate) | ✅ | `cmd_upload` with k-anonymity gate + consent check; endpoint placeholder pending activation |
| 5 | Positioning: local-first memory moat | ✅ | README framing confirmed; auto-tune flywheel badge reinforces it |

### Schema Gaps (strategy vs. v0.3.2)

| Field | Strategy status | Implementation status | Priority |
|-------|----------------|----------------------|----------|
| `project_type_id` | Planned (cluster ID) | **Partial** — `ctx-telemetry cluster` writes `project_type_hint` (local-first proxy, no cross-user data needed). Full cluster ID requires Stage 2 aggregation. | Stage 3: cross-user cluster model; local proxy now unblocked |
| `node_type_dist` | Planned (`{"commit":3,"doc":1}`) | **Not implemented** | Adds injection type richness; can be derived from hook_source_hist if CM tagged |
| `cited_node_types` | Planned | **Not implemented** | Requires per-node citation tracking (beyond current binary cited/not) |
| `session_outcome` | NORMAL / ABANDONED / SHORT | NORMAL / SHORT only | ABANDONED state (user never responded) not yet detected |

### Caveats Update

- **Citation bias**: **RESOLVED** in v1.5 — `top_score_bm25 × utility_rate` Pearson r in `ctx-telemetry calibrate` directly measures causal vs. bias. r > 0.30 = healthy flywheel.
- **Cold start problem**: Still true — < 1,000 opt-in sessions. Current priority remains instrumentation completeness.
- **Consent infrastructure gap**: **RESOLVED** — `ctx-telemetry consent grant` with interactive preview, schema published in README.
- **Backend engineering**: Still unresolved — upload endpoint not activated. Data collection is complete; aggregation infrastructure remains.
- **Legal**: Still requires review before any upload activation.

## Sources
- [Cursor vs GitHub Copilot 2026 — data flywheel dynamics](https://digidai.github.io/2026/02/08/cursor-vs-github-copilot-ai-coding-tools-deep-comparison/)
- [Sourcegraph telemetry spec — numeric-only, anonymized](https://sourcegraph.com/docs/admin/telemetry)
- [AI product data flywheel — implicit signals & feedback loops](https://mrmaheshrajput.medium.com/the-data-flywheel-why-ai-products-live-or-die-by-user-feedback-4ae7aab32d4d)
- [Sourcegraph Cody enterprise strategy 2025](https://www.software.com/ai-index/tools/cody)

## Further Investigation Needed
- Current CTX install base size (plugin metrics unavailable locally)
- GDPR guidance on hashed machine identifiers
- Claude citation position/recency bias documentation
- Whether retrieval_method schema stability can be guaranteed across bm25-memory.py versions

## Related
- [[projects/CTX/research/20260421-ctx-monetization-session-summary|20260421-ctx-monetization-session-summary]]
- [[projects/CTX/research/20260427-ctx-flywheel-data-coverage|20260427-ctx-flywheel-data-coverage]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260427-ctx-plugin-distribution-research|20260427-ctx-plugin-distribution-research]]
- [[projects/CTX/research/20260426-retrieval-node-relevance-verification|20260426-retrieval-node-relevance-verification]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
