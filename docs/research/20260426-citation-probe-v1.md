# [live-inf iter 40/∞] Citation Probe v1 — Measuring Actual Node Citation Rate
**Date**: 2026-04-26  **Iteration**: 40

## Goal
Implement citation probe v1 to measure the actual harmful false-positive rate — i.e., what
fraction of retrieved G1/G2 nodes does Claude actually cite in its response?

**Background** (iter 37 finding):
> "85.8% surface-match-only rate is an upper bound on noise in the retrieval pool — actual
> harmful FP rate is likely much lower. Without citation probe data, the user impact is unknown."

---

## Implementation

### Hook instrumentation (`bm25-memory.py`)

New function `log_retrieved_nodes()`:
```python
def log_retrieved_nodes(project_dir, session_id, prompt, block, items):
    """Append retrieval event to .omc/retrieval_log.jsonl."""
    entry = {
        "ts": time.time(),
        "session_id": session_id,
        "prompt_prefix": prompt[:120],
        "block": block,  # "g1_decisions" | "g2_docs"
        "items": items[:10],  # [{id, text, date?}]
    }
    with open(".omc/retrieval_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")
```

Called after G1 retrieval block (7 items/turn) and G2-DOCS block (5 items/turn).
Also added `_session_id = input_data.get("session_id", "")` capture in `main()`.

### Analysis script (`benchmarks/eval/citation_probe.py`)

Cross-references `.omc/retrieval_log.jsonl` with `vault.db` chat history:
- **Citation heuristic**: ≥2 distinctive keywords from node text appear in assistant response
- **Distinctive** = ≥4 chars, not in STOPWORDS, not generic terms (iter/live/inf/ctx)
- **Subsequent responses**: checks next 3 assistant responses after retrieval timestamp

Output:
```
Block                Retrieved     Cited  Citation%   No resp
------------------------------------------------------------
g1_decisions               N        M      XX.X%         K
g2_docs                    N        M      XX.X%         K
------------------------------------------------------------
TOTAL                      N        M      XX.X%
```

Interpretation thresholds:
- **>50%** → FP reduction IS the right priority (nodes are being used)
- **20-50%** → balanced: both recall and FP matter
- **<20%** → recall is binding constraint (FP reduction low priority)

---

## Verification

```
# Test invocation
CLAUDE_PROJECT_DIR="/path/to/CTX" python3 ~/.claude/hooks/bm25-memory.py --rich << INPUT
{"session_id": "test-001", "prompt": "how is BM25 implemented"}
INPUT

# Log output:
block=g1_decisions items=7 session=test-001 prompt=how is BM25 implemented
block=g2_docs items=5 session=test-001 prompt=how is BM25 implemented
```

Log is accumulating from this session. First real analysis requires ~10 turns of
vault.db data with matching session_ids.

---

## Architecture

```
bm25-memory.py                         citation_probe.py
  │                                           │
  ├─ hybrid_rank_decisions() → G1 nodes       │
  │         │                                 │
  │   log_retrieved_nodes() ─────────┐        │
  │                                  ↓        │
  ├─ hybrid_search_docs() → G2 nodes   .omc/retrieval_log.jsonl
  │         │                          │      │
  │   log_retrieved_nodes() ───────────┘      │
  │                                           │ load
  └─ [response injected to Claude] ──→ vault.db (chat history)
                                             │      │
                                             └──────┘
                                               cross-ref
                                               → citation rate
```

---

## Expected findings (from iter 37 hypothesis)

If citation rate < 20%:
- Confirmed: recall is binding (not FP reduction)
- Engineering priority: continue hybrid retrieval improvements
- The 85.8% surface-match rate doesn't harm quality (Claude filters mentally)

If citation rate > 50%:
- Pivotal finding: FPs actually affect Claude's reasoning
- Engineering priority: domain-specific filter + sense disambiguation
- BGE failure (iter 37) means we need pre-index filtering

---

## Data accumulation plan

The probe runs passively from now — no user action needed. After 5+ sessions:
```bash
python3 benchmarks/eval/citation_probe.py --summary-only
```

Log file: `.omc/retrieval_log.jsonl` (gitignored, grows with sessions)

## Related
- [[projects/CTX/research/20260426-g2-code-gap-and-false-positive-analysis|20260426-g2-code-gap-and-false-positive-analysis]]
- [[projects/CTX/research/20260426-retrieval-node-relevance-verification|20260426-retrieval-node-relevance-verification]]
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260411-g1-g2-architecture-improvements|20260411-g1-g2-architecture-improvements]]
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|20260426-g1-hybrid-rrf-dense-retrieval]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
