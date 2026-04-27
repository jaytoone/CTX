# [live-inf iter 38/∞] G2-CODE Staleness Auto-Fix — Auto-Reindex on UserPromptSubmit
**Date**: 2026-04-26  **Iteration**: 38

## Goal
Implement G2-CODE staleness detection + automatic background reindex — the highest-ROI
improvement identified in iter 37's G2-CODE gap analysis.

**Root cause** (from iter 37): index staleness affects retrieval quality more than algorithm
choice. CTX codebase-memory-mcp DB was 7.1 days (171h) stale at the start of this session
— confirmed by node count 2441 before vs 3693 after reindex.

---

## Implementation

### Tool Discovery
The reindex tool was found by querying the MCP server's `tools/list` endpoint directly:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | codebase-memory-mcp
```
Relevant tools discovered:
- `index_repository` — `{"repo_path": str, "mode": "full"|"fast"}` (fast = incremental)
- `index_status` — check indexing status

Previously, `codebase-memory-mcp cli index_*` guesses all failed with "unknown tool". Direct
MCP protocol was the correct discovery method.

### New functions in `~/.claude/hooks/bm25-memory.py`

```python
_REINDEX_LOCK = "~/.cache/codebase-memory-mcp/.reindex_in_progress"
_STALE_THRESHOLD_HOURS = 24

def check_and_trigger_reindex(project_dir, db_path):
    """Detect DB staleness; spawn background reindex if >24h old."""
    age_hours = (time.time() - os.path.getmtime(db_path)) / 3600
    if age_hours < 24: return None  # fresh

    # Check lock file (< 10 min old = reindex already running)
    if lock_exists_and_fresh(): return f"⚠ G2-CODE DB stale — reindex already running"

    # Spawn background, non-blocking
    subprocess.Popen(
        ["codebase-memory-mcp", "cli", "index_repository",
         json.dumps({"repo_path": project_dir, "mode": "fast"})],
        stdout=DEVNULL, stderr=DEVNULL, start_new_session=True
    )
    open(_REINDEX_LOCK, "w").close()
    return f"⚠ G2-CODE DB stale ({age_str}) — auto-reindex triggered (fast mode, background)"
```

### Wiring
Inserted into G2-PREFETCH block after `find_db()` returns:
```python
if db_path:
    stale_warn = check_and_trigger_reindex(project_dir, db_path)
    if stale_warn:
        lines.append(stale_warn)
    graph_results = search_graph_for_prompt(db_path, keywords)
    ...
```

### Fail-safe behavior

| Condition | Behavior |
|---|---|
| DB fresh (< 24h) | No action, no output |
| DB stale, no lock | Spawn background reindex + emit warning + create lock |
| DB stale, lock < 10 min | Emit "reindex already running" |
| DB stale, lock > 10 min | Treat as completed, spawn new reindex |
| `codebase-memory-mcp` not in PATH | Exception → emit "run manually" hint |

---

## Verification

### Before (7.1 days stale)
```
DB mtime: 2026-04-19 19:32
Node count: 2441
```

### After auto-reindex (background, fast mode)
```
DB mtime: 2026-04-26 22:31  (updated)
Node count: 3693  (+1252 nodes, +51%)
DB age: 1.9 minutes
```

Node count increased by 51% because fast mode picks up all file changes from iters 34-37
(new hooks functions, new research docs, modified benchmarks).

### Lock file behavior
- Lock created: `~/.cache/codebase-memory-mcp/.reindex_in_progress`
- Subsequent hook calls within 10 min emit "already running" (no duplicate spawns)
- After reindex completes, next UserPromptSubmit confirms DB is fresh → no action

---

## Architecture impact

| Surface | Before | After |
|---|---|---|
| G2-CODE DB freshness | Manual reindex only (user had to notice) | Auto-detected + auto-fixed on first prompt after 24h |
| G2-CODE retrieval quality | MRR degrades silently with staleness | Self-healing: lag ≤ 24h + 1 UserPromptSubmit |
| User experience | No warning on stale DB | Visible `⚠ G2-CODE DB stale` warning + auto-fix confirmation |

**Check frequency**: Every UserPromptSubmit (O(1) = stat syscall only, negligible latency).
**Reindex latency**: Fast mode runs in background — zero impact on hook response time.

---

## Summary

| Item | Status |
|---|---|
| Tool discovery | `index_repository` via MCP stdio `tools/list` ✅ |
| Staleness detection | `os.path.getmtime` < 24h threshold ✅ |
| Background reindex | `subprocess.Popen(start_new_session=True)` ✅ |
| Lock file guard | 10-min window prevents concurrent spawns ✅ |
| Verification | 2441 → 3693 nodes after auto-trigger ✅ |

The G2-CODE staleness problem (identified in 2026-04-17 session as silent failure mode,
quantified in iter 37 as "staleness > algorithm as ROI driver") is now self-healing.

## Related
- [[projects/CTX/research/20260426-retrieval-node-relevance-verification|20260426-retrieval-node-relevance-verification]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260411-auto-index-necessity-analysis|20260411-auto-index-necessity-analysis]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
- [[projects/CTX/research/20260424-memory-experiential-eval-protocol|20260424-memory-experiential-eval-protocol]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260411-chat-memory-threshold-principled|20260411-chat-memory-threshold-principled]]
