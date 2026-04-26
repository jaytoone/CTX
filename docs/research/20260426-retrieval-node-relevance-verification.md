# [expert-research-v2] Retrieval Node Relevance Verification
**Date**: 2026-04-26  **Skill**: expert-research-v2

## Original Question
When CTX selects a retrieval node (G1 decision or G2 file) as "related" to the current prompt, can we formally prove or measure that it is actually relevant? What SOTA methods exist to verify retrieval node relevance?

## Web Facts

[FACT-1] ARES (Stanford, arXiv:2311.09476): Automated RAG evaluation via fine-tuned LM judges — context relevance, answer faithfulness, answer relevance. Uses prediction-powered inference (PPI) with ~150 human annotations for confidence intervals.

[FACT-2] RAGAS framework: context precision (fraction of retrieved chunks actually relevant), context recall, faithfulness, answer relevance. LLM-as-judge — no ground truth labels needed at runtime.

[FACT-3] Faithfulness ≠ correctness (ACM 2025): Relevance and faithfulness are separate measurable dimensions — a node can be cited without actually being used.

[FACT-4] Counterfactual ablation: Remove node, re-run generation, measure ΔQ = Q(with) − Q(without). Cleanest causal proof; requires 2 LLM calls per node.

[FACT-5] SELF-RAG: LLM generates inline reflection tokens [IsREL], [IsSUP] as self-assessment. Requires fine-tuned model.

[FACT-6] BM25 score = lexical overlap proxy only. CTX's 85.8% surface-match-without-semantic-match confirms this is insufficient alone.

## Multi-Lens Analysis

### Domain Expert (Lens 1)

**Insight 1 — BM25 score is a lexical overlap signal, not a relevance certificate**
The 85.8% false-positive rate is exactly what IR theory predicts for polysemous technical corpora ("token", "context", "memory", "index" each have 3-5 distinct meanings). BM25's Okapi formulation was designed for sparse web vocabulary, not dense codebase vocabulary.

**Insight 2 — Counterfactual ablation is the closest to formal causal proof, but impractical synchronously**
ΔQ = Q(with node) − Q(without node) > threshold is grounded in Pearl's do-calculus. If removing a node degrades response quality, that node had causal influence. Cost: 2 LLM calls per node × k nodes — infeasible at 100-180ms budget. Solution: run asynchronously on 10% random sample to build calibration data over time.

**Insight 3 — LLM-as-judge (RAGAS context precision) gives probabilistic verification with no labels needed**
A lightweight RAGAS judge prompt — "Given prompt {P} and retrieved node {N}, is the node relevant? Yes/No + one sentence" — via MiniMax API is implementable today. Not formal proof; probabilistic verification from a second model's perspective. Judge accuracy: 70-85% on RAG benchmarks (15-30% error on ambiguous cases).

**Insight 4 — Citation probe is a zero-cost usage signal (SELF-RAG proxy)**
Prompt CTX to include "USED: [node-ids] | UNUSED: [node-ids]" in system prompt. Nodes consistently appearing in UNUSED lists are operationally irrelevant regardless of BM25 score. Zero infrastructure cost. Caveat: citation confabulation/omission rates for background context injection (not explicit QA) are uncharacterized.

**Insight 5 — Vec-daemon cosine similarity + BGE-reranker is the most actionable improvement**
Hybrid BM25+cosine (already runs in chat-memory, 50%/50%) applied to G1/G2 immediately cuts homograph false positives. BGE cross-encoder (bge-daemon, already deployed, +90ms) as second-pass reranker provides fine-grained passage-query matching. Infrastructure path exists — it's a configuration extension, not new development.

### Self-Critique (Lens 2)

- **[CONFLICT]** RAGAS context precision and counterfactual ablation can give contradictory verdicts: a node can be topically relevant (high RAGAS score) but causally redundant (ΔQ≈0) if another node covers the same information. These measure different things: topical alignment vs. causal necessity.
- **[OVERCONFIDENT]** Counterfactual ablation's causal purity is overstated. Removing node A changes attention patterns on nodes B,C,D (SUTVA violation). ΔQ measures A's marginal contribution given others present — not A's standalone relevance.
- **[MISSING — critical]** No SOTA method addresses temporal-causal relevance for G1 nodes. G1 is past decisions — a commit from 6 days ago about "BM25 threshold" may be causally relevant to a current prompt about "retrieval cutoffs" even if vocabulary doesn't overlap. All RAGAS/ARES/SELF-RAG methods treat relevance as synchronic (same-time) semantic relation. G1 requires temporal-causal relevance — a fundamentally different, unsolved problem.

### Synthesis (Lens 3)

**Short answer: Formal proof of relevance is impossible. Probabilistic verification is achievable at multiple confidence levels.**

| Method | What it measures | Cost | CTX-implementable today? |
|---|---|---|---|
| BM25 score | Lexical overlap only | ~0ms | Yes — already running; insufficient alone |
| Cosine (vec-daemon) | Semantic proximity | ~90ms | Yes — hybrid exists in chat-memory |
| BGE cross-encoder (bge-daemon) | Fine-grained match | ~90ms | Yes — already deployed |
| LLM-as-judge (RAGAS async) | Topical alignment | ~500ms async | Yes — MiniMax API |
| Counterfactual ablation | Causal necessity | ~2 LLM calls | Yes — async 10% sampling |
| Citation probe | Model's self-reported usage | ~0ms overhead | Yes — prompt modification only |

**Recommended implementation sequence:**
1. **TODAY (1-2h)**: Extend G1/G2 to hybrid BM25+cosine via vec-daemon (same config as chat-memory)
2. **TODAY (1h)**: Add citation probe to CTX system prompt — generates calibration data at zero cost
3. **WEEK 1**: Enable async RAGAS judge logging at 20% sample rate — first quantitative context precision measurement
4. **WEEK 1**: Apply BGE-reranker to top-10 candidates (already deployed)
5. **OPEN RESEARCH**: Temporal-causal relevance for G1 — no SOTA method handles this; requires novel graph-distance-weighted formulation (git blame ancestry + semantic similarity)

## Final Conclusion

**Formal proof: No.** Relevance is a relation that depends on the model's reasoning process — not fully observable.

**Measurable proxies, in order of strength:**
1. Counterfactual ablation ΔQ — causal necessity (strongest, async-only)
2. LLM-as-judge (RAGAS) — topical alignment (probabilistic, ~70-85% accurate)
3. Citation probe — operational usage (zero cost, noisy)
4. Cosine similarity (vec-daemon) — semantic proximity (continuous, fast)
5. BM25 score — lexical overlap (necessary but not sufficient)

**The 85.8% false-positive problem is solvable now** by routing G1/G2 through the hybrid BM25+cosine already running in chat-memory. The citation probe adds zero-cost calibration data collection.

**G1 temporal-causal relevance is genuinely unsolved in SOTA** — the most important open research problem for CTX's G1 subsystem.

## Sources

- [ARES: Automated RAG Evaluation (arXiv:2311.09476)](https://arxiv.org/html/2311.09476v2)
- [RAGAS Framework (confident-ai.com)](https://www.confident-ai.com/blog/rag-evaluation-metrics-answer-relevancy-faithfulness-and-more)
- [Faithfulness-Aware Multi-Objective Context Ranking (ACM 2025)](https://dl.acm.org/doi/full/10.1145/3797161.3797180)
- [RAG Evaluation Metrics (Braintrust)](https://www.braintrust.dev/articles/rag-evaluation-metrics)
