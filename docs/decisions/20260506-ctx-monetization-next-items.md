# CTX Monetization & PLG — Open Items

**Date**: 2026-05-06
**Source**: Driller framework session (AI-tech monetization drill-down)

---

## Context

Applied the Driller 5-layer monetization framework to CTX. Key findings:

- **Moat**: data flywheel (vault.db accumulation → better retrieval signal) — not the algorithm
- **PLG motion**: team expansion loop (individual engineer → team → Pro paywall)
- **Cold-start fix**: `step_seed_vault()` built and shipped (`3964d39`) — seeds git history into vault.db on install so G1 recall fires in session 1
- **Monetization path**: open-core (free local + Pro cloud vault sync + Team shared memory)

---

## Open Items

### Sprint-ready (next 1-2 weeks)

**1. Sharing trigger at aha moment**
- When G1 recall fires for the first time (Claude references a past decision unprompted), surface a one-line prompt: "Share CTX with your team → [one-click team install link]"
- This activates the team expansion PLG loop
- Currently: G1 fires silently, no social trigger → loop doesn't propagate

**2. Pro paywall design — team vault gate**
- Define the free/Pro boundary: local vault stays free, cloud vault sync is the paywall
- Specific features behind Pro: team shared memory, admin panel, analytics ("your team's top recalled decisions")
- Currently: no paywall exists, 100% free → no conversion path

**3. Force re-seed flag (`--reseed`)**
- Currently `step_seed_vault()` is idempotent (skips if already seeded)
- Need `ctx-install --reseed` to refresh after new commits accumulate
- Or: auto-reseed on `ctx-install` if last seed was >30 days ago

### Quick tasks (hours)

**4. PyPI download stats baseline**
- Check `pypi.org/project/ctx-retriever` download velocity
- Establish current organic growth rate before building any monetization
- Command: `pip index versions ctx-retriever` or check PyPI stats API

**5. Market signal dashboard setup**
- Weekly monitor: GitHub CTX issues + Claude Code Discord + HN keyword alerts
- Keywords: "context loss", "Claude forgot", "cross-session memory", "Claude Code memory"
- Takes ~2 hours to set up, runs passively

---

## Monetization Architecture (decided)

```
Free (local, MIT):
  vault.db grows locally — per-user flywheel
  No data leaves machine

Pro ($15-20/mo):
  Cloud vault sync — data joins aggregate pool
  Better retrieval model (trained on aggregate signals)
  Team shared memory

Team ($49-99/mo):
  Private team vault (company data stays within org)
  Admin panel + audit trail
  Custom retrieval tuning on team's codebase patterns
```

**Value metric**: context injections per session (CS score 4, COGS score 5, composite 20)

---

## Kill Criteria

| Condition | Signal | Action |
|---|---|---|
| Free tier cannibalizes paid | >90% users never hit Pro features | Move team features earlier in paywall |
| Anthropic ships native Claude Code memory | G1 moat commoditized | Pivot moat to import-graph retrieval (R@5 advantage) |
| No team expansion signal after 90 days | Single-user plateau | Skip PLG, go direct B2B sales |

---

## References

- Driller framework: `/home/desk-1/Project/Driller/docs/strategy/20260506-ai-monetization-drill-down-framework.md`
- Vault seed commit: `3964d39` — `feat: seed vault.db with git history on install`
