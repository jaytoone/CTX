# CTX North Star

**Vision**: CTX becomes the data moat layer for AI coding tools — the only system that closes the loop between context injection and AI citation behavior, across sessions and across users.

**North Star Metric (NS1)**: Cross-user `utility_rate` improvement delta (measured: how much does CTX get better per 100 sessions of opt-in data?)

**North Star Metric (NS2 — active)**: `distinct_external_users` in Turso `ctx_session_aggregates` > 0
- Gate: at least 1 real user (not developer) has opted in and uploaded data
- Current: 0 external users (1054 rows = developer self-data only)
- Fast-check: `SELECT COUNT(DISTINCT user_id) FROM ctx_session_aggregates WHERE user_id NOT LIKE 'test_%'`
- **This is the primary goal until the first external upload is confirmed**

---

## Current State (2026-05-09 — updated)

- v0.3.19 on PyPI ✅ — schema v1.7: project_type_id + ctx_version + utility_by_qtype
- Auto-upload on session end (opt-out model) — zero friction for users
- Turso: 1058 rows, 1 distinct user (self), ctx_version='0.3.18' appearing ✅
- NS2 gate: PENDING — awaiting first external user upload
- M1 ✅ M2 ✅ M5-GN ✅ | M4 waiting (2026-05-16) | M5-HN karma=1 (gate)
- GN post: 1pt, 5 comments (updated today with v0.3.16+v0.3.19 info)

---

## Milestones

### M1 — Activate flywheel upload [IMMEDIATE]
**Goal**: First real cross-user data flowing into Turso
**Acceptance**: `ctx-telemetry upload --send` succeeds, row count > 0 in Turso
**Actions**:
1. `ctx-telemetry consent grant` (interactive — user runs)
2. `ctx-telemetry upload --send`
3. Verify row count: query Turso `SELECT COUNT(*) FROM ctx_session_aggregates`
**Blocked by**: None (pipeline live)

### M2 — Opt-in funnel at install [THIS WEEK]
**Goal**: Every new CTX install sees the consent ask
**Acceptance**: `ctx-install` output includes opt-in prompt + link to schema docs
**Actions**:
1. Add `ctx-telemetry consent` call at end of `src/cli/install.py`
2. Add 3-line consent summary to README "Telemetry" section
3. Bump to v0.3.16 + publish to PyPI (commit + GitHub Release)
**Blocked by**: M1

### M3 — Cross-user signal validation [n=50 sessions]
**Goal**: Verify `utility_rate` variance across users is real signal, not noise
**Acceptance**: Pearson r(top_score_bm25, utility_rate) > 0.20 on cross-user data
**Actions**:
1. Query Turso for cross-user sessions
2. Run `ctx-telemetry calibrate` on aggregated data
3. Document causal r result in `docs/research/`
**Blocked by**: M2 (need real cross-user data)

### M4 — awesome-claude-code listing [2026-05-16]
**Goal**: CTX listed in awesome-claude-code (43k stars audience)
**Acceptance**: Issue submitted via web form, auto-validation passes
**Actions**:
1. Navigate to `https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml`
2. Submit via web form (NOT API — 7-day cooldown from API submission on 2026-05-09)
**Blocked by**: Cooldown expires 2026-05-16
**Note**: Previous API submission rejected (#1773 closed) — MUST use web form

### M5 — HN + GeekNews posts [PARTIALLY DONE]
**Goal**: Show HN post live, GeekNews post live
**Acceptance**: Both posts indexed, >5 points each
**Actions**:
1. HN: jaytoone karma=1, needs 1 upvote to unlock link posting — comment on active Claude Code thread first
2. GeekNews: sign up at news.hada.io (ID/password), post under "Show"
**Blocked by**: HN karma gate

### M6 — Pro tier launch [n=200 cross-user sessions]
**Goal**: First paid tier: $8/mo "CTX learns from usage patterns"
**Acceptance**: Gumroad/Stripe page live, first paying user
**Actions**:
1. Set up Gumroad product: "CTX Pro — cross-user auto-tune"
2. WTP test: show upgrade CTA to users whose `utility_rate` improved ≥10pp after auto-tune
3. Pro feature: auto-tune params updated weekly from cross-user data
**Blocked by**: M3 (need validated signal before monetizing it)

---

## Fast-Validation Gates

| Milestone | Gate | Pass Condition |
|-----------|------|---------------|
| M1 | Turso row count | `SELECT COUNT(*) FROM ctx_session_aggregates` > 0 |
| M2 | install output | `ctx-install 2>&1 \| grep -i "telemetry"` returns result |
| M3 | causal r | r > 0.20 on cross-user data |
| M4 | awesome-claude-code | issue auto-labelled `validation-passed` |
| M5 | HN | item indexed at news.ycombinator.com |
| M6 | Pro | first Stripe payment confirmed |

---

## Anti-patterns to Avoid

- Monetizing before M3 (no validated signal = no WTP)
- Submitting awesome-claude-code via API again (7-day cooldown, must use web form)
- Using FRWP Turso DB long-term (migrate to dedicated `ctx-telemetry` DB when write token goes into pip package)
- Exposing TURSO_WRITE_TOKEN in pip package source (rotate to write-only token before M2 publish)
