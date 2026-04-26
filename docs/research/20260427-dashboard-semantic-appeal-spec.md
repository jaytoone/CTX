# Dashboard Semantic Appeal — Research + Spec
**Date**: 2026-04-27  **Type**: Design Research + Implementation Spec

## Problem Statement

Current dashboard shows *what* was retrieved (node list, BM25 scores, matched tokens).
It does NOT show:
1. **Why semantically** — "this node was found even though you didn't use those exact words"
2. **How it helped Claude** — "Claude actually used this information in the response"

These two gaps make the dashboard feel like a debug tool, not a proof-of-value surface.
Users (including external evaluators and paper reviewers) can't see the intelligence of CTX.

---

## Research: What Makes Retrieval Explainability Compelling

### The live proof we have (2026-04-27 session)
Query: `"can the hook be used outside the original project"`
Gold doc: `20260409-bm25-memory-generalization-research.md`
- BM25: **MISS** (zero keyword overlap)
- Hybrid (e5-small): **HIT at rank 4** (semantic bridge: "outside project" ≈ "generalization")

This is the story the dashboard should tell visually. Currently invisible.

### What to show per retrieved node (ranked by impact)

| Signal | What it tells | Current state | Gap |
|--------|---------------|---------------|-----|
| Retrieval method | BM25 (keyword) vs Dense (semantic) vs BGE rerank | Not shown | ❌ |
| Semantic bridge | "why semantically related" — e5-small similarity with explanation | Not shown | ❌ |
| Keyword overlap | Matched tokens (already exists) | Shown | ✓ |
| Injection preview | What was actually sent to Claude | Shown | ✓ |
| Citation signal | Did Claude reference this in response? | Not shown | ❌ |
| BM25 score rank | Raw score | Shown in explain | partial |

### What "semantic bridge" means visually
When a node was rescued by dense embedding (BM25 score = 0, dense score > 0):
- Show: `[SEMANTIC MATCH]` badge (vs `[KEYWORD MATCH]`)  
- Show: The conceptual connection — "your prompt phrase 'X' matched concept 'Y' in this doc"
- This is the WOW moment: "CTX found this even without the keywords"

### Citation signal (from existing citation probe)
`.omc/retrieval_log.jsonl` already logs retrieved nodes per turn.
Citation probe cross-references with vault.db response text.
Current rate: 7.6% — low, but even 1 cited node per session is demonstrable.

---

## Current Dashboard Architecture (what exists)

### Server (`~/.claude/hooks/ctx-dashboard/server.py`)
- `_explain_node(node_id, prompt_id)` → returns: `depth`, `bm25_score`, `matched_tokens`, `token_contributions`, `summary` (NL sentence), `injection_preview`
- Current NL summary for depth-1: "Retrieved because N of M prompt keywords match this node — 'X' alone contributes Y% of the BM25 score."
- **Missing**: no mention of whether dense embedding contributed, no semantic explanation

### What `_explain_node` already computes but doesn't expose
- `bm25_score` — if 0.0 at depth 1, the node was retrieved by e5-small, not BM25
- `matched_tokens` — if empty but node is at depth 1, it's a pure semantic retrieval
- These two facts together = "semantic rescue" signal — just needs to be surfaced

### Frontend (`static/index.html`, `static/app.js`)
- Node detail panel: shows explain data
- Contributor ranking list: shows ranked nodes with scores
- Electrical signal animation: depth-3 propagation

---

## Spec: Three Changes (Research → UI)

### Change 1: Retrieval Method Badge (server + UI)

**Server change** — add `retrieval_method` to `_explain_node` response:
```python
if depth == 1:
    if bm25_score > 0.05 and len(matched_tokens) > 0:
        retrieval_method = "keyword"       # BM25 found it
    elif bm25_score > 0.05:
        retrieval_method = "hybrid"        # BM25 score but no token match (unusual)
    else:
        retrieval_method = "semantic"      # Dense embedding rescued it (BM25 miss)
elif depth == 1 and node_type == "chatmem":
    retrieval_method = "cm_hybrid"
elif depth == 1 and node_type == "code":
    retrieval_method = "code_index"
else:
    retrieval_method = "cascade"           # depth > 1, BFS propagation
```

**UI badge** (contributor list + node detail):
```
[KEYWORD]   ← BM25 matched tokens directly
[SEMANTIC]  ← Dense embedding found it (no keyword overlap) — highlight this
[CASCADE]   ← Reached via BFS from another retrieved node
[CM]        ← Chat memory hybrid
```
Color: KEYWORD=blue, SEMANTIC=purple (distinctive — this is the "wow" signal), CASCADE=gray, CM=green

### Change 2: Semantic Bridge Explanation (server NL summary)

**Replace** current NL summary for `retrieval_method == "semantic"`:

Current:
> "Retrieved by direct BM25 match (score 0.00, 0 matching tokens)."

New:
> "Retrieved by semantic embedding (e5-small) — your prompt phrase matched the concept in this doc without keyword overlap. BM25 alone would have missed it."

**For keyword matches**, keep current summary but upgrade:
> "Retrieved by keyword match — 'X' and 'Y' directly match this doc's content (BM25 score: Z)."

**For cascade nodes (depth 2-3)**:
> "Pulled in via [parent node label] — shares a temporal/topic cluster. Indirect but contextually related."

### Change 3: Citation Indicator (from retrieval_log.jsonl)

**Server** — add `/api/citation-status` endpoint or extend `/api/node-explain`:
```python
# Check if this node was cited in the response following the prompt
# Source: .omc/retrieval_log.jsonl (written by citation_probe v1)
def _check_citation(node_id: str, prompt_id: str) -> bool:
    log_path = Path(project_dir) / ".omc" / "retrieval_log.jsonl"
    if not log_path.exists():
        return None  # unknown
    # scan for turn matching prompt_id, check if node_id in cited_nodes
    ...
```

**UI** — on node card in contributor list:
```
[CITED ✓]   ← Claude actually referenced this in response (green chip)
[INJECTED]  ← Was in context but not explicitly cited (gray)
[UNKNOWN]   ← No citation data available
```

---

## Visual Layout: Contributor List Card (revised)

```
┌─────────────────────────────────────────────────────┐
│ #1  20260409-bm25-generalization-research.md        │
│     [SEMANTIC]  score: 0.84  [CITED ✓]              │
│     "your prompt 'used outside project' matched     │
│      concept 'cross-project generalization'"         │
│     ───────────────────────────────────────         │
│     Injected as: G2-DOCS > bm25-memory-generaliz…  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ #2  2026-04-09: BM25 threshold config change        │
│     [KEYWORD]  score: 0.71  [INJECTED]              │
│     "matched tokens: bm25, threshold, config"       │
│     ───────────────────────────────────────         │
│     Injected as: RECENT DECISIONS > [2026-04-09]…  │
└─────────────────────────────────────────────────────┘
```

---

## Implementation Sequence

1. **Server**: Add `retrieval_method` field to `_explain_node()` — detect semantic vs keyword based on `bm25_score==0 + depth==1`
2. **Server**: Update NL summary strings for each retrieval_method
3. **Server** (optional): Add citation status lookup from `.omc/retrieval_log.jsonl`
4. **UI**: Add method badge to contributor list cards
5. **UI**: Show semantic bridge explanation text (from updated NL summary)
6. **UI**: Add citation chip (CITED / INJECTED / UNKNOWN)

**Not in scope now**: Prompt rewriting for better retrieval, LLM-based query expansion — separate track.

---

## Appeal Narrative for External Viewers

The revised dashboard tells this story:
> "CTX didn't just find keywords. It understood that 'used outside project' means the same thing as 'cross-project generalization' — and retrieved the right doc without a single shared word. Then Claude actually used that information."

This is the differentiator vs keyword-only tools. The dashboard should make that visible at a glance.

---

## Related
- `~/.claude/hooks/ctx-dashboard/server.py` — `_explain_node()`, `/api/node-explain`
- `.omc/retrieval_log.jsonl` — citation probe output (iter 40-41)
- `benchmarks/eval/citation_probe.py` — citation analysis script
- `docs/research/20260426-citation-probe-v1.md` — citation probe design
- `docs/research/20260426-g2-docs-eval-corpus-drift-fix.md` — semantic retrieval proof data
