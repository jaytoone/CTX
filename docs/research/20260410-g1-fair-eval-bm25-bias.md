# G1 Fair Eval — BM25 Structural Bias Measurement

**Date**: 2026-04-09
**Script**: `benchmarks/eval/g1_fair_eval.py`
**Goal**: Quantify how much BM25 Structural Recall@7=1.000 is inflated by query-GT token overlap

---

## Key Finding: BM25 Structural Bias = 0.373

| Eval Type | Recall@7 | Avg Token Overlap | Count |
|-----------|----------|-------------------|-------|
| Type1 Original ("When did we implement X?") | **1.000** | 0.476 | 59 pairs |
| Type1 Paraphrase (keywords removed) | **0.627** | 0.085 | 59 pairs |
| Type2/3/4 (why/what/rationale) | **0.667** | 0.038 | 12 queries |
| **Combined Fair** | **0.634** | — | 71 queries |

**BM25 Structural Bias: 0.373**
- The previously claimed Structural Recall@7=1.000 overstates BM25's real capability by 0.373
- After removing keyword overlap, fair Recall@7 = **0.627~0.634**

---

## Methodology

### Type1 Paraphrase Generation
- 59 original queries ("When did we implement X?") contain exact topic keywords
- Average Jaccard token overlap between query and GT commit subject: **0.476** (high)
- Paraphrased via MiniMax M2.5 in batches of 10
- Paraphrase removes main technical keywords, uses descriptions/synonyms
- Average overlap after paraphrase: **0.085** (low)

### Token Overlap Measurement
Jaccard similarity after removing stop words from query and GT subject:
- Stop words include: implement, add, when, did, we, the, a, ...
- Example:
  - Original: "When did we implement G1 temporal retention?" | GT: "20260408 G1 temporal retention: age-based..."
  - Overlap: {G1, temporal, retention} = 3/7 = 0.429
  - Paraphrase: "When was the time-based recall analysis added to G1?"
  - Overlap: {G1} = 1/6 = 0.167

### Type2/3/4 Query Generation
- 20 commits with meaningful body text selected (step sampling from 58 eligible)
- LLM generated: Type2 (why), Type3 (what findings), Type4 (rationale)
- 12/20 successfully generated (4 parse failures skipped)
- Average overlap: **0.038** — near-zero, no keyword leakage

---

## Paraphrase Examples

### Successful retrievals (in_top7=True after paraphrase)
```
Original: "When did we implement restore optimal BM25 blend ratio in rank_ctx_doc (norm*0.9)?"
Paraphrase: "When was the ranking normalization factor restored to its optimal value?"
Overlap: 0.476 → 0.071 | in_top7: True ✓
```

### Failed retrievals (in_top7=False after paraphrase)
```
Original: "When did we implement G1 noise filter + topic-dedup?"
Paraphrase: "When was the filtering and deduplication for G1 data added?"
GT rank: 18 (missed top-7) — BM25 returned unrelated commits higher
```

---

## Type2/3/4 Results

| Type | Example Query | Result |
|------|--------------|--------|
| type2 (why) | "Why was age=15 identified as the cleanest signal?" | ✓ rank 1 |
| type2 (why) | "What motivated the G1/G2 distinction clarification?" | ✓ rank 4 |
| type3 (what) | "What research gaps were identified in this analysis?" | ✓ rank 5 |
| type3 (what) | "What performance gains from PascalCase tuning?" | ✓ rank 6 |
| type4 (rationale) | "What drove the BM25 fallback decision?" | ✓ rank 3 |
| type3 (what) | "How well did different recall approaches perform?" | ✗ rank 20 |

**Type2/3/4 Recall@7: 0.667** (8/12) — better than expected, but harder than Type1

---

## Corrected Performance Claims

| Metric | Previously Claimed | Fair Value |
|--------|-------------------|------------|
| G1 Structural Recall@7 (Type1) | **1.000** | **0.627** (paraphrase) |
| G1 Structural Recall@7 (fair, all types) | (not measured) | **0.634** (71 queries) |
| BM25 Structural Bias | (unknown) | **0.373** |

The 0.881 end-to-end recall from the full eval (59 pairs × 7 baselines × LLM judge) was:
- Based on Type1 queries (high overlap → easy for BM25)
- Structural recall floor was 1.000 (trivial due to overlap)
- Actual end-to-end recall with fair queries: **not yet measured** (needs LLM eval)
- Estimate: 0.627 × 0.88 ≈ **0.552 fair end-to-end recall**

---

## Analysis: Why Bias is 0.373

BM25 exploits keyword co-occurrence. When the query contains "G1 temporal retention" and the GT commit subject contains the same tokens, BM25 trivially retrieves it. Without those tokens, BM25 must rely on:
- Semantic context (which BM25 does NOT have)
- Partial matches from body text (BM25 only indexes subjects in this setup)

The 0.373 bias is the fraction of pairs where BM25 could only find the GT commit because the query contained exact keywords from the commit subject. This is NOT a sign of good retrieval — it's memorization of the evaluation set.

**22/59 paraphrase failures** — these are cases where BM25 genuinely cannot retrieve the answer without keyword hints.

---

## Implications for CTX

1. **BM25 body indexing**: Currently only commit subjects are indexed. Adding commit bodies would give BM25 semantic context beyond subject keywords → would recover some of the paraphrase failures.

2. **Hybrid retrieval**: Dense embedding + BM25 would handle the 22 paraphrase-failure cases (semantic queries that BM25 can't resolve without keywords).

3. **Query rewriting**: Production hook could rewrite user queries to include technical keywords from context before BM25 retrieval → partially recovers the advantage.

4. **Fair production recall**: If real user queries have ~0.085-0.200 keyword overlap with GT commits (lower than the 0.476 in Type1 eval), production recall is closer to **0.627** than 0.881.

---

## Files

- `benchmarks/eval/g1_fair_eval.py` — evaluation script
- `benchmarks/results/g1_fair_eval_results.json` — full results (59+12=71 pairs)

## Related

- `docs/research/20260409-g1-fulleval-sota-comparison.md` — original G1 eval (Structural Recall@7=1.000)
- `docs/research/20260409-g1g2-critique-and-verification.md` — initial bias analysis
- `docs/research/20260409-bm25-memory-generalization-research.md` — BM25 open-set research
