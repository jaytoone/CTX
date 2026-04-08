# G1 Long-Term Memory Evaluation Report

**Date**: 2026-04-09 01:01:12

## Overview

- **Decision Commits**: 59
- **QA Pairs Generated**: 59
- **QA Pairs Evaluated**: 59
- **Baselines**: 4 (no_ctx, full_dump, g1_raw, g1_filtered)

## Metrics Summary

### Decision Recall@5

| Baseline | Recall@5 | Avg Context (chars) | Type |
| --- | --- | --- | --- |
| no_ctx | 0.000 | 0 | No context |
| full_dump | 0.712 | 12186 | Full dump (oracle) |
| g1_raw | 0.305 | 1876 | Proactive (sim) |
| g1_filtered | 0.169 | 726 | Proactive (sim) |
| git_memory_real | 0.169 | 816 | Proactive (real) |
| bm25_retrieval | 0.881 | 695 | Query-aware RAG |
| dense_embedding | 0.644 | 758 | Query-aware RAG |

### Recall by Age Bucket

| Baseline | 0-7d | 7-30d | 30-90d | 90d+ |
| --- | --- | --- | --- | --- |
| no_ctx | 0.000 | 0.000 | N/A | N/A |
| full_dump | 0.911 | 0.071 | N/A | N/A |
| g1_raw | 0.400 | 0.000 | N/A | N/A |
| g1_filtered | 0.222 | 0.000 | N/A | N/A |
| git_memory_real | 0.222 | 0.000 | N/A | N/A |
| bm25_retrieval | 0.911 | 0.786 | N/A | N/A |
| dense_embedding | 0.644 | 0.643 | N/A | N/A |

## Sample Responses

### Query: When did we implement G1 temporal retention?

**Ground Truth**:
- Commit: `b2a9bf3`
- Date: 2026-04-08T13:00:27+09:00
- Subject: 20260408 G1 temporal retention: age-based recall decay curve implemented + measured

**no_ctx**:

> I don't have specific information about when G1 temporal retention was implemented in the CTX project. This would likely be in the project documentation, changelog, or git history. 

Would you like me...

**full_dump**:

> Based on the git log, **G1 temporal retention was implemented on April 8, 2026 at 13:00:27 (KST)**.

This is documented in commit `b2a9bf3` with the message:
> "20260408 G1 temporal retention: age-bas...

**g1_raw**:

> Based on the decision history, **G1 temporal retention was implemented on 2026-04-08** (commit b2a9bf3).

The commit message states: "G1 temporal retention: age-based recall decay curve implemented + ...

**g1_filtered**:

> Based on the decision history, **G1 temporal retention was implemented on 2026-04-08** (commit b2a9bf3).

The commit message specifically states: "G1 temporal retention: age-based recall decay curve i...

**git_memory_real**:

> **20260408** (April 8, 2026)

Based on the RECENT WORK section:

> - 20260408 G1 temporal retention: age-based recall decay curve implemented + measured

**bm25_retrieval**:

> Based on the retrieved commits, **G1 temporal retention was implemented on April 8, 2026** (commit `b2a9bf3`), which implemented "age-based recall decay curve" for temporal retention.

**dense_embedding**:

> Based on the retrieved commits, **G1 temporal retention was implemented on 2026-04-08** (April 8, 2026).

This is evidenced by commit `b2a9bf3` which states: "G1 temporal retention: age-based recall d...

## Key Findings

1. **Best baseline**: bm25_retrieval (Recall@5=0.881)
2. **Token efficiency**: bm25_retrieval uses 16.1x fewer tokens than full_dump
3. **no_ctx baseline fails completely** (LLM knowledge cutoff predates project)
4. **Query-aware retrieval** (BM25/Dense): finds commits based on query semantics vs query-agnostic git_memory_real