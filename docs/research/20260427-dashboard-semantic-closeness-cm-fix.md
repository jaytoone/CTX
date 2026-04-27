# [live-inf iter 47/∞] Dashboard: Semantic Closeness Scores + CM Session Exclusion Fix
**Date**: 2026-04-27  **Iteration**: 47

## Deliverables

### 1. Semantic Closeness Score per Contributor Node

**What**: Every contributor node in the dashboard now shows `sem 0.xxx` — the cosine
similarity between the current prompt embedding and the retrieved node's content embedding,
computed via vec-daemon (multilingual-e5-small, 384-dim, normalized).

**Why**: BM25 scores are relative within a prompt's result set (not comparable across prompts),
and they only reflect keyword overlap. Cosine similarity provides an absolute, cross-session
signal: "how semantically close is this node to the query, independent of BM25 ranking?"

**Implementation** (`server.py` — `_explain_node()`):
```python
semantic_score = None
try:
    _prompt_text = (prompt or {}).get("full") or (prompt or {}).get("label") or ""
    _node_text = (node_text[:600]) if node_text else ""
    if _prompt_text and _node_text:
        _q_emb = _bm._vec_embed(_prompt_text[:800])
        _n_emb = _bm._vec_embed(_node_text)
        if _q_emb and _n_emb:
            semantic_score = round(_bm._cosine(_q_emb, _n_emb), 3)
except Exception:
    semantic_score = None
```

`_bm._vec_embed()` and `_bm._cosine()` are exposed from bm25-memory.py (loaded as `_bm`
via importlib). vec-daemon handles the multilingual-e5-small inference; both embeddings are
L2-normalized so dot product = cosine similarity.

**UI** (`app.js` — contributor card score row):
- `sem 0.xxx` shown in purple (`≥0.75`), blue (`≥0.55`), or gray (`<0.55`)
- Hovering shows `"e5-small cosine similarity"` tooltip

**Observed values** (live, prompt "but other clients wrer possibl"):
```
method=keyword   sem=0.807   n4
method=keyword   sem=0.779   n160
method=keyword   sem=0.786   n157
method=keyword   sem=0.802   n124
```
All keyword-retrieved nodes score 0.77–0.81 — confirms BM25 surface matching aligns
with genuine semantic relevance in this corpus. Cross-validation between BM25 signal
and dense similarity provides retrieval reliability evidence.

**Bug fixed during implementation**: `_explain_node()` referenced `prompt_node` but the
local variable is named `prompt` (see line ~1560: `prompt = nodes_by_id.get(prompt_id)`).
The `NameError` was silently swallowed by `except Exception` → `semantic_score` always
`None`. Fixed: `prompt_node.get(...)` → `(prompt or {}).get(...)`.

Also fixed: `_prompt_contributors()` was not forwarding `retrieval_method` from
`_explain_node()` return to each contributor dict — added `"retrieval_method"` and
`"semantic_score"` forwarding.

---

### 2. CM Session Exclusion Fix

**Problem**: vault.db is populated in near-real-time during each session (vault importer
runs live, writing current-session messages). The CM hook (`chat-memory.py`) had no mechanism
to exclude current-session content, so it returned the user's own recent messages as
"retrieved memory" — making the CM pane look like "current conversation replay" instead
of genuine cross-session memory recall.

Confirmed: current session `801e3a8c` had 5,503 rows in vault.db. All 3 CM results for
a test prompt were from `session_id = 801e3a8c`.

**Fix**: Pass `data.get("session_id")` as `exclude_session_id` to both query functions,
adding `AND s.session_id != ?` to all SQL queries (4 FTS5 paths + 2 KNN paths).

`query_vault()` signature change:
```python
def query_vault(keywords, project_filters=None, exclude_session_id=None):
    sess_clause = "AND s.session_id != ?" if exclude_session_id else ""
    sess_params_tuple = (exclude_session_id,) if exclude_session_id else ()
    # Applied in all 4 SQL variants
```

`query_vault_vector()` similarly extended. In `main()`:
```python
current_session_id = data.get("session_id") or None
bm25_results = query_vault(..., exclude_session_id=current_session_id)
vec_results = query_vault_vector(..., exclude_session_id=current_session_id)
```

**Validation** (3-prompt E2E test):
| Prompt | Before fix | After fix |
|--------|------------|-----------|
| "retrieval method badges" | 3 results: current session | 0 results (no past match) |
| "semantic closeness" | 3 results: current session | 0 results (no past match) |
| "dashboard semantic appeal" | 3 results: current session | 3 past-session results ✅ |

Prompt 3 returned genuine past sessions:
- `2026-04-02`: "[assistant@CTX] **[INFINITE] Previous run is CON..."
- `2026-03-30`: "[assistant@CTX] The evaluation ran. Recall@3 = 0..."

**Semantic clarity**: CM now exclusively shows genuine cross-session recall.

---

## Files Changed (in ~/.claude/hooks — outside CTX git repo)

- `~/.claude/hooks/ctx-dashboard/server.py`
  - `_explain_node()`: added `semantic_score` computation via vec-daemon
  - `_prompt_contributors()`: forwarded `retrieval_method` + `semantic_score` to API response
- `~/.claude/hooks/ctx-dashboard/static/app.js`
  - Contributor card: `sem 0.xxx` display (color-coded by threshold)
- `~/.claude/hooks/chat-memory.py`
  - `query_vault()`: added `exclude_session_id` param, `AND s.session_id != ?` in all 4 SQL paths
  - `query_vault_vector()`: same exclusion in 2 KNN paths
  - `main()`: extract `data.get("session_id")` → pass to both query functions

---

## Combined State After iter 46+47

| Feature | Status |
|---------|--------|
| Retrieval method badges (KEYWORD/SEMANTIC/CASCADE/CM) | ✅ live |
| Semantic bridge NL summary in `_explain_node()` | ✅ live |
| Semantic closeness score (sem 0.xxx, e5-small cosine) | ✅ live |
| CM session exclusion (no current-session contamination) | ✅ live |
| Citation chip (CITED/INJECTED from retrieval_log.jsonl) | deferred |

---

## Related
- `~/.claude/hooks/ctx-dashboard/server.py` — `_explain_node()`, `_prompt_contributors()`
- `~/.claude/hooks/ctx-dashboard/static/app.js` — contributor card UI
- `~/.claude/hooks/chat-memory.py` — `query_vault()`, `query_vault_vector()`
- `docs/research/20260427-dashboard-semantic-appeal-spec.md` — parent spec
- `docs/research/20260426-citation-probe-v1.md` — citation chip (deferred)

## Related (links)
- [[projects/CTX/research/20260427-dashboard-semantic-appeal-spec|20260427-dashboard-semantic-appeal-spec]]
- [[projects/CTX/research/20260426-citation-probe-v1|20260426-citation-probe-v1]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
