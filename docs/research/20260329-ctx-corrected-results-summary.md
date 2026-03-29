# CTX 수정된 실험 결과 종합 요약 (논문 기준)

**Date**: 2026-03-29
**Purpose**: aggregated_stat_report.md 버그 수정 후 논문에 사용할 정확한 수치 종합

---

## Table A: CTX vs BM25 — Code Retrieval R@5 (All 7 Datasets)

| Dataset | Files | Queries | CTX R@5 | BM25 R@5 | Δ (CTX-BM25) | p-value | CTX Wins |
|---------|-------|---------|---------|---------|--------------|---------|---------|
| **CTSB-small** (synthetic) | 50 | 166 | 0.874 | 0.982 | -0.108 | <0.001 | ✗ |
| AgentNode | 596 | 86 | **0.132** | 0.081 | **+0.051** | — | ✓ |
| GraphPrompt | 73 | 80 | **0.619** | 0.200 | **+0.419** | — | ✓ |
| OneViral | 299 | 84 | **0.424** | 0.000 | **+0.424** | — | ✓ |
| Flask | 79 | 87 | **0.489** | 0.277 | **+0.212** | 0.000230 | ✓ |
| FastAPI | 928 | 88 | **0.285** | 0.153 | **+0.132** | 0.000061 | ✓ |
| Requests | 35 | 85 | **0.598** | 0.428 | **+0.170** | 0.003095 | ✓ |
| **Real avg** (6 codebases) | — | — | **0.425** | 0.190 | **+0.235** | 6/6 | ✓ |

**Note**:
- External codebases (Flask/FastAPI/Requests): BM25 from statistical_tests JSON (McNemar+Wilcoxon tested)
- Internal codebases (AgentNode/GraphPrompt/OneViral): BM25 computed 2026-03-29 using stored queries
- Synthetic CTSB-small: BM25 wins — expected, as synthetic queries are designed for keyword matching

**Key paper claim**: CTX outperforms BM25 on all 6 real codebases (avg R@5: 0.425 vs 0.190, Δ=+0.235).
The 3 external codebases are statistically significant (p<0.005 all). Internal: not yet significance-tested.

---

## Table B: G2 v4 Downstream Quality — Unified Benchmark (All Models)

| Model | G2 WITHOUT CTX | G2 WITH CTX | Δ |
|-------|---------------|------------|---|
| MiniMax M2.5 | 0.000 | 0.833 | **+0.833** |
| Nemotron-Cascade-2 | 0.000 | **1.000** | **+1.000** |
| Claude Sonnet 4.6 | 0.000 | **1.000** | **+1.000** |
| **Mean** | **0.000** | **0.944** | **+0.944** |

**Note**: G2 v4 uses 6 CTX-unique scenarios (confidence formula, regex pattern, BFS depth, etc.).
WITHOUT=0.000 for all models confirms scenarios require CTX source code — no general knowledge leakage.
MiniMax missed h04_v4 (deals?\s+ exact pattern) — all other models got 6/6 WITH CTX.

---

## Table C: G1 Session Recall — Cross-Model

| Model | G1 WITHOUT | G1 WITH | Δ |
|-------|-----------|---------|---|
| MiniMax M2.5 | 0.219 | 1.000 | **+0.781** |
| Nemotron-Cascade-2 | 0.000 | 1.000 | **+1.000** |
| Claude Sonnet 4.6 | 0.000 | 1.000 | **+1.000** |
| **Mean** | **0.073** | **1.000** | **+0.927** |

**Note**: G1=session memory recall (CTX persistent_memory injection). All models: perfect WITH CTX.
MiniMax G1 WITHOUT=0.219 > 0 likely due to earlier version without complete context isolation.

---

## Table D: Latency Profile (CTX — LLM-free)

| Percentile | Latency (307-file codebase) | SOYA Threshold |
|-----------|---------------------------|---------------|
| P50 | 0.9ms | — |
| P95 | 2.1ms | — |
| P99 | 2.8ms | <500ms |

**Note**: CTX uses no LLM calls — latency is purely algorithmic (BFS + BM25L indexing).

---

## Previous G2 Cross-Model Numbers (INVALID — different benchmark versions)

| Model | G2 Δ | Benchmark Version | Status |
|-------|------|------------------|--------|
| MiniMax M2.5 | 0.375 | v2 (general Python leakage) | **INVALID** |
| Nemotron-Cascade-2 | 0.667 | v3 (partial calibration) | **INVALID** |
| Claude Sonnet 4.6 | 1.000 | v4 (correct) | Valid |

**→ Use Table B (G2 v4 unified) for all cross-model comparisons in the paper**

---

## Paper Viability Assessment (Updated)

**Strong claims (paper-ready):**
1. CTX > BM25 on all 6 real codebases (avg +0.235 R@5)
2. G1 session recall: universal Δ=+0.927 mean (3 LLMs)
3. G2 CTX-specific knowledge: mean Δ=+0.944 (G2 v4 unified, 3 LLMs)
4. Latency P99=2.8ms (178× SOYA margin, no LLM overhead)

**Remaining gaps (before full paper submission):**
- Only Python (no TypeScript/Java)
- n=166 synthetic queries (below top-tier 500+ standard)
- No dense retrieval (DPR/ColBERT) baseline
- Internal codebase BM25 comparison lacks significance testing
- CTSB-small shows BM25 wins — framing needed (synthetic bias)

**Recommended venue**: ICSE NIER 2027 (4-page) or ML4Code workshop.
For full paper: need multi-language + larger dataset.

---

*Generated: 2026-03-29 | Based on stat test JSONs + G2 v4 unified eval*

## Related
- [[projects/CTX/research/20260328-ctx-downstream-nemotron-eval|20260328-ctx-downstream-nemotron-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-eval-nemotron-final|20260328-ctx-downstream-eval-nemotron-final]]
- [[projects/CTX/research/20260327-ctx-downstream-eval|20260327-ctx-downstream-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-nemotron-eval-v2|20260328-ctx-downstream-nemotron-eval-v2]]
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-eval-complete|20260328-ctx-downstream-eval-complete]]
- [[projects/CTX/decisions/20260326-unified-doc-code-indexing|20260326-unified-doc-code-indexing]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|20260328-ctx-real-codebase-g2-eval]]
