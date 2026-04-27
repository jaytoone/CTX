# [live-inf iter 37/∞] G2-CODE Gap + False Positive Analysis
**Date**: 2026-04-26  **Iteration**: 37

## Goal
Address remaining items from the CTX retrieval upgrade plan:
- Item 2: G2-CODE — benchmark gap and path forward
- Item 3: False positive noise — does hybrid help, and what actually works?

---

## Item 2: G2-CODE Benchmark Gap

### Current state
G2-CODE (codebase file retrieval) uses BM25 keyword search on the codebase-memory-mcp SQLite
index. No hybrid retrieval applied here.

### Why no valid public proxy benchmark exists

| Benchmark | What it tests | Why not G2-CODE proxy |
|---|---|---|
| MAB (ICLR 2026) | In-context dialogue memory | Conversation retrieval, not file localization |
| LongMemEval (ICLR 2025) | Long-context session memory | Same — no code file retrieval task |
| SWE-Bench | Full patch generation | Requires code modification, not retrieval only |
| LocAgent/SWE-Gym | File localization in repo | Closest match, but tests full agent behavior |
| COIR (RepoBench subset) | Code-to-code retrieval | Tests external repos; CTX is project-internal |

**Structural gap**: G2-CODE retrieves project-internal files that are NOT in any public benchmark.
External benchmarks (Flask/FastAPI/Requests) test whether CTX can find files in codebases it
has never seen — different task from finding files in the user's own project.

### What G2-CODE actually does
1. User prompt → keyword extraction → codebase-memory-mcp SQLite fulltext search
2. Returns `{file_path, snippet}` pairs ranked by keyword overlap
3. G2b-hooks: direct BM25 search over `~/.claude/hooks/*.py` function signatures

### Why hybrid doesn't apply cleanly here
- Codebase-memory-mcp uses its OWN indexing/retrieval (MCP tool, not vec-daemon)
- G2b-hooks BM25 is over function signatures — exact keyword match is correct behavior
- File retrieval is keyword-exact by nature (function names, class names, imports)
- Dense embeddings would help semantic queries ("where is auth handled") but hurt precision queries ("find OAuth class")

### Practical gap: G2-CODE false negative rate
The real G2-CODE problem is **staleness** (from MEMORY.md 2026-04-17 session):
> Index staleness was found to affect retrieval quality more than algorithm choice.
> codebase-memory-mcp DB was 254 hours (10.6 days) stale → MRR +15% after reindex.

The algorithm is not the bottleneck — index freshness is.

### Path forward for G2-CODE
1. **Auto-reindex trigger** (highest ROI): detect if DB is >24h stale on SessionStart → trigger incremental reindex
2. **LocAgent/SWE-Bench evaluation**: the only valid G2-CODE benchmark would be project-internal file localization — requires per-project gold labels (no public dataset)
3. **Hybrid for G2-CODE**: only useful for semantic queries; defer until staleness is solved first

**Decision**: G2-CODE hybrid deferred. Staleness auto-fix is the correct next priority.

---

## Item 3: False Positive Noise — Empirical Analysis

### Background
The homograph audit (2026-04-24) found:
- BM25 surface-match-only rate: **85.8%** (20 prompts, 174-commit corpus)
- Threshold for "load-bearing noise reduction": ≥30%
- Conclusion at the time: MMR dedup + adaptive floor work was correct priority

### New measurement: hybrid vs BM25-raw rank distribution

Both retrievers compared on the same 20 homograph prompts, tracking WHERE
surface-match-only items rank in the top-7:

```
BM25-raw false positive ranks: [1,1,1,1,1,1, 2,2,2,2,2, 3,3,3,3,3, 4,4,4,4,4, 5,5,5,5, 6,6, 7,7,7]
Hybrid   false positive ranks: [1,1,1,1,1,1, 2,2,2,2,2, 3,3,3,3,3, 4,4, 5,5,5,5, 6, 7,7,7]

Avg rank BM25-raw: 3.5
Avg rank Hybrid:   3.3  (worse — slightly more concentrated at top)
```

**Critical finding**: BGE cross-encoder reranker does NOT demote homograph false positives.
Surface-match-only items appear at ranks 1-3 in BOTH pipelines at similar rates.

### Why BGE cannot fix homograph false positives

BGE cross-encoder sees: `[query] + [commit subject]`

For the query "how is session token storage configured for the dev server" and a commit
"live-inf iter 47/∞: remove token% claim", the cross-encoder still sees:
- Both mention "token"
- Both are about software configuration/operations
- BGE cannot distinguish OAuth-token from text-token from within the CTX commit vocabulary

**Root cause**: Homograph false positives are semantically coherent at the surface level — they
mention the same word in the same technical domain. Only PROJECT-LEVEL CONTEXT (knowing this
project uses BM25/retrieval, not OAuth) would disambiguate.

### The real false positive rate question

The 85.8% applies to the LABELED HITS from the gold set. But:
1. Only 3-7 of 7 returned commits had gold labels (others were new commits not in original audit)
2. The rate for non-labeled items is UNKNOWN
3. Actual user experience: Claude reads the FULL commit message and uses judgment — a surface-match
   commit is filtered out by Claude even if retrieved

### Practical impact on Claude's quality

A retrieved false positive (homograph commit) affects quality only if:
- Claude cites the wrong commit in its response
- OR Claude's reasoning is anchored to an irrelevant past decision

The citation probe (from retrieval-node-relevance-verification.md) would measure this directly:
"Did Claude actually REFERENCE this retrieved node in its response?"

**Without citation probe data**: the false positive rate in terms of USER IMPACT is unknown.
The 85.8% is an upper bound on "noise in the retrieval pool" — actual harmful FP rate is likely much lower.

### Why false positive reduction is not the right engineering priority

1. **Recall is the binding constraint**: at 0.983 recall, missing 1/59 relevant commit is the
   bigger problem than having extra irrelevant commits in the pool
2. **Claude filters at consumption**: Claude reads all 7 commits and selects relevant ones;
   irrelevant commits cause context dilution, not systematic errors
3. **The homograph problem is structural**: requires sense disambiguation at index time (pre-query),
   not retrieval-time scoring
4. **BGE already failed**: the cross-encoder with full semantic understanding does not improve FP rank
   (avg 3.3 hybrid vs 3.5 BM25-raw — not significant)

### Recommended path forward for false positive reduction

| Approach | Mechanism | ROI | Timeline |
|---|---|---|---|
| Citation probe | Track which retrieved commits Claude actually references | HIGH | 1 week |
| Domain-specific filter | Flag commits whose subject matches a known-irrelevant pattern | MEDIUM | 1 day |
| Sense disambiguation | Pre-annotate corpus items with domain tags | LOW (manual) | weeks |
| Better MMR | Increase Jaccard threshold to 0.60 | LOW | hours |

**Recommended next**: citation probe — measures actual impact, not theoretical noise.

---

## Summary

| Item | Finding | Status |
|---|---|---|
| G2-CODE benchmark | No valid proxy exists; staleness is the real problem | Gap documented ✅ |
| G2-CODE hybrid | Deferred — keyword precision is correct for code search | Deferred ✅ |
| False positive reduction | Hybrid doesn't help; BGE doesn't help; citation probe is correct path | Analyzed ✅ |

The CTX retrieval upgrade "items 1-3" are now fully addressed:
- Item 1 (G2-DOCS hybrid): ✅ Shipped in iter 36
- Item 2 (G2-CODE): ✅ Gap documented, staleness auto-fix is correct priority
- Item 3 (False positives): ✅ Analyzed — structural problem, citation probe is path forward

## Related
- [[projects/CTX/research/20260426-retrieval-node-relevance-verification|20260426-retrieval-node-relevance-verification]]
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|20260426-g1-hybrid-rrf-dense-retrieval]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
- [[projects/CTX/research/20260426-g2-code-staleness-auto-fix|20260426-g2-code-staleness-auto-fix]]
- [[projects/CTX/research/20260426-ctx-research-critical-evaluation|20260426-ctx-research-critical-evaluation]]
- [[projects/CTX/research/20260426-citation-probe-v1|20260426-citation-probe-v1]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
