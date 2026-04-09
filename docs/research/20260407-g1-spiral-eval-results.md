# G1 Spiral Long-Term Memory Evaluation — Initial Results
**Date**: 2026-04-07  **Type**: Empirical measurement + benchmark design

## Setup

- **Script**: `benchmarks/eval/g1_spiral_eval.py`
- **Projects**: CTX (22d in n=100), PaintPoint (93d in n=100), Entity (1d), FromScratch (1d)
- **Parameters**: n=20 git log window, top-7 inject cap (matching git-memory.py defaults)
- **Metrics**: IP@7, DA@7, SpiralDepth (SD), Spiral Miss/Noise Rates

---

## Results Summary

### n=20 Window (G1 default)

| Project | Decisions in window | Injected | Spiral Clusters | IP@7 | DA@7 | SD mean |
|---------|---------------------|----------|-----------------|------|------|---------|
| CTX | 3 | 3 | 0 | N/A | 0.00 | 0.00 |
| PaintPoint | 17 | 7 | 2 | **0.000** | **1.000** | 1.14 |
| Entity | 1 | 1 | 0 | N/A | 1.000 | 0.00 |
| FromScratch | 1 | 1 | 0 | N/A | 0.000 | 0.00 |
| **Aggregate** | — | — | **2** | **0.000** | — | — |

**Spiral Miss Rate: 100% (2/2 clusters)** — both newest iterations fell outside top-7 cap

### n=100 Extended Window (diagnostic)

| Project | Decisions found | Files with spiral pattern |
|---------|----------------|--------------------------|
| CTX | 22 | 2 |
| PaintPoint | 93 | **28** |

---

## Key Findings

### Finding 1: IP@7 = 0.000 — Version Bumps Crowd Out Spiral Memory

PaintPoint has 17 decisions in the n=20 window, but **version bump commits
(v3.42.x, v3.41.x, ...) fill the top-7 cap**. This pushes the newer iterations
of recurring topics into the tail (positions 8-17).

```
Top-7 injected: v3.42.4, v3.42.3, omc-live iter, v3.42.0, v3.41.7, v3.41.6, v3.41.5
Tail (missed): v3.41.4 (newest iteration of CommentLens spiral — MISS)
               v3.40.1 (newest iteration of Hero section spiral — MISS)
```

**Root cause**: G1's recency ordering is correct but topic-blind. When a rapidly
versioning project commits many version bumps, spiral topic decisions get pushed
below the 7-cap by structurally different (but more recent) commits.

### Finding 2: DA@7 = 0.00 for CTX — Deletion Decisions Are Valid Context

CTX top-7 includes "Old CTX remnants fully removed" (OBSOLETE — files deleted)
and "command hook + additionalContext for SOTA G1" (OBSOLETE — hook restructured).

**However**: These are highly VALID decisions for understanding current project direction.
"Old CTX remnants removed" is essential context for knowing WHY current architecture
exists. The DA@7 git-oracle proxy **incorrectly penalizes deletion-class decisions**.

**Implication**: DA@7 proxy (file still active = ALIGNED) has a systematic false negative
for deletion/retirement decisions. True Validity@5 requires human annotation to distinguish
"VALID but file deleted" from "OBSOLETE: code replaced without intentional decision".

### Finding 3: DA@7 = 1.000 for PaintPoint — Alignment Is Excellent on Active Projects

All 7 injected PaintPoint decisions point to files that still exist in HEAD.
For projects with primarily additive development (no major architectural rework),
DA@7 proxy is a reliable ALIGNED signal.

### Finding 4: Spiral Patterns Require n=100+ to Detect

- n=20 window: **2 spiral clusters** found
- n=100 window: **28 spiral file clusters** in PaintPoint alone (0.28 clusters/decision)

G1's n=20 window is **too short** to capture spiral recurrence. Most recurring topics
span 30-100 commits (10+ days in active projects).

### Finding 5: SpiralDepth Mean = 1.14 — Projects Are Primarily Layer 0-1

Injected decisions are mostly Layer 0 (introduction) and Layer 1 (problem identification).
Layer 2-3 commits (solutions, integrations) are rarer — they tend to occur after longer
development spirals that fall outside the n=20 window.

---

## Metric Definitions (Finalized)

| Metric | Definition | Automation | Current Value |
|--------|-----------|-----------|---------------|
| **IP@7** | Fraction of spiral clusters where newest iteration in injected top-7 | Full auto (git) | 0.000 (n=20) |
| **DA@7** | Fraction of injected decisions with active code files in HEAD | git-oracle proxy | 0.000–1.000 (varies) |
| **SD** | Mean spiral depth layer (0=intro, 1=problem, 2=solution, 3=integration) | Full auto (keywords) | 1.14 avg |
| **Spiral Miss Rate** | % of clusters where newest is in tail (not injected) | Full auto | 100% (n=20) |
| **Spiral Noise Rate** | % of clusters where ALL iterations injected (redundant) | Full auto | 0% |

---

## Limitations of Current Measurement

1. **n=20 too small**: Only 2 spiral clusters detected (insufficient for statistical conclusions)
2. **DA@7 proxy flaw**: Deletion decisions marked OBSOLETE despite being valid context
3. **Topic clustering by file**: Different decisions on same file ≠ same logical topic
   (e.g., unrelated bug fix + feature add to same file = false spiral)
4. **SpiralDepth layer keywords are heuristic**: "fix" could be Layer 2 (solution) or just
   a minor patch; human validation needed

---

## Implications for G1 Design

### Immediate improvement: topic-aware reranking in get_git_decisions()

Current behavior: top-7 by recency (topic-blind)
Proposed: deduplicate by topic cluster → inject newest-per-topic before others

```python
# Pseudocode for topic-deduplication
topic_seen = {}  # file_key → best (newest) decision index
for i, decision in enumerate(decisions_in_window):
    tk = extract_topic_key(decision)
    if tk not in topic_seen:
        topic_seen[tk] = decision  # first = newest (recency-ordered)
    # else: skip older iteration of same topic

topic_prioritized = list(topic_seen.values())[:7]
# fallback: fill remaining slots with non-spiral decisions
```

**Expected impact**: IP@7 would jump from 0.000 → ~1.000 by ensuring each topic's
newest iteration is always preferred.

### Increase n or use topic-window instead of time-window

For projects with >10 decisions in n=20 (PaintPoint: 17/20), the 7-cap is binding.
Options:
1. **Increase cap to 10**: reduces compression pressure
2. **Topic-window**: scan n=50 but inject 1 decision per topic cluster

---

## Paper Metric Mapping (from 20260407-g1-temporal-evaluation-framework.md)

| Paper Metric | Current Value | Gap |
|---|---|---|
| IP@7 (NEW) | 0.000 (n=20) | Need n≥50 for meaningful baseline |
| DA@7 proxy | 0.000–1.000 | DA@7 proxy has deletion-class FN |
| Validity@5 | **Not measured** | Requires human annotation 30-50 decisions |
| Conflict Rate | 0.0% (from staleness eval) | Baseline established |
| Staleness Rate | 35.7% (from staleness eval) | Baseline established |
| SpiralDepth | 1.14 avg | Valid — Layer 0-1 dominant |

---

## Next Steps

1. **Fix IP@7 flaw**: Add topic-aware deduplication to `get_git_decisions()` → re-measure
2. **Human annotation**: Label 30 decisions across 4 projects for true Validity@5
3. **Extend to n=50**: Re-run with larger window → more spiral clusters for statistical power
4. **Deletion-class fix for DA@7**: Add "RETIRED_VALID" class for deletion decisions

---
- [G1 temporal evaluation framework](20260407-g1-temporal-evaluation-framework.md)
- [G1 temporal eval results (staleness)](20260407-g1-temporal-eval-results.md)
- [Established benchmarks (G1/G2)](20260407-g1g2-established-benchmarks.md)

## Related
- [[projects/CTX/research/20260402-project-understanding-evaluation-framework|20260402-project-understanding-evaluation-framework]]
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260407-g1-temporal-evaluation-framework|20260407-g1-temporal-evaluation-framework]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260407-g1g2-established-benchmarks|20260407-g1g2-established-benchmarks]]
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
- [[projects/CTX/research/20260326-ctx-benchmark-validation-roadmap|20260326-ctx-benchmark-validation-roadmap]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
