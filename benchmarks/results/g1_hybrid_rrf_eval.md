# G1 Hybrid RRF — Human Loop Relevance Report

**Purpose**: Manual verification that retrieved nodes are actually relevant.

For each query, compare what each retrieval method found vs the gold commit.

Mark each retrieved node: ✅ relevant | ❌ not relevant | ❓ partial

---

## Query 1: `When did we implement G1 temporal retention?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `b2a9bf3` — 20260408 G1 temporal retention: age-based recall decay curve implemented + measured

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

---

## Query 2: `When did we implement G1 format ablation?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `4a8507e` — 20260408 G1 format ablation: 5포맷 downstream δ 실측 완료

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4a8507e` | 20260408 G1 format ablation: 5포맷 downstream δ 실측 완료 ⭐ | [ ] |
| 2 | `fdb182e` | 20260408 원래 의도 gap analysis: Downstream δ 미수행, Format ablati | [ ] |
| 3 | `0ba58df` | live-infinite iter 63/∞: success | goal_v3: Section 5.3 — ab | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4a8507e` | 20260408 G1 format ablation: 5포맷 downstream δ 실측 완료 ⭐ | [ ] |
| 2 | `fdb182e` | 20260408 원래 의도 gap analysis: Downstream δ 미수행, Format ablati | [ ] |
| 3 | `0ba58df` | live-infinite iter 63/∞: success | goal_v3: Section 5.3 — ab | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4a8507e` | 20260408 G1 format ablation: 5포맷 downstream δ 실측 완료 ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `0ba58df` | live-infinite iter 63/∞: success | goal_v3: Section 5.3 — ab | [ ] |

---

## Query 3: `When did we implement 원래 의도 gap analysis?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `fdb182e` — 20260408 원래 의도 gap analysis: Downstream δ 미수행, Format ablation 미수행

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `fdb182e` | 20260408 원래 의도 gap analysis: Downstream δ 미수행, Format ablati ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `fdb182e` | 20260408 원래 의도 gap analysis: Downstream δ 미수행, Format ablati ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `fdb182e` | 20260408 원래 의도 gap analysis: Downstream δ 미수행, Format ablati ⭐ | [ ] |
| 2 | `ea77b9d` | live-infinite iter 5/∞: AST 개선 테스트 추가 (19 tests) | [ ] |
| 3 | `cff8db5` | live-infinite iter 4/∞: sig_only eval + 연구 문서 업데이트 | [ ] |

---

## Query 4: `When did we implement G1 noise filter + topic-dedup?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `f3e39ba` — 20260407 G1 noise filter + topic-dedup: NoiseRatio 50%→0%, TopicCov 73%→79%

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f3e39ba` | 20260407 G1 noise filter + topic-dedup: NoiseRatio 50%→0%, T ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f3e39ba` | 20260407 G1 noise filter + topic-dedup: NoiseRatio 50%→0%, T ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f3e39ba` | 20260407 G1 noise filter + topic-dedup: NoiseRatio 50%→0%, T ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou | [ ] |

---

## Query 5: `When did we implement git-memory?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `c707021` — 20260407 git-memory: universal decision detection (feat:/fix:/v-version patterns)

### A: BM25-only — ✅ HIT (rank 4)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  | [ ] |
| 2 | `db72e38` | 20260409 bm25-memory: G1+G2 BM25 hook (recall 0.169→0.881) | [ ] |
| 3 | `9e5baa5` | 20260409 PageIndex + BM25 docs eval: G1 long-term memory via | [ ] |

### B: BM25+rerank — ✅ HIT (rank 4)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  | [ ] |
| 2 | `db72e38` | 20260409 bm25-memory: G1+G2 BM25 hook (recall 0.169→0.881) | [ ] |
| 3 | `9e5baa5` | 20260409 PageIndex + BM25 docs eval: G1 long-term memory via | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 2)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  | [ ] |
| 2 | `c707021` | 20260407 git-memory: universal decision detection (feat:/fix ⭐ | [ ] |
| 3 | `db72e38` | 20260409 bm25-memory: G1+G2 BM25 hook (recall 0.169→0.881) | [ ] |

---

## Query 6: `When did we implement G1 temporal eval results?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `acd6096` — 20260407 G1 temporal eval results: Staleness 35.7%, Conflict 0% (4 projects)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

---

## Query 7: `When did we implement G1 temporal eval?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `d8f2de1` — 20260407 G1 temporal eval: Staleness Flag + Conflict Detection implemented

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti ⭐ | [ ] |
| 2 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti ⭐ | [ ] |
| 2 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti ⭐ | [ ] |
| 2 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

---

## Query 8: `When did we implement G2 prefetch benchmark?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `01dd8c0` — 20260405 G2 prefetch benchmark: 30% -> 65% after ko-en mapping + filepath search

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `01dd8c0` | 20260405 G2 prefetch benchmark: 30% -> 65% after ko-en mappi ⭐ | [ ] |
| 2 | `914817d` | CTX iter5: G2 v4 benchmark calibration + SOYA deployment ver | [ ] |
| 3 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `01dd8c0` | 20260405 G2 prefetch benchmark: 30% -> 65% after ko-en mappi ⭐ | [ ] |
| 2 | `914817d` | CTX iter5: G2 v4 benchmark calibration + SOYA deployment ver | [ ] |
| 3 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `01dd8c0` | 20260405 G2 prefetch benchmark: 30% -> 65% after ko-en mappi ⭐ | [ ] |
| 2 | `914817d` | CTX iter5: G2 v4 benchmark calibration + SOYA deployment ver | [ ] |
| 3 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |

---

## Query 9: `When did we implement Old CTX remnants fully removed?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `ebd429f` — 20260405 Old CTX remnants fully removed

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `ebd429f` | 20260405 Old CTX remnants fully removed ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `ebd429f` | 20260405 Old CTX remnants fully removed ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `ebd429f` | 20260405 Old CTX remnants fully removed ⭐ | [ ] |
| 2 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  | [ ] |
| 3 | `62e6db0` | 20260402 2100 CTX repositioned as context bootstrapper + G1/ | [ ] |

---

## Query 10: `When did we implement New CTX?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `a84b91e` — 20260405 New CTX: git-memory + g2-augment + auto-index (old CTX retired)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a84b91e` | 20260405 New CTX: git-memory + g2-augment + auto-index (old  ⭐ | [ ] |
| 2 | `fcdd544` | feat: CTX downstream LLM evaluation framework (G1+G2) | [ ] |
| 3 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |

---

## Query 11: `When did we implement inject_decisions.py?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `e06a15f` — 20260404 inject_decisions.py: git-only mode (no world-model dependency)

### A: BM25-only — ❌ MISS (not retrieved)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `fdd26fc` | eval: g1_fair_eval.py 캐시 레이어 추가 — 반복 실행 분산 제거 | [ ] |

### B: BM25+rerank — ❌ MISS (not retrieved)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `fdd26fc` | eval: g1_fair_eval.py 캐시 레이어 추가 — 반복 실행 분산 제거 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 3)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `e06a15f` | 20260404 inject_decisions.py: git-only mode (no world-model  ⭐ | [ ] |

---

## Query 12: `When did we implement G1 git-log hook test results?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `10519bd` — 20260404 G1 git-log hook test results: 95% recall across 3 projects

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `10519bd` | 20260404 G1 git-log hook test results: 95% recall across 3 p ⭐ | [ ] |
| 2 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `10519bd` | 20260404 G1 git-log hook test results: 95% recall across 3 p ⭐ | [ ] |
| 2 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s | [ ] |
| 3 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `10519bd` | 20260404 G1 git-log hook test results: 95% recall across 3 p ⭐ | [ ] |
| 2 | `acd6096` | 20260407 G1 temporal eval results: Staleness 35.7%, Conflict | [ ] |
| 3 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s | [ ] |

---

## Query 13: `When did we implement inject_decisions.py?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `8a3f0ac` — 20260404 inject_decisions.py: git log primary, world-model secondary

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `fdd26fc` | eval: g1_fair_eval.py 캐시 레이어 추가 — 반복 실행 분산 제거 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `fdd26fc` | eval: g1_fair_eval.py 캐시 레이어 추가 — 반복 실행 분산 제거 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8a3f0ac` | 20260404 inject_decisions.py: git log primary, world-model s ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `e06a15f` | 20260404 inject_decisions.py: git-only mode (no world-model  | [ ] |

---

## Query 14: `When did we implement command hook + additionalContext for SOTA G1 activation?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `66ac725` — 20260403 command hook + additionalContext for SOTA G1 activation

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `66ac725` | 20260403 command hook + additionalContext for SOTA G1 activa ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `66ac725` | 20260403 command hook + additionalContext for SOTA G1 activa ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `66ac725` | 20260403 command hook + additionalContext for SOTA G1 activa ⭐ | [ ] |
| 2 | `9e082f3` | 20260403 SOTA eval complete: G1 recall 90% + G2 complementar | [ ] |
| 3 | `db72e38` | 20260409 bm25-memory: G1+G2 BM25 hook (recall 0.169→0.881) | [ ] |

---

## Query 15: `When did we implement G1/G2 measurement complete — standard benchmarks applied?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `33dba2e` — 20260403 G1/G2 measurement complete — standard benchmarks applied

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap ⭐ | [ ] |
| 2 | `914817d` | CTX iter5: G2 v4 benchmark calibration + SOYA deployment ver | [ ] |
| 3 | `a989d84` | 20260403 G1/G2 definition clarified in CLAUDE.md | [ ] |

---

## Query 16: `When did we implement COIR full corpus?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `ef4c7ef` — 20260403 COIR full corpus: BM25 Hit@5=0.640 on 280K docs

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `ef4c7ef` | 20260403 COIR full corpus: BM25 Hit@5=0.640 on 280K docs ⭐ | [ ] |
| 2 | `9279b56` | 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSe | [ ] |
| 3 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `ef4c7ef` | 20260403 COIR full corpus: BM25 Hit@5=0.640 on 280K docs ⭐ | [ ] |
| 2 | `9279b56` | 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSe | [ ] |
| 3 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `ef4c7ef` | 20260403 COIR full corpus: BM25 Hit@5=0.640 on 280K docs ⭐ | [ ] |
| 2 | `9279b56` | 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSe | [ ] |
| 3 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c | [ ] |

---

## Query 17: `When did we implement COIR standard benchmark?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `9279b56` — 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSearchNet Python (24.9K corpus)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `9279b56` | 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSe ⭐ | [ ] |
| 2 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |
| 3 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `9279b56` | 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSe ⭐ | [ ] |
| 2 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |
| 3 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `9279b56` | 20260403 COIR standard benchmark: BM25 Hit@5=0.780 on CodeSe ⭐ | [ ] |
| 2 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |
| 3 | `b043d0e` | feat: before/after benchmark + hook improvement report | [ ] |

---

## Query 18: `When did we implement SOTA eval complete?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `9e082f3` — 20260403 SOTA eval complete: G1 recall 90% + G2 complementary analysis

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `9e082f3` | 20260403 SOTA eval complete: G1 recall 90% + G2 complementar ⭐ | [ ] |
| 2 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |
| 3 | `83e54f3` | live-inf state update: iter4 complete — G1 0.746, synonym+te | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `9e082f3` | 20260403 SOTA eval complete: G1 recall 90% + G2 complementar ⭐ | [ ] |
| 2 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |
| 3 | `83e54f3` | live-inf state update: iter4 complete — G1 0.746, synonym+te | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `9e082f3` | 20260403 SOTA eval complete: G1 recall 90% + G2 complementar ⭐ | [ ] |
| 2 | `33a992a` | 20260409 G1 long-term memory: full eval + SOTA comparison (7 | [ ] |
| 3 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |

---

## Query 19: `When did we implement G1/G2 definition clarified in CLAUDE.md?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `a989d84` — 20260403 G1/G2 definition clarified in CLAUDE.md

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a989d84` | 20260403 G1/G2 definition clarified in CLAUDE.md ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a989d84` | 20260403 G1/G2 definition clarified in CLAUDE.md ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `a989d84` | 20260403 G1/G2 definition clarified in CLAUDE.md ⭐ | [ ] |
| 2 | `33dba2e` | 20260403 G1/G2 measurement complete — standard benchmarks ap | [ ] |
| 3 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev | [ ] |

---

## Query 20: `When did we implement live-inf CONVERGED?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `4db7a3c` — 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrough achieved

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou ⭐ | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at | [ ] |
| 3 | `eddf068` | live-infinite iter 76/∞: CONVERGED | goal_v2: CTX 논문 Referen | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou ⭐ | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at | [ ] |
| 3 | `eddf068` | live-infinite iter 76/∞: CONVERGED | goal_v2: CTX 논문 Referen | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou ⭐ | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at | [ ] |
| 3 | `eddf068` | live-infinite iter 76/∞: CONVERGED | goal_v2: CTX 논문 Referen | [ ] |

---

## Query 21: `When did we implement live-inf iter 4/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `783ac1a` — 20260403 live-inf iter 4/∞: IMPLICIT_CONTEXT exempted from doc filtering

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `783ac1a` | 20260403 live-inf iter 4/∞: IMPLICIT_CONTEXT exempted from d ⭐ | [ ] |
| 2 | `0e8d284` | live-infinite iter 4/∞: 미커밋 파일 정리 커밋 | [ ] |
| 3 | `cff8db5` | live-infinite iter 4/∞: sig_only eval + 연구 문서 업데이트 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `783ac1a` | 20260403 live-inf iter 4/∞: IMPLICIT_CONTEXT exempted from d ⭐ | [ ] |
| 2 | `0e8d284` | live-infinite iter 4/∞: 미커밋 파일 정리 커밋 | [ ] |
| 3 | `cff8db5` | live-infinite iter 4/∞: sig_only eval + 연구 문서 업데이트 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 5)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `cff8db5` | live-infinite iter 4/∞: sig_only eval + 연구 문서 업데이트 | [ ] |
| 2 | `d012467` | live-infinite iter 4/∞: external R@5 0.5406→0.5623 | bigram  | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

---

## Query 22: `When did we implement live-inf iter 2/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `90cf49a` — 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 structural BM25 limits

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st ⭐ | [ ] |
| 2 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio | [ ] |
| 3 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st ⭐ | [ ] |
| 2 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio | [ ] |
| 3 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 3)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  | [ ] |
| 2 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |
| 3 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st ⭐ | [ ] |

---

## Query 23: `When did we implement live-inf iter 1/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `f6c9bd8` — 20260403 live-inf iter 1/∞: G1 BREAKTHROUGH — trigger→surfacing eval + doc-fallback fix

### A: BM25-only — ❌ MISS (not retrieved)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

### B: BM25+rerank — ❌ MISS (not retrieved)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

### C: Hybrid-RRF — ❌ MISS (not retrieved)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev | [ ] |
| 2 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |
| 3 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |

---

## Query 24: `When did we implement live-inf CONVERGED?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `dd7f602` — 20260403 live-inf CONVERGED: plateau 7 iterations, escape attempts exhausted

### A: BM25-only — ✅ HIT (rank 2)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at ⭐ | [ ] |
| 3 | `eddf068` | live-infinite iter 76/∞: CONVERGED | goal_v2: CTX 논문 Referen | [ ] |

### B: BM25+rerank — ✅ HIT (rank 2)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at ⭐ | [ ] |
| 3 | `eddf068` | live-infinite iter 76/∞: CONVERGED | goal_v2: CTX 논문 Referen | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 2)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at ⭐ | [ ] |
| 3 | `eddf068` | live-infinite iter 76/∞: CONVERGED | goal_v2: CTX 논문 Referen | [ ] |

---

## Query 25: `When did we implement live-inf iter 8/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `429f257` — 20260403 live-inf iter 8/∞: G1 3-run average stabilized — delta=+0.270 (±0.074)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `429f257` | 20260403 live-inf iter 8/∞: G1 3-run average stabilized — de ⭐ | [ ] |
| 2 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun | [ ] |
| 3 | `b4605f3` | live-infinite iter 8/∞: README Key Findings — add external c | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `429f257` | 20260403 live-inf iter 8/∞: G1 3-run average stabilized — de ⭐ | [ ] |
| 2 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun | [ ] |
| 3 | `b4605f3` | live-infinite iter 8/∞: README Key Findings — add external c | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 2)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b4605f3` | live-infinite iter 8/∞: README Key Findings — add external c | [ ] |
| 2 | `429f257` | 20260403 live-inf iter 8/∞: G1 3-run average stabilized — de ⭐ | [ ] |
| 3 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |

---

## Query 26: `When did we implement live-inf iter 7/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `839f26f` — 20260403 live-inf iter 7/∞: H03 ctx_query improved + History 0.55→0.661

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History ⭐ | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at | [ ] |
| 3 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History ⭐ | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at | [ ] |
| 3 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History ⭐ | [ ] |
| 2 | `dd7f602` | 20260403 live-inf CONVERGED: plateau 7 iterations, escape at | [ ] |
| 3 | `c0bc6b3` | live-infinite iter 7/∞: success | README — external codebase | [ ] |

---

## Query 27: `When did we implement live-inf iter 6/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `c6950b7` — 20260403 live-inf iter 6/∞: docs fully separated from BM25 corpus + file_paths

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c ⭐ | [ ] |
| 2 | `d503220` | 20260402 1130 live-infinite iter 6/∞: import_alias_map for I | [ ] |
| 3 | `71156c1` | live-infinite iter 6/∞: fix paper Limitations — clarify BM25 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c ⭐ | [ ] |
| 2 | `d503220` | 20260402 1130 live-infinite iter 6/∞: import_alias_map for I | [ ] |
| 3 | `71156c1` | live-infinite iter 6/∞: fix paper Limitations — clarify BM25 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c ⭐ | [ ] |
| 2 | `71156c1` | live-infinite iter 6/∞: fix paper Limitations — clarify BM25 | [ ] |
| 3 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |

---

## Query 28: `When did we implement live-inf iter 5/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `85ccac0` — 20260403 live-inf iter 5/∞: docs excluded from BM25 corpus + compact summary reverted

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `85ccac0` | 20260403 live-inf iter 5/∞: docs excluded from BM25 corpus + ⭐ | [ ] |
| 2 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |
| 3 | `783ac1a` | 20260403 live-inf iter 4/∞: IMPLICIT_CONTEXT exempted from d | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `85ccac0` | 20260403 live-inf iter 5/∞: docs excluded from BM25 corpus + ⭐ | [ ] |
| 2 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |
| 3 | `783ac1a` | 20260403 live-inf iter 4/∞: IMPLICIT_CONTEXT exempted from d | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `85ccac0` | 20260403 live-inf iter 5/∞: docs excluded from BM25 corpus + ⭐ | [ ] |
| 2 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |
| 3 | `8ff9bfe` | live-infinite iter 5/∞: success | goal_v0: external R@5 0.56 | [ ] |

---

## Query 29: `When did we implement 2100 CTX repositioned as context bootstrapper + G1/G2?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `62e6db0` — 20260402 2100 CTX repositioned as context bootstrapper + G1/G2 redefined

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `62e6db0` | 20260402 2100 CTX repositioned as context bootstrapper + G1/ ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `62e6db0` | 20260402 2100 CTX repositioned as context bootstrapper + G1/ ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `62e6db0` | 20260402 2100 CTX repositioned as context bootstrapper + G1/ ⭐ | [ ] |
| 2 | `fcdd544` | feat: CTX downstream LLM evaluation framework (G1+G2) | [ ] |
| 3 | `914817d` | CTX iter5: G2 v4 benchmark calibration + SOYA deployment ver | [ ] |

---

## Query 30: `When did we implement 2040 live iter 2/5?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `1e84ef9` — 20260402 2040 live iter 2/5: hybrid scoring (50% judge + 50% keyword) — CTX vs None delta=+0.300

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1e84ef9` | 20260402 2040 live iter 2/5: hybrid scoring (50% judge + 50% ⭐ | [ ] |
| 2 | `acbe485` | live-infinite iter 61/∞: success | goal_v3: Section 2.1 — Me | [ ] |
| 3 | `b4067e0` | live-infinite iter 2/∞: P3 README 배지 추가 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1e84ef9` | 20260402 2040 live iter 2/5: hybrid scoring (50% judge + 50% ⭐ | [ ] |
| 2 | `acbe485` | live-infinite iter 61/∞: success | goal_v3: Section 2.1 — Me | [ ] |
| 3 | `b4067e0` | live-infinite iter 2/∞: P3 README 배지 추가 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1e84ef9` | 20260402 2040 live iter 2/5: hybrid scoring (50% judge + 50% ⭐ | [ ] |
| 2 | `1c3bdf4` | 20260402 2030 live iter 1/5: ctx_query optimization + key do | [ ] |
| 3 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio | [ ] |

---

## Query 31: `When did we implement 2030 live iter 1/5?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `1c3bdf4` — 20260402 2030 live iter 1/5: ctx_query optimization + key doc boost (README/CLAUDE +1.0)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1c3bdf4` | 20260402 2030 live iter 1/5: ctx_query optimization + key do ⭐ | [ ] |
| 2 | `517a21d` | live iter 1/5: hook 아키텍처 시간/공간 기억 상한선 실증 측정 완료 | [ ] |
| 3 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1c3bdf4` | 20260402 2030 live iter 1/5: ctx_query optimization + key do ⭐ | [ ] |
| 2 | `517a21d` | live iter 1/5: hook 아키텍처 시간/공간 기억 상한선 실증 측정 완료 | [ ] |
| 3 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1c3bdf4` | 20260402 2030 live iter 1/5: ctx_query optimization + key do ⭐ | [ ] |
| 2 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev | [ ] |
| 3 | `f02c5b7` | live-infinite iter 3/∞: external R@5 0.5259→0.5406 | goal_v0 | [ ] |

---

## Query 32: `When did we implement 2015 live-inf?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `471065f` — 20260402 2015 live-inf: save state for next session

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `471065f` | 20260402 2015 live-inf: save state for next session ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `471065f` | 20260402 2015 live-inf: save state for next session ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `471065f` | 20260402 2015 live-inf: save state for next session ⭐ | [ ] |
| 2 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |
| 3 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev | [ ] |

---

## Query 33: `When did we implement 2010 live-inf iter 2/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `453ce8f` — 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-priority boost for high-level queries

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio ⭐ | [ ] |
| 2 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |
| 3 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio ⭐ | [ ] |
| 2 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |
| 3 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio ⭐ | [ ] |
| 2 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |
| 3 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |

---

## Query 34: `When did we implement 1935 live-inf?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `0afe878` — 20260402 1935 live-inf: save state for context rotation

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `0afe878` | 20260402 1935 live-inf: save state for context rotation ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `0afe878` | 20260402 1935 live-inf: save state for context rotation ⭐ | [ ] |
| 2 | `d8f2de1` | 20260407 G1 temporal eval: Staleness Flag + Conflict Detecti | [ ] |
| 3 | `b2a9bf3` | 20260408 G1 temporal retention: age-based recall decay curve | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `0afe878` | 20260402 1935 live-inf: save state for context rotation ⭐ | [ ] |
| 2 | `4db7a3c` | 20260403 live-inf CONVERGED: G1 trigger→surfacing breakthrou | [ ] |
| 3 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |

---

## Query 35: `When did we implement 1930 live-inf iter 1/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `22f3137` — 20260402 1930 live-inf iter 1/∞: G1 eval rebuilt — LLM-as-judge + 3-arm + random baseline

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `22f3137` | 20260402 1930 live-inf iter 1/∞: G1 eval rebuilt — LLM-as-ju ⭐ | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `22f3137` | 20260402 1930 live-inf iter 1/∞: G1 eval rebuilt — LLM-as-ju ⭐ | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `22f3137` | 20260402 1930 live-inf iter 1/∞: G1 eval rebuilt — LLM-as-ju ⭐ | [ ] |
| 2 | `a54c6e0` | live-infinite iter 1/∞: success | goal_v0: trigger classifie | [ ] |
| 3 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |

---

## Query 36: `When did we implement 1900 live-inf iter 3/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `e9b9096` — 20260402 1900 live-inf iter 3/∞: G1=0.705 achieved | target 0.70 reached

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `e9b9096` | 20260402 1900 live-inf iter 3/∞: G1=0.705 achieved | target  ⭐ | [ ] |
| 2 | `e438578` | live-infinite iter 3/∞: BM25 stem 강화 실험 (neutral) | [ ] |
| 3 | `080047e` | live-infinite iter 3/∞: P4 교차 파일 추론 강화 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `e9b9096` | 20260402 1900 live-inf iter 3/∞: G1=0.705 achieved | target  ⭐ | [ ] |
| 2 | `e438578` | live-infinite iter 3/∞: BM25 stem 강화 실험 (neutral) | [ ] |
| 3 | `080047e` | live-infinite iter 3/∞: P4 교차 파일 추론 강화 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `e9b9096` | 20260402 1900 live-inf iter 3/∞: G1=0.705 achieved | target  ⭐ | [ ] |
| 2 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |
| 3 | `f02c5b7` | live-infinite iter 3/∞: external R@5 0.5259→0.5406 | goal_v0 | [ ] |

---

## Query 37: `When did we implement 1850 live-inf iter 2/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `bc80c5e` — 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated questions, language-independent keywords

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  ⭐ | [ ] |
| 2 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |
| 3 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  ⭐ | [ ] |
| 2 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |
| 3 | `453ce8f` | 20260402 2010 live-inf iter 2/∞: .md doc indexing + doc-prio | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `bc80c5e` | 20260402 1850 live-inf iter 2/∞: G1 eval redesign — curated  ⭐ | [ ] |
| 2 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |
| 3 | `90cf49a` | 20260403 live-inf iter 2/∞: miss analysis complete — 7/30 st | [ ] |

---

## Query 38: `When did we implement 1820 live-inf iter 1/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `5ff6f22` — 20260402 1820 live-inf iter 1/∞: G1 project-understanding eval framework

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev ⭐ | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev ⭐ | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `a13e563` | live-inf USER_STOPPED state written (14 iters) | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ff6f22` | 20260402 1820 live-inf iter 1/∞: G1 project-understanding ev ⭐ | [ ] |
| 2 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |
| 3 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |

---

## Query 39: `When did we implement 1805 omc-live iter 2?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `4de1872` — 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tuned (8+ chars only)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun ⭐ | [ ] |
| 2 | `6651697` | 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCa | [ ] |
| 3 | `b4067e0` | live-infinite iter 2/∞: P3 README 배지 추가 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun ⭐ | [ ] |
| 2 | `6651697` | 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCa | [ ] |
| 3 | `b4067e0` | live-infinite iter 2/∞: P3 README 배지 추가 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun ⭐ | [ ] |
| 2 | `6651697` | 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCa | [ ] |
| 3 | `521264a` | omc: update world model — iters 39-40 improved impact (0.985 | [ ] |

---

## Query 40: `When did we implement 1800 omc-live iter 1?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `6651697` — 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCase after function/class keyword

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `6651697` | 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCa ⭐ | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `6651697` | 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCa ⭐ | [ ] |
| 2 | `646936c` | live-infinite iter 1/∞: P1 실용 임팩트 완료 | [ ] |
| 3 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `6651697` | 20260402 1800 omc-live iter 1: SYMBOL_PATTERN fix — PascalCa ⭐ | [ ] |
| 2 | `4de1872` | 20260402 1805 omc-live iter 2: PascalCase SYMBOL_PATTERN tun | [ ] |
| 3 | `521264a` | omc: update world model — iters 39-40 improved impact (0.985 | [ ] |

---

## Query 41: `When did we implement 1745 live-infinite iter 13/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `f05c215` — 20260402 1745 live-infinite iter 13/∞: G1 zero-storage analysis — concept group R@5=0.965

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f05c215` | 20260402 1745 live-infinite iter 13/∞: G1 zero-storage analy ⭐ | [ ] |
| 2 | `050cf81` | live-infinite iter 13/∞: fix paper abstract — synthetic 600  | [ ] |
| 3 | `41be972` | live-infinite iter 5/∞: success | goal_v3: paper References  | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f05c215` | 20260402 1745 live-infinite iter 13/∞: G1 zero-storage analy ⭐ | [ ] |
| 2 | `050cf81` | live-infinite iter 13/∞: fix paper abstract — synthetic 600  | [ ] |
| 3 | `41be972` | live-infinite iter 5/∞: success | goal_v3: paper References  | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f05c215` | 20260402 1745 live-infinite iter 13/∞: G1 zero-storage analy ⭐ | [ ] |
| 2 | `050cf81` | live-infinite iter 13/∞: fix paper abstract — synthetic 600  | [ ] |
| 3 | `71fd115` | live-infinite iter 15/∞: docs — final ASCII→BM25 in trigger  | [ ] |

---

## Query 42: `When did we implement 1730 live-infinite iter 12/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `8f658a2` — 20260402 1730 live-infinite iter 12/∞: G1 redefined — zero-storage instant retrieval

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8f658a2` | 20260402 1730 live-infinite iter 12/∞: G1 redefined — zero-s ⭐ | [ ] |
| 2 | `79f5bf9` | live-infinite iter 12/∞: paper — author Jeawon Jang + clean  | [ ] |
| 3 | `0e8d284` | live-infinite iter 4/∞: 미커밋 파일 정리 커밋 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8f658a2` | 20260402 1730 live-infinite iter 12/∞: G1 redefined — zero-s ⭐ | [ ] |
| 2 | `79f5bf9` | live-infinite iter 12/∞: paper — author Jeawon Jang + clean  | [ ] |
| 3 | `0e8d284` | live-infinite iter 4/∞: 미커밋 파일 정리 커밋 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `8f658a2` | 20260402 1730 live-infinite iter 12/∞: G1 redefined — zero-s ⭐ | [ ] |
| 2 | `3b1ac9a` | 20260402 1530 live-infinite iter 10/∞: checkpoint uncommitte | [ ] |
| 3 | `71fd115` | live-infinite iter 15/∞: docs — final ASCII→BM25 in trigger  | [ ] |

---

## Query 43: `When did we implement 1717 live-infinite iter 11/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `5ba6a7c` — 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, temporal noise reduction, BM25 large-repo boost

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ba6a7c` | 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, ⭐ | [ ] |
| 2 | `f55dda7` | live-infinite iter 11/∞: docs — update integration guide ASC | [ ] |
| 3 | `517a21d` | live iter 1/5: hook 아키텍처 시간/공간 기억 상한선 실증 측정 완료 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ba6a7c` | 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, ⭐ | [ ] |
| 2 | `f55dda7` | live-infinite iter 11/∞: docs — update integration guide ASC | [ ] |
| 3 | `517a21d` | live iter 1/5: hook 아키텍처 시간/공간 기억 상한선 실증 측정 완료 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5ba6a7c` | 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, ⭐ | [ ] |
| 2 | `f55dda7` | live-infinite iter 11/∞: docs — update integration guide ASC | [ ] |
| 3 | `cff8db5` | live-infinite iter 4/∞: sig_only eval + 연구 문서 업데이트 | [ ] |

---

## Query 44: `When did we implement 1530 live-infinite iter 10/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `3b1ac9a` — 20260402 1530 live-infinite iter 10/∞: checkpoint uncommitted changes from iter 6-10

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `3b1ac9a` | 20260402 1530 live-infinite iter 10/∞: checkpoint uncommitte ⭐ | [ ] |
| 2 | `cdf0820` | live-infinite iter 10/∞: README intro — add external codebas | [ ] |
| 3 | `5ba6a7c` | 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `3b1ac9a` | 20260402 1530 live-infinite iter 10/∞: checkpoint uncommitte ⭐ | [ ] |
| 2 | `cdf0820` | live-infinite iter 10/∞: README intro — add external codebas | [ ] |
| 3 | `5ba6a7c` | 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `3b1ac9a` | 20260402 1530 live-infinite iter 10/∞: checkpoint uncommitte ⭐ | [ ] |
| 2 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |
| 3 | `5ba6a7c` | 20260402 1717 live-infinite iter 11/∞: reverse_import 10→30, | [ ] |

---

## Query 45: `When did we implement 1130 live-infinite iter 6/∞?`
- **Type**: type1 | **Age**: 0-7d
- **Gold commit**: `d503220` — 20260402 1130 live-infinite iter 6/∞: import_alias_map for IMPLICIT_CONTEXT depth + alias traversal

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `d503220` | 20260402 1130 live-infinite iter 6/∞: import_alias_map for I ⭐ | [ ] |
| 2 | `71156c1` | live-infinite iter 6/∞: fix paper Limitations — clarify BM25 | [ ] |
| 3 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `d503220` | 20260402 1130 live-infinite iter 6/∞: import_alias_map for I ⭐ | [ ] |
| 2 | `71156c1` | live-infinite iter 6/∞: fix paper Limitations — clarify BM25 | [ ] |
| 3 | `c6950b7` | 20260403 live-inf iter 6/∞: docs fully separated from BM25 c | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `d503220` | 20260402 1130 live-infinite iter 6/∞: import_alias_map for I ⭐ | [ ] |
| 2 | `71156c1` | live-infinite iter 6/∞: fix paper Limitations — clarify BM25 | [ ] |
| 3 | `22668ca` | live-infinite iter 1/∞: COIR R@5 0.740→1.000, RepoBench 0.55 | [ ] |

---

## Query 46: `When did we implement SEMANTIC_CONCEPT R@5 0.500→0.867 on COIR — two fixes?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `2051a11` — perf: SEMANTIC_CONCEPT R@5 0.500→0.867 on COIR — two fixes

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `2051a11` | perf: SEMANTIC_CONCEPT R@5 0.500→0.867 on COIR — two fixes ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `2051a11` | perf: SEMANTIC_CONCEPT R@5 0.500→0.867 on COIR — two fixes ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `2051a11` | perf: SEMANTIC_CONCEPT R@5 0.500→0.867 on COIR — two fixes ⭐ | [ ] |
| 2 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  | [ ] |
| 3 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 | [ ] |

---

## Query 47: `When did we implement HF Space deployed + PyPI package validated?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `1335244` — feat: HF Space deployed + PyPI package validated

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1335244` | feat: HF Space deployed + PyPI package validated ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1335244` | feat: HF Space deployed + PyPI package validated ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `1335244` | feat: HF Space deployed + PyPI package validated ⭐ | [ ] |
| 2 | `f8dd028` | feat: distribution prep — pyproject.toml + README + HF Space | [ ] |
| 3 | `7ef1bc8` | Add HF Space and tier evaluation research | [ ] |

---

## Query 48: `When did we implement CONTRIBUTING.md + PyPI publish script + build fix?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `462d7a9` — feat: CONTRIBUTING.md + PyPI publish script + build fix

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `462d7a9` | feat: CONTRIBUTING.md + PyPI publish script + build fix ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `462d7a9` | feat: CONTRIBUTING.md + PyPI publish script + build fix ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `462d7a9` | feat: CONTRIBUTING.md + PyPI publish script + build fix ⭐ | [ ] |
| 2 | `1335244` | feat: HF Space deployed + PyPI package validated | [ ] |
| 3 | `ffda682` | live-infinite iter 70/∞: success | goal_v3: Conclusion IMPLI | [ ] |

---

## Query 49: `When did we implement distribution prep — pyproject.toml + README + HF?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `f8dd028` — feat: distribution prep — pyproject.toml + README + HF Space + hooks/

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f8dd028` | feat: distribution prep — pyproject.toml + README + HF Space ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f8dd028` | feat: distribution prep — pyproject.toml + README + HF Space ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f8dd028` | feat: distribution prep — pyproject.toml + README + HF Space ⭐ | [ ] |
| 2 | `1335244` | feat: HF Space deployed + PyPI package validated | [ ] |
| 3 | `462d7a9` | feat: CONTRIBUTING.md + PyPI publish script + build fix | [ ] |

---

## Query 50: `When did we implement before/after benchmark + hook improvement report?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `b043d0e` — feat: before/after benchmark + hook improvement report

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b043d0e` | feat: before/after benchmark + hook improvement report ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b043d0e` | feat: before/after benchmark + hook improvement report ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `b043d0e` | feat: before/after benchmark + hook improvement report ⭐ | [ ] |
| 2 | `ad93926` | Add CTX Hook effectiveness evaluation (CHR=70%, RT=117ms) | [ ] |
| 3 | `c4b8536` | feat(hook): anti-anchoring guidance for Fix/Replace tasks | [ ] |

---

## Query 51: `When did we implement classify_intent 한국어 명사 오탐(FP) 수정 — regex 동사어미?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `523be3e` — fix: classify_intent 한국어 명사 오탐(FP) 수정 — regex 동사어미 앵커링

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `523be3e` | fix: classify_intent 한국어 명사 오탐(FP) 수정 — regex 동사어미 앵커링 ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `523be3e` | fix: classify_intent 한국어 명사 오탐(FP) 수정 — regex 동사어미 앵커링 ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `523be3e` | fix: classify_intent 한국어 명사 오탐(FP) 수정 — regex 동사어미 앵커링 ⭐ | [ ] |
| 2 | `770cb4e` | feat: TriggerClassifier.classify_intent 한국어 modify/create 키워 | [ ] |
| 3 | `74b2dbc` | test: TriggerClassifier 한국어 intent 분류 단위 테스트 33개 추가 | [ ] |

---

## Query 52: `When did we implement TriggerClassifier.classify_intent 한국어 modify/create 키워드 추가?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `770cb4e` — feat: TriggerClassifier.classify_intent 한국어 modify/create 키워드 추가

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `770cb4e` | feat: TriggerClassifier.classify_intent 한국어 modify/create 키워 ⭐ | [ ] |
| 2 | `74b2dbc` | test: TriggerClassifier 한국어 intent 분류 단위 테스트 33개 추가 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `770cb4e` | feat: TriggerClassifier.classify_intent 한국어 modify/create 키워 ⭐ | [ ] |
| 2 | `74b2dbc` | test: TriggerClassifier 한국어 intent 분류 단위 테스트 33개 추가 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `770cb4e` | feat: TriggerClassifier.classify_intent 한국어 modify/create 키워 ⭐ | [ ] |
| 2 | `74b2dbc` | test: TriggerClassifier 한국어 intent 분류 단위 테스트 33개 추가 | [ ] |
| 3 | `ceefd94` | live-infinite iter 2/∞: success | goal_v1: 논문+README trigger | [ ] |

---

## Query 53: `When did we implement update paper draft (v4.0 P10) with external R@5=0.495,?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `3d8f2f1` — feat: update paper draft (v4.0 P10) with external R@5=0.495, G1/G2 eval, bootstrap CI

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `3d8f2f1` | feat: update paper draft (v4.0 P10) with external R@5=0.495, ⭐ | [ ] |
| 2 | `bf857f8` | CTX iter4: BM25 baseline comparison + paper draft v4.0 P10 u | [ ] |
| 3 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `3d8f2f1` | feat: update paper draft (v4.0 P10) with external R@5=0.495, ⭐ | [ ] |
| 2 | `bf857f8` | CTX iter4: BM25 baseline comparison + paper draft v4.0 P10 u | [ ] |
| 3 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `3d8f2f1` | feat: update paper draft (v4.0 P10) with external R@5=0.495, ⭐ | [ ] |
| 2 | `bf857f8` | CTX iter4: BM25 baseline comparison + paper draft v4.0 P10 u | [ ] |
| 3 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  | [ ] |

---

## Query 54: `When did we implement fix SEMANTIC trigger misclassification — external R@5...?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `727b5c3` — feat: fix SEMANTIC trigger misclassification — external R@5 0.217→0.495 (+128%)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  ⭐ | [ ] |
| 2 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  ⭐ | [ ] |
| 2 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  ⭐ | [ ] |
| 2 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 | [ ] |
| 3 | `2051a11` | perf: SEMANTIC_CONCEPT R@5 0.500→0.867 on COIR — two fixes | [ ] |

---

## Query 55: `When did we implement fix external codebase generalization — IMPLICIT R@5 +350%?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `720380f` — feat: fix external codebase generalization — IMPLICIT R@5 +350% avg

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `720380f` | feat: fix external codebase generalization — IMPLICIT R@5 +3 ⭐ | [ ] |
| 2 | `727b5c3` | feat: fix SEMANTIC trigger misclassification — external R@5  | [ ] |
| 3 | `8ff9bfe` | live-infinite iter 5/∞: success | goal_v0: external R@5 0.56 | [ ] |

---

## Query 56: `When did we implement CTX downstream LLM evaluation framework (G1+G2)?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `fcdd544` — feat: CTX downstream LLM evaluation framework (G1+G2)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `fcdd544` | feat: CTX downstream LLM evaluation framework (G1+G2) ⭐ | [ ] |
| 2 | `ad93926` | Add CTX Hook effectiveness evaluation (CHR=70%, RT=117ms) | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `fcdd544` | feat: CTX downstream LLM evaluation framework (G1+G2) ⭐ | [ ] |
| 2 | `ad93926` | Add CTX Hook effectiveness evaluation (CHR=70%, RT=117ms) | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `fcdd544` | feat: CTX downstream LLM evaluation framework (G1+G2) ⭐ | [ ] |
| 2 | `ad93926` | Add CTX Hook effectiveness evaluation (CHR=70%, RT=117ms) | [ ] |
| 3 | `dbcd692` | docs: CTX downstream LLM eval report + DOC_INDEX 업데이트 | [ ] |

---

## Query 57: `When did we implement CTX-doc keyword R@3 ≥ 0.724 달성 — query_type-aware?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `f42a22b` — feat: CTX-doc keyword R@3 ≥ 0.724 달성 — query_type-aware routing

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f42a22b` | feat: CTX-doc keyword R@3 ≥ 0.724 달성 — query_type-aware rout ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f42a22b` | feat: CTX-doc keyword R@3 ≥ 0.724 달성 — query_type-aware rout ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `f42a22b` | feat: CTX-doc keyword R@3 ≥ 0.724 달성 — query_type-aware rout ⭐ | [ ] |
| 2 | `839f26f` | 20260403 live-inf iter 7/∞: H03 ctx_query improved + History | [ ] |
| 3 | `cec60c0` | live-infinite iter 58/∞: success | goal_v3: Section 5.7 — CT | [ ] |

---

## Query 58: `When did we implement restore optimal BM25 blend ratio in rank_ctx_doc (norm*0.9)?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `7d1a6a8` — refactor: restore optimal BM25 blend ratio in rank_ctx_doc (norm*0.9)

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `7d1a6a8` | refactor: restore optimal BM25 blend ratio in rank_ctx_doc ( ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `7d1a6a8` | refactor: restore optimal BM25 blend ratio in rank_ctx_doc ( ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `7d1a6a8` | refactor: restore optimal BM25 blend ratio in rank_ctx_doc ( ⭐ | [ ] |
| 2 | `85ccac0` | 20260403 live-inf iter 5/∞: docs excluded from BM25 corpus + | [ ] |
| 3 | `db72e38` | 20260409 bm25-memory: G1+G2 BM25 hook (recall 0.169→0.881) | [ ] |

---

## Query 59: `When did we implement replace TF-IDF with BM25 in AdaptiveTriggerRetriever and doc?`
- **Type**: type1 | **Age**: 7-30d
- **Gold commit**: `5099f32` — feat: replace TF-IDF with BM25 in AdaptiveTriggerRetriever and doc benchmark

### A: BM25-only — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5099f32` | feat: replace TF-IDF with BM25 in AdaptiveTriggerRetriever a ⭐ | [ ] |

### B: BM25+rerank — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5099f32` | feat: replace TF-IDF with BM25 in AdaptiveTriggerRetriever a ⭐ | [ ] |

### C: Hybrid-RRF — ✅ HIT (rank 1)
| # | Hash | Subject | Your rating |
|---|------|---------|-------------|
| 1 | `5099f32` | feat: replace TF-IDF with BM25 in AdaptiveTriggerRetriever a ⭐ | [ ] |
| 2 | `71fd115` | live-infinite iter 15/∞: docs — final ASCII→BM25 in trigger  | [ ] |
| 3 | `f55dda7` | live-infinite iter 11/∞: docs — update integration guide ASC | [ ] |

---


## Summary

Queries with differences: 59 / 59
