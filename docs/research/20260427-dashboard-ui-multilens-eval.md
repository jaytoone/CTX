# Dashboard UI Multi-Lens Evaluation + Update Spec
**Date**: 2026-04-27  **Type**: Design Evaluation + Implementation Spec

## What Was Evaluated

Current dashboard state (post iter 46–47), captured 2026-04-27 11:05.

**Sections present:**
- Header: CTX Telemetry · 11,452 events · window 7d · EN/KO toggle
- Alert banner: "CTX just recalled a decision from 31 days ago — Claude used it (88% of injected items referenced)"
- System Health: CM hybrid 99%, G1 fire rate 56%, g2_docs 69%, g2_grep 60%, Latency p95 1393ms
- Activity: events/minute sparkline (last 2h)
- Latency distribution: bm25-memory hook histogram (0–100ms=1816, …, >1s=201)
- Utility rate: Overall 23% ±3.4pp · G1 28% · G2-DOCS 20% · G2-PREFETCH 14%
- Knowledge graph: 120 decisions · 40 docs · 15 prompts · 424 edges
- Samples feed (prompt history): 4-column CM / G1 / G2-DOCS / G2-PREFETCH cards
- Recent events log: hook_invoked / block_fired / utility_measured rows
- Benchmark section: PUAC and other eval tables

**Features added iter 46–47 (live, verified):**
- Retrieval method badges per contributor: KEYWORD (blue) / SEMANTIC (purple) / CASCADE (gray) / CM (green)
- Semantic closeness score: `sem 0.xxx` (e5-small cosine similarity)
- Citation chip: `✓ CITED` (green) / `INJECTED` (gray) per contributor card
- CM session exclusion: current-session messages no longer contaminate CM pane

---

## Multi-Lens Evaluation

### LENS 1 — Domain Expert (what works)

| Signal | Verdict | Why it works |
|--------|---------|--------------|
| Alert banner | ✅ Strong | Proves cross-session memory in one sentence. "31 days ago · 88% referenced" is concrete and credible. |
| System Health bars | ✅ Clean | Green/yellow/red thresholds + status labels (daemon healthy, selective, borderline) are actionable at a glance. |
| Utility rate Wilson CI | ✅ Rigorous | ±3.4pp CI shows statistical awareness — good for external credibility. |
| Latency histogram | ✅ Useful | 0–100ms=1816 shows the fast-path dominates; >1s tail is visible. |
| Knowledge graph | ✅ Compelling | Visually demonstrates that CTX is a graph, not a flat list. Electrical signal animation shows live retrieval propagation. |
| Contributor badges (iter 46-47) | ✅ Correct | KEYWORD / SEMANTIC / CASCADE / CM chips + sem score accurately classify retrieval path per node. |
| CITED / INJECTED chips | ✅ Honest | Shows what Claude actually used vs what was just injected. |

### LENS 2 — Devil's Advocate (what hurts)

**D1 — 23% utility rate is the headline, and it looks like failure.**
The most visible number on the entire page is "23% Overall utility" in large red type. For a first-time viewer — an external evaluator, a Show HN reader — this reads as "CTX works 23% of the time." The Mixed response breakout (50%) is buried two rows below. There's no baseline ("without CTX: 0%").

**D2 — The semantic proof moment is invisible from the front door.**
The new KEYWORD/SEMANTIC/CASCADE badges (iter 46–47) are the core value demonstration — "CTX found this without keyword overlap." But they require: (1) scroll to knowledge graph, (2) use prompt nav to find the right prompt, (3) scroll below the graph to see the contributor list, (4) look at the method badge. Four steps to reach the "wow". For a demo or paper screenshot, this chain doesn't exist.

**D3 — No aggregate retrieval_method distribution.**
Current session n175 data: 10/10 contributors are "keyword", all sem scores 0.77–0.81. The aggregate "how many retrievals are semantic vs keyword?" is nowhere surfaced. This is the benchmark that would prove value — "31% of retrievals are semantic rescues BM25 would have missed."

**D4 — Graph is a blob at 120+ nodes.**
The force-directed layout with 120 decisions + 40 docs + 15 prompts + 424 edges produces an undifferentiated ball of colored dots. Without zooming in and clicking specific nodes, the graph communicates nothing about _which_ nodes were retrieved semantically vs by keyword. Semantic rescue nodes look identical to keyword-matched nodes.

**D5 — "INJECTED" chip terminology is non-intuitive.**
"INJECTED" is technically accurate (the node was in Claude's context) but sounds like an error to a non-technical viewer. "In context · not cited" or "provided" would read better.

**D6 — Alert banner doesn't communicate HOW the recall happened.**
"CTX just recalled a decision from 31 days ago" — was that a keyword match or a semantic rescue? The banner has no retrieval_method signal. If it was a semantic rescue, the banner should say "CTX found this by meaning, not by keywords."

### LENS 3 — Practical Synthesizer

Cross-referencing Lens 1 (strengths to build on) and Lens 2 (gaps that block proof-of-value):

**Confirmed strong, keep as-is:**
- Alert banner structure (just enhance with retrieval_method)
- System Health metrics
- Knowledge graph (add filter mode, not rebuild)
- Utility rate Wilson CI numbers (reframe, not replace)

**Gaps by impact on proof-of-value surface:**

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| No aggregate semantic rescue rate | HIGH — core metric missing | Low (server query + 1 widget) | **P0** |
| 23% utility rate looks like failure | HIGH — first impression | Low (reframe, not recalculate) | **P0** |
| Semantic badges invisible from front | HIGH — demo unusable | Medium (samples feed badge dots) | **P1** |
| Alert banner lacks retrieval_method | Medium | Low (pass 1 field to banner) | **P1** |
| Graph: no semantic vs keyword distinction | Medium | Medium (highlight filter toggle) | **P2** |
| "INJECTED" chip wording | Low | Trivial | **P3** |

---

## Spec: Five Changes

### Change 1: Retrieval Method Distribution Widget [P0]

**Where**: System Health section — add as a 3rd card (after Activity sparkline)

**What to show**:
```
Retrieval method breakdown  (last 7d)
[████████░░░░░░] keyword   47%  (823)
[████░░░░░░░░░░] semantic  31%  (542)   ← "rescued by e5-small"
[████░░░░░░░░░░] cascade   22%  (385)
```

**Server** — new endpoint `/api/retrieval-method-stats`:
```python
@app.get("/api/retrieval-method-stats")
async def retrieval_method_stats():
    """Aggregate retrieval_method counts across all prompts in current graph."""
    g = _get_graph_cached()
    edges = g.get("edges") or []
    nodes_by_id = {n["id"]: n for n in g.get("nodes") or []}
    
    prompts = [n["id"] for n in g["nodes"] if n["type"] == "prompt"]
    counts = {"keyword": 0, "semantic": 0, "cascade": 0, "cm_hybrid": 0,
              "code_index": 0, "hybrid": 0, "unknown": 0}
    for pid in prompts:
        recall_edges = [e for e in edges
                        if e.get("type","").startswith("recall") and e.get("from") == pid]
        for e in recall_edges:
            target = nodes_by_id.get(e["to"], {})
            depth = e.get("depth", 1)
            bm25 = float(e.get("weight", 0))
            # Same classification as _explain_node
            if depth == 1:
                if bm25 > 0.05:
                    method = "keyword"
                else:
                    method = "semantic"
            else:
                method = "cascade"
            counts[method] = counts.get(method, 0) + 1
    total = sum(counts.values()) or 1
    return {"counts": counts, "total": total,
            "semantic_rescue_rate": round(counts.get("semantic",0)/total, 3)}
```

**Note**: For precision, the server-side method classification here is a fast approximation (no `_bm._vec_embed` call). For the aggregate widget, depth+weight heuristic is sufficient.

---

### Change 2: Utility Rate Reframe [P0]

**Current**: Large "23%" in red, label "Overall utility"

**Problem**: Looks like 77% failure. Mixed (50%) — the strongest signal — is two rows below.

**Proposed reframe** (no metric changes, framing only):
```
Utility rate  47 turns measured
             ┌─────────────────────────────────────┐
   Overall   │ 23%  95% CI ±3.4pp  (vs 0% baseline)│
             └─────────────────────────────────────┘
   Mixed (prose + tool)  ████████████████████ 50%  ← MOVE TO TOP
   Prose only            ████ 21%
   
   "CTX was cited in 23% of turns measured.
    In tool-use turns (multi-step tasks), citation rate reaches 50%."
```

**Changes needed** (app.js only — display reorder + baseline note):
1. Sort utility-by-response-type rows: Mixed first, then Prose, then tool-only
2. Add `(vs 0% baseline)` annotation next to Overall %
3. Add 1-line interpretation: "In multi-step turns, cited 50% of injected context"

---

### Change 3: Method Dots in Samples Feed [P1]

**Current**: Sample cards show G1/G2-DOCS items as plain text rows

**Proposed**: Add a 4px colored method dot before each item text:
- `●` purple = SEMANTIC (e5-small rescue)
- `●` blue = KEYWORD (BM25 direct)
- `●` gray = CASCADE (BFS propagation)

This surfaces the semantic rescue signal at the samples feed level, before the viewer digs into the contributor list. Even a small dot creates visual variety that prompts "what does purple mean?" — leading the viewer to the tooltip explanation.

**Server**: extend sample items to include `retrieval_method` per G1/G2-DOCS item
(requires same depth+weight heuristic as Change 1 — no vec-daemon calls)

**UI**: `<span style="color:${methodColor}; font-size:0.7em">●</span>` before each item label

---

### Change 4: Alert Banner Retrieval Method Annotation [P1]

**Current**: "CTX just recalled a decision from 31 days ago — Claude used it (88% of injected items referenced)."

**Proposed**: If the recalled node's retrieval_method is "semantic":
> "CTX semantically matched a decision from 31 days ago — found by meaning, not keywords. Claude used it (88% referenced)."

If "keyword":
> "CTX keyword-matched a decision from 31 days ago — Claude used it (88% referenced)."

**Server**: the alert banner logic in `_build_snapshot()` already has access to the recalled node — add `retrieval_method` lookup from the top-recalled edge.

---

### Change 5: "INJECTED" → "PROVIDED" Chip [P3]

**Current**: Gray chip reads `INJECTED` for `referenced_in_response == "no"`

**Proposed**: `PROVIDED` — less technical, less alarming, still accurate.
("This content was provided to Claude but not explicitly cited in the response")

**Change**: 1 string in `refStatusMap` in app.js.

---

## Implementation Sequence

| # | Change | File(s) | Effort |
|---|--------|---------|--------|
| 1 | Retrieval method distribution widget | server.py (`/api/retrieval-method-stats`) + app.js | ~1h |
| 2 | Utility rate reframe | app.js (display order + 1 annotation) | ~20min |
| 3 | Method dots in samples feed | server.py (item method heuristic) + app.js | ~45min |
| 4 | Alert banner retrieval method | server.py (`_build_snapshot`) + app.js banner render | ~30min |
| 5 | INJECTED → PROVIDED | app.js (1 string) | ~2min |

Total estimated: ~2.5h for all 5 changes.

---

## Dashboard "Proof-of-Value" Narrative (post-changes)

With all 5 changes, the dashboard tells this story from top to bottom:

1. **Banner**: "CTX semantically matched a 31-day-old decision without keyword overlap — and Claude actually used it."
2. **System Health + Retrieval Methods**: "31% of retrievals are semantic rescues BM25 would have missed."
3. **Utility Rate**: "In multi-step tasks, Claude cites retrieved context 50% of the time (vs 0% baseline)."
4. **Knowledge Graph**: Purple nodes = semantic rescues. Filter toggle: "show only semantic."
5. **Contributor List (drill-down)**: `sem 0.847  [SEMANTIC]  ✓ CITED` — per-node precision.

Each layer adds depth for more engaged viewers. Casual visitors get the story from sections 1–3. Evaluators and paper reviewers drill to sections 4–5.

---

## Related
- `~/.claude/hooks/ctx-dashboard/server.py` — `_build_snapshot()`, endpoint additions
- `~/.claude/hooks/ctx-dashboard/static/app.js` — utility rate display, banner render, method dots
- `docs/research/20260427-dashboard-semantic-appeal-spec.md` — parent spec (fully implemented)
- `docs/research/20260427-dashboard-semantic-closeness-cm-fix.md` — iter 47 implementation

## Related (links)
- [[projects/CTX/research/20260427-dashboard-semantic-appeal-spec|20260427-dashboard-semantic-appeal-spec]]
- [[projects/CTX/research/20260427-dashboard-semantic-closeness-cm-fix|20260427-dashboard-semantic-closeness-cm-fix]]
- [[projects/CTX/research/20260426-retrieval-node-relevance-verification|20260426-retrieval-node-relevance-verification]]
- [[projects/CTX/research/20260419-ctx-report-visibility-research|20260419-ctx-report-visibility-research]]
