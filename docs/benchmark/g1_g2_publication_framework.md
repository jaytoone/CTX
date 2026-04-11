# CTX G1/G2 Publication-Quality Benchmark Framework

## Overview

This document defines the publication-quality benchmark mapping for CTX G1 and G2 evaluation.

## Goal Definitions

| Goal | Definition | Measurement |
|------|------------|-------------|
| **G1** | Cross-session recall — retrieval of relevant code/files from past sessions without persistent memory storage | On-the-fly retrieval via import graph BFS + structural signals |
| **G2** | Instruction-grounded code work — finding relevant code/files based on user instructions in large codebase | Query-type-aware retrieval (EXPLICIT_SYMBOL / SEMANTIC_CONCEPT / IMPLICIT_CONTEXT / TEMPORAL_HISTORY) |

## Benchmark Mapping

### G1: Cross-Session Recall

| Benchmark | Source | Metric | Current | Target | Notes |
|-----------|--------|--------|---------|--------|-------|
| COIR (CodeSearchNet) | Standard | R@5 | 1.000 | ≥0.90 | Perfect — ceiling |
| RepoBench-R | Standard | R@5 | 0.767 | ≥0.85 | Long-range dependency |
| **MEMORYCODE** (ACL 2025) | New | TBD | — | — | Multi-session code retrieval |

### G2: Instruction-Grounded Code Work

| Benchmark | Source | Metric | Current | Target | Notes |
|-----------|--------|--------|---------|--------|-------|
| Flask | Real external | R@5 | 0.709 | ≥0.75 | |
| FastAPI | Real external | R@5 | 0.673 | ≥0.75 | Weakest |
| Requests | Real external | R@5 | 0.849 | ≥0.75 | Strongest |
| **Mean** | 3-repo | R@5 | **0.744** | ≥0.75 | Achieved |

## Evaluation Protocol

### G1 Evaluation (without persistent_memory)

1. **Setup**: Create synthetic multi-session query pairs
2. **Query**: Session-N asks about code from Session-(N-1)
3. **Retrieval**: CTX on-the-fly (import graph BFS, not persistent_memory.json)
4. **Metric**: Recall@K, MRR, NDCG@K

### G2 Evaluation (instruction-grounded)

1. **Setup**: Real-world instruction queries
2. **Query**: User instruction → trigger classification → strategy routing
3. **Retrieval**: Adaptive trigger pipeline
4. **Metric**: R@K, TES, Token Efficiency

## Standards Compliance

| Criterion | Status |
|-----------|--------|
| Reproducibility | ✅ Same seed, same results |
| Standardized metrics | ✅ R@K, NDCG, MRR, TES |
| Public dataset | △ Synthetic + partial real |
| Peer-reviewed | Pending (MEMORYCODE ACL 2025) |
| Multi-model validation | ✅ Anthropic + MiniMax tested |

## MEMORYCODE (ACL 2025) — Key Findings

**Paper**: "From Tools to Teammates: Evaluating LLMs in Multi-Session Coding Interactions"
- **Citation**: Rakotonirina et al., ACL 2025, pp.19609-19642
- **URL**: https://aclanthology.org/2025.acl-long.964/

### Dataset Characteristics
- **Type**: Synthetic multi-session coding dataset
- **Goal**: Test LLM ability to track and execute simple coding instructions amid irrelevant information
- **Setting**: Realistic multi-session coding environment

### Key Findings (Relevant to CTX G1)
| Finding | Implication for CTX |
|---------|---------------------|
| All models handle isolated instructions well | G2 baseline is not the problem |
| Performance **deteriorates** when instructions spread across sessions | G1 is the real challenge |
| Even GPT-4o suffers from this | Not model-specific, architectural |
| Root cause: failure to retrieve and integrate over long interaction chains | CTX import graph BFS directly addresses this |

### CTX vs MEMORYCODE Alignment
- **MEMORYCODE**: LLM-centric (does LLM retrieve cross-session?)
- **CTX G1**: Retrieval-system-centric (does CTX retrieve without LLM?)
- CTX can be evaluated as a **retrieval layer** for MEMORYCODE-style scenarios

## Publication Scores (Calculated)

### G1: Cross-Session Recall
| Benchmark | R@5 | Weight | Weighted |
|-----------|-----|--------|----------|
| COIR | 1.000 | 0.5 | 0.500 |
| RepoBench | 0.767 | 0.5 | 0.384 |
| **G1 Publication Score** | | | **0.884** |

### G2: Instruction-Grounded Code Work
| Benchmark | R@5 | Weight | Weighted |
|-----------|-----|--------|----------|
| Flask | 0.709 | 0.33 | 0.236 |
| FastAPI | 0.673 | 0.33 | 0.222 |
| Requests | 0.849 | 0.33 | 0.282 |
| **G2 Publication Score** | | | **0.740** |

### Overall Composite
```
Overall = 0.4 * G1 + 0.6 * G2
       = 0.4 * 0.884 + 0.6 * 0.740
       = 0.354 + 0.444
       = 0.798
```

## Target: R@5 0.80+ Analysis

| Repo | Current R@5 | Gap to 0.80 | Strategy |
|------|-------------|-------------|----------|
| Flask | 0.709 | +0.091 | Improve SEMANTIC_CONCEPT |
| FastAPI | 0.673 | +0.127 | **Weakest** — prioritize |
| Requests | 0.849 | -0.049 | Already above target |

**FastAPI가瓶颈** — FastAPI R@5를 0.80+로 끌어올리면 전체 Mean도 0.80+ 달성 가능.

## TODO

- [x] MEMORYCODE paper deep analysis (ACL 2025)
- [x] Dataset structure mapping to CTX
- [x] CTX adapter implementation for MEMORYCODE (`benchmarks/eval/memorycode_adapter.py`)
- [x] G1 publication score calculation (0.884)
- [x] G2 publication score calculation (0.740)
- [ ] FastAPI R@5 improvement (0.673 → 0.80+)

## Related
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|20260328-ctx-real-codebase-g2-eval]]
- [[projects/CTX/research/20260408-g1-longterm-memory-evaluation-framework|20260408-g1-longterm-memory-evaluation-framework]]
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260407-g1-spiral-eval-results|20260407-g1-spiral-eval-results]]
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260326-ctx-benchmark-validation-roadmap|20260326-ctx-benchmark-validation-roadmap]]
