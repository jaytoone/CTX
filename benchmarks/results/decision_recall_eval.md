# Decision Recall Rate (DRR) Measurement

**Date**: 2026-03-26
**Decisions tested**: 5 (from docs/decisions/)
**Queries per decision**: 4 natural language queries
**Hit criterion**: any of 4 queries retrieves target file within top-k

## Results

| Metric | Score | Threshold | Status |
|--------|-------|-----------|--------|
| DRR@1 | 0.400 | — | — |
| DRR@3 | 1.000 | ≥ 0.7 | ✅ PASS |
| DRR@5 | 1.000 | ≥ 0.8 | ✅ PASS |

## Per-Decision

| ID | File | Hit@1 | Hit@3 | Hit@5 | Best Query |
|----|------|-------|-------|-------|------------|
| D1 | `20260326-import-bfs-over-ast.md` | ❌ | ✅ | ✅ | why did we choose import BFS over AST pa... |
| D2 | `20260326-non-symbols-frozenset.md` | ✅ | ✅ | ✅ | SEMANTIC_CONCEPT false positive fix froz... |
| D3 | `20260326-path-derived-module-to-file.md` | ❌ | ✅ | ✅ | why we derive module names from file pat... |
| D4 | `20260326-unified-doc-code-indexing.md` | ✅ | ✅ | ✅ | why we added markdown file indexing |
| D5 | `20260326-concept-extraction-sema-conc.md` | ❌ | ✅ | ✅ | SEMANTIC_CONCEPT query parsing fix |

## Interpretation

DRR measures the **결정 기억 복원** capability of the unified AdaptiveTriggerRetriever.
A decision is 'recalled' if at least one of 4 natural language queries about it
surfaces the corresponding `docs/decisions/*.md` file within top-k results.
