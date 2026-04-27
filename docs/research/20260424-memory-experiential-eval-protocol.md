# Experiential Evaluation of Coding-Agent Memory Systems
## A Protocol for "피부로 와닿는" Assessment of CTX vs claude-mem vs claude-memory-compiler

**Date**: 2026-04-24  
**Status**: Design proposal — pre-registration candidate  
**Purpose**: Complement MERIDIAN (Recall@K, NDCG, p95 latency) with a human-perceptible utility layer  
**Scope**: Three-tier evaluation protocol; literature grounding; adversarial audit list; ablation matrix

---

## Part 1: Literature — Experiential Evaluation of Retrieval Systems

### 1.1 The gap MERIDIAN leaves open

MERIDIAN measures whether the *right item was retrieved*. It does not measure whether:
- A human using Claude Code *felt* that the injection was helpful
- Claude *used* the injected content in forming its response
- The response would have been *worse* without it

This gap is well-documented in IR and NLP literature and is the proximate cause of the "token noise" problem already observed in this project ("token" prompt → 3 of 4 BM25 hits are about paper-editing commits, not the BM25 algorithm).

### 1.2 Foundational literature: pairwise human judgment for RAG

**Gienapp et al., "The Viability of Crowdsourcing for RAG Evaluation" (arXiv:2504.15689, SIGIR 2025)** [GROUNDED]

The strongest recent methodological paper on human evaluation of RAG. Key findings directly applicable here:

- *Pairwise human judgment on utility dimensions* outperforms both pointwise human judgment and LLM-as-judge pairwise when measuring *utility* (the composite of coverage + coherence + answer quality). The reason: humans are inconsistent at absolute scales ("is this response a 4 or 5?") but are reliable at relative comparison ("is A or B more useful for this query?"). The CrowdRAG-25 corpus demonstrates that 47,320 pairwise judgments over 65 topics produce high inter-rater reliability with low annotator cost.
- *Seven utility dimensions* are operationalized: coverage, coherence, relevance, groundedness, completeness, readability, and attribution. For coding-agent memory evaluation, **coverage** (did the response address what I needed?) and **attribution** (did it use the injected context?) are the two load-bearing ones.
- *LLM pairwise judgment tracks human pairwise judgment* significantly better than LLM pointwise judgment, but still underestimates disagreement cases. Implication: for Tier 3 (real sessions), human raters are required; for Tier 2 (semi-automatic), LLM-judge is acceptable *if* cross-validated against a human anchor set.

**RAGAS (Es et al., arXiv:2309.15217, 2023)** [GROUNDED]

The de facto standard decomposition of RAG quality into four independently measurable metrics:

1. **Faithfulness** — are the claims in the response entailed by the retrieved context?
2. **Answer Relevance** — does the response address the question?
3. **Context Precision** — of what was retrieved, what fraction was actually needed?
4. **Context Recall** — of what was needed, what fraction was retrieved?

RAGAS occupies the space between pure IR (Recall@K) and end-to-end answer quality (LLM judge). For this study:
- **Faithfulness directly measures "did Claude use the memory?"** — a claim in the response is faithfulness-positive if and only if it can be traced to the retrieved context.
- **Context Precision maps directly to the noise problem**: low precision = Claude received irrelevant memory nodes that potentially distracted or mislead it.

RAGAS is fully automatable using Claude itself as the entailment checker, which is how we can scale Tier 2 to hundreds of prompts without human annotators.

**RAGChecker (Ru et al., arXiv:2408.08067, NeurIPS 2024 D&B)** [GROUNDED]

Finer-grained than RAGAS. Instead of document-level attribution, RAGChecker extracts *claims* from the response and checks each claim against the retrieved context via entailment. This produces:

- `context_utilization`: what fraction of retrievable claims actually appeared in the response (directly analogous to: "did Claude use this memory node?")
- `noise_sensitivity_in_relevant`: rate at which an answer is *changed* by injecting a *relevant* document — a measure of over-anchoring
- `noise_sensitivity_in_irrelevant`: rate at which answer is changed by injecting an *irrelevant* document — the key adversarial metric for CTX's token-noise failure mode
- `hallucination`: claims in response not in context AND not in ground truth

The RAGChecker `noise_sensitivity_in_irrelevant` metric is the most directly applicable adversarial probe for the surface-token match failure. If CTX injects BM25 hits that match "token" lexically but are semantically about paper edits, and Claude changes its code answer in response to that irrelevant content, the score is positive — meaning CTX actively *harmed* the response. This is what "피부로 와닿는" bad looks like.

### 1.3 The "right for wrong reason" and post-rationalization problems

**Wallat et al., "Correctness is not Faithfulness in RAG Attributions" (arXiv:2412.18004, ICTIR 2025)** [GROUNDED]

The most directly relevant paper to the attribution problem. Key distinction:

- **Citation correctness**: the cited document *supports* the stated claim (can be verified after the fact)
- **Citation faithfulness**: the model *actually derived* the claim from the cited document (the document was causally necessary)

Critically: **up to 57% of citations lack faithfulness** despite being correct. The mechanism is *post-rationalization*: the model knew the answer from parametric memory, generated the response, then found a supporting document to cite — creating the *appearance* of grounded retrieval while the memory was not causally involved. This is the "right for the wrong reason" problem in its sharpest form.

For CTX evaluation, this means that **a high RAGAS faithfulness score alone is insufficient** to prove memory utility. A model that already knows the answer and happens to receive a relevant memory node will score highly on faithfulness even though memory provided zero marginal benefit. Only counterfactual ablation — comparing responses with vs. without each memory node — can disentangle causal from correlative attribution.

### 1.4 The context utilization / "lost in the middle" problem

**Liu et al., "Lost in the Middle: How Language Models Use Long Contexts" (arXiv:2307.03172, 2023)** [GROUNDED]

LLMs preferentially use information at the *beginning and end* of the context window; information in the middle is used at a substantially lower rate. For CTX, which injects memory as a header block before the user prompt, this is favorable positioning — but for claude-mem and claude-memory-compiler, which may inject in variable positions or summarize into running context, this creates a confound: a system that retrieves correctly but positions context in the middle of a long window will score lower on downstream tasks than a system that retrieves less accurately but positions content first.

The implication for evaluation: **position of injection must be controlled or reported as a covariate** in any downstream task comparison. MERIDIAN v2 should add a "position" metadata field to each condition.

### 1.5 What the strongest RAG/memory papers do that the weakest don't

Survey of five recent papers (2024-2026):

| Paper | With/without user study | Pairwise preference | Attribution chain | Counterfactual | Verdict |
|---|---|---|---|---|---|
| Mem0 blog (Singh 2025) [GROUNDED] | No user study — LLM-as-judge only | No | No | No | Weakest: no human signal, self-reported benchmark on own LOCOMO dataset |
| RAGAS (Es et al. 2023) [GROUNDED] | WikiEval with human labels as anchor | Yes (precision/recall vs human) | Partial (faithfulness) | No | Medium: automated but anchored to human; no real-session replay |
| RAGChecker (Ru et al. 2024) [GROUNDED] | Human-annotated preference dataset for meta-eval | Yes — meta-eval correlates metrics with human preferences | Full claim-level chain | Partial (noise sensitivity) | Strong: claim-level entailment + human meta-eval + NeurIPS venue |
| CrowdRAG-25 (Gienapp et al. 2025) [GROUNDED] | Full human study, 47k judgments | Yes — pairwise as primary signal | No explicit chain | No | Strongest for *human utility*: shows pairwise > pointwise + LLM |
| Wallat et al. 2024 [GROUNDED] | Designed experiments, no real-user study | No | Full faithfulness chain | Yes (causal experiment design) | Strongest for *attribution*: explicitly tests causal vs. correlative |

**What the strongest papers share that the weakest don't:**
1. They separate multiple failure modes instead of collapsing to one score
2. They include at least one human anchor even if the primary evaluation is automated
3. They report effect sizes and confidence intervals, not just point estimates
4. They test at least one adversarial condition (irrelevant injection, post-rationalization)

---

## Part 2: Adversarial Audit Design

### 2.1 The surface-token match failure (already observed)

The known failure: BM25 returns documents matching "token" as a surface form (paper-editing commits about "token budgets", "token count" in some CLAUDE.md entry) when the user's prompt uses "token" in the sense of software token parsing. RAGChecker's `noise_sensitivity_in_irrelevant` directly quantifies this.

**Systematic audit**:
1. Construct a *homograph query set*: 20+ prompts where a key term has multiple senses in the corpus (e.g., "token", "graph", "model", "context", "session", "index", "cache")
2. For each prompt, label each retrieved node as `RELEVANT` / `SURFACE_MATCH_ONLY` / `IRRELEVANT`
3. Measure: what fraction of BM25-top-5 items are `SURFACE_MATCH_ONLY`?
4. Measure: does Claude's response change (get worse) when `SURFACE_MATCH_ONLY` nodes are included vs. excluded?

Expected finding direction: CTX-BM25 will show higher `SURFACE_MATCH_ONLY` rate than CTX+vec-rerank or claude-mem (dense). But claude-mem may show false positive *semantic* matches (different kind of noise).

### 2.2 The post-rationalization failure

**Systematic audit**:
1. Select 30 prompts where Claude demonstrably knows the answer from parametric memory (well-known Python APIs, common patterns)
2. For each, inject *true-but-unnecessary* memory (correct information Claude already knows)
3. Compare: response with memory vs. without memory — are they identical?
4. If identical: injection was zero-utility (context_utilization = 0 despite faithfulness = 1)
5. If different and *better*: injection was genuinely helpful
6. If different and *worse*: injection caused regression (over-anchoring)

This audit exposes what Wallat et al. call the "alignment tax": memory that scores high on correctness but zero on causal utility.

### 2.3 The stale-index failure

**Systematic audit**: (specific to CTX based on observed 254-hour staleness incident, 2026-04-17)
1. Artificially age the codebase-memory-mcp index to T+24h, T+72h, T+168h (1 week)
2. At each point, query with prompts targeting *recent* changes (new function names, new file paths)
3. Measure: at what staleness threshold does Hit@5 drop below 0.50?
4. Measure: does the system's own warning system correctly flag the staleness?

For claude-mem: the analog is session-summary drift — if observations were written N sessions ago, do they still correctly describe the current codebase?

### 2.4 The semantic-void failure (injection without information)

For systems that inject narrative summaries (claude-mem, claude-memory-compiler):
1. Construct prompts where the memory is semantically adjacent but factually empty ("we discussed the BM25 approach" — correct, but contains no specific information)
2. Measure: does Claude behave as if it received useful context, producing confident but wrong responses?
3. This is the "semantic placebo" failure: the injection shapes Claude's tone and confidence without providing actionable information.

### 2.5 The injection-position exploit

For any system:
1. Inject memory at position 0 (before system prompt), position 1 (after system prompt), and position 2 (after user turn)
2. Measure downstream task performance at each position
3. A system that scores well only because it positions content first is not demonstrating memory quality — it is demonstiting injection strategy quality.

---

## Part 3: Concrete 3-Tier Protocol

### Tier 1: Automatic Public Benchmark (Citable)

**What is measured**: Retrieval quality on a third-party gold set that no system author has seen during development.

**Dataset construction**:
- N = 300 queries minimum (power calculation: to detect Δ = 0.08 in Recall@5 at α=0.05, β=0.20, paired design → N ≈ 280)
- Sources: 100 from COIR (Natural Language → Code queries, existing labeled), 100 from LongMemEval-mini (cross-session decision recall), 100 hand-labeled from real Claude Code session transcripts (covering homograph, temporal, and multi-hop query types)
- Stratification: query_type × age_bucket × topic_domain

**What is measured per query**:
- Recall@{1, 3, 5, 10}
- MRR
- NDCG@10
- Binary: was any `SURFACE_MATCH_ONLY` item in the top-5? (noise audit)
- RAGChecker `context_precision` and `claim_recall` over each system's top-5

**Statistical test**: Paired bootstrap (n=10,000 resamples), Benjamini-Hochberg FDR correction across all metric comparisons. Wilson 95% CI on each Recall@K point. Effect size: Cohen's d on NDCG.

**Threshold for "real" difference**: Δ Recall@5 ≥ 0.05 with 95% CI lower bound > 0 AND Cohen's |d| ≥ 0.30 (medium effect). Smaller deltas are reported as "practical tie."

**How it composes into a paper claim**: "System X achieves Recall@5 = A [CI: B–C] vs. System Y at D [CI: E–F], a statistically significant difference (paired bootstrap p = G, d = H)."

**Tier 1 is citable** because: (a) the gold set is released under CC-BY-4.0, (b) any reader can reproduce the numbers on identical hardware, (c) no system author labeled the queries.

---

### Tier 2: Semi-Automatic Attribution Chain (Retrieval → Response → Citation)

**What is measured**: Whether retrieved memory was causally used in the response, and whether its absence would have degraded the response.

**Setup**: For each of N = 150 prompts (sampled from the same gold set), run 4 conditions:
- A: Full memory injection (system-under-test's default)
- B: Empty injection (no memory nodes injected, prompt otherwise identical)
- C: Gold-only injection (only the labeled-correct nodes, no noise)
- D: Noise-only injection (only `SURFACE_MATCH_ONLY` or IRRELEVANT nodes)

All conditions use the same backing model (Claude Sonnet 4.6, temperature = 0), same system prompt, same user turn.

**Measured metrics**:

| Metric | Formula | Source |
|---|---|---|
| Causal lift (CL) | judge(A) − judge(B) | LLM judge on [0,1] scale |
| Attribution rate (AR) | RAGChecker context_utilization on condition A | Automated |
| Post-rationalization rate (PRR) | judge(A) ≈ judge(B) AND AR > 0 | Derived: high AR + ~0 CL = post-rationalization |
| Noise harm rate (NHR) | judge(D) < judge(B) | Condition D performs worse than baseline = noise hurt |
| Over-anchoring rate (OAR) | judge(C) > judge(A) | Gold-only beats full injection = noise in A is harmful |

**The 피부로 와닿는 composite** (PUAC — Perceived Utility Attribution Composite):

```
PUAC = 0.5 × CL + 0.3 × AR − 0.2 × PRR
```

Rationale: Causal lift (did memory help?) is the primary signal. Attribution rate (did Claude reference the content?) is supporting evidence. Post-rationalization rate (did Claude pretend to use memory it didn't need?) is a penalty — it inflates AR without delivering lift.

**Statistical test**: McNemar's test for binary outcome version of CL (response improved / not improved). Wilcoxon signed-rank on continuous CL distribution. Effect size: r = Z/√N.

**Threshold for "real" difference**: Δ PUAC ≥ 0.10, McNemar p < 0.05, r ≥ 0.30.

**N rationale**: 150 prompts × 4 conditions = 600 LLM calls per system. At Claude Sonnet pricing (~$0.003/call) = ~$1.80/system. Entirely feasible for paper-tier evaluation.

**How it composes**: "CTX's post-rationalization rate is X% vs. claude-mem's Y% — meaning X% of CTX's attributed citations were present in the response but were not causally necessary, consistent with Wallat et al. (2024)'s finding of up to 57% PRR in attributed RAG systems."

---

### Tier 3: Human Pairwise A/B Over Real Claude Code Sessions (피부로 와닿는)

**What is measured**: Whether a real human, seeing two side-by-side Claude Code sessions (one with memory, one without; or CTX vs. claude-mem), judges the memory-augmented session to be more helpful — not on a scale, not on a rubric, but on a binary preference choice with a brief free-text justification.

**Session collection protocol**:
1. Recruit 5–8 Claude Code users (can be paper authors' colleagues; declare conflict; use for secondary analysis only)
2. Each user completes 10 real coding tasks over 2–4 sessions, alternating memory systems (ABBA counterbalance for order effects)
3. For each session, record: (a) the full transcript, (b) all memory injections with injection contents visible, (c) the user's own task-completion judgment
4. After each session, show the user *their own session* with memory annotations highlighted: "these memory items were injected before this prompt"
5. User is asked per-prompt: "Was this memory relevant? Did Claude seem to use it? Would you have wanted this memory?" (3-item binary checklist, ~30 seconds per prompt)

**Post-session analysis**:
6. A *blinded* second rater (not the user, not a system author) reviews each session transcript and marks each memory injection as `relevant / irrelevant / misleading` based on the conversation context
7. Agreement with user's own judgment is computed (Fleiss' κ or Cohen's κ if N is small)
8. LLM-as-judge is run on the same sessions to compute Tier 2 PUAC — correlation between PUAC and human "was this useful?" is the primary cross-tier validation

**What "피부로 와닿는" looks like in this protocol**:
- A session where the user marks 8/10 injections as "relevant + Claude used it" is a win condition
- A session where the user marks 7/10 injections as "noise — I had to scroll past this" is a loss condition
- The free-text justifications are qualitatively coded into failure mode taxonomy (surface-token match / temporal mismatch / semantic placebo / position waste)

**Statistical test**: Sign test on within-user preference counts (CTX vs. claude-mem, 10 tasks per user, 5–8 users = 50–80 paired observations). Threshold: p < 0.05 one-tailed, Cohen's g ≥ 0.30. Cross-tier Pearson r between PUAC (Tier 2) and human preference rate (Tier 3) — report r ≥ 0.60 as "PUAC is a valid proxy for human judgment."

**N rationale**: 5 users × 10 tasks × avg 8 prompts/task = 400 human annotations. At ~1 minute per annotation: ~7 hours of annotation labor. This is feasible for a small human study that complements the automated tiers.

---

### How the Tiers Compose into a Paper Claim

```
Tier 1 (citable benchmark): "CTX Recall@5 = 0.746, claude-mem = X [CI], Δ = Y [CI]"
      ↓ feeds
Tier 2 (attribution chain): "Of CTX's retrievals, Z% caused measurable response lift (PUAC = A)"
      ↓ feeds
Tier 3 (human sessions): "Human users judged B% of CTX injections as 'relevant + used';
                           Tier 2 PUAC correlates with human judgment at r = C"
```

The composed claim: "CTX achieves higher retrieval accuracy (Tier 1) AND a higher fraction of its retrievals are causally useful to Claude (Tier 2), and humans can perceive this utility without a rubric (Tier 3, r = C)."

This is the claim that survives both top-tier reviewers (who need Tier 1 statistics) and product users (who need Tier 3 experience).

---

## Part 4: Ablation Matrix

The following single-variable ablations are required for a credible paper claim. Each ablation changes exactly one component and measures Recall@5, PUAC, and noise_sensitivity_in_irrelevant.

### CTX ablations

| Ablation ID | Variable changed | Expected direction |
|---|---|---|
| CTX-A1 | BM25-only → BM25 + BGE-M3 rerank | ↑ Recall on paraphrase; ↓ latency; ↑ Context Precision |
| CTX-A2 | BM25-only → BM25 + vec-daemon (multilingual-e5-small) | ↑ homograph queries; marginal latency cost |
| CTX-A3 | Default n=30 candidates → n=10 / n=50 | Tests sensitivity of retrieval depth to PUAC |
| CTX-A4 | With G1 (decision memory) → G2-only (code search only) | Isolates which memory type provides causal lift |
| CTX-A5 | With G2 (code search) → G1-only | Symmetric isolation |
| CTX-A6 | With vec-daemon semantic rerank → BM25-only (fallback mode) | Quantifies degradation from the 6-day silent failure mode (2026-04-11) |
| CTX-A7 | Full injection → injection with min-score threshold (MMR dedup) | Tests whether noise reduction improves PUAC without hurting Recall@5 |

### claude-mem ablations

| Ablation ID | Variable changed | Expected direction |
|---|---|---|
| CM-A1 | ChromaDB semantic → SQLite FTS-only | Tests semantic retrieval marginal value |
| CM-A2 | LLM-summarized observations → raw session transcript chunks | Tests whether LLM compression adds or removes information |
| CM-A3 | All observations → recency-capped (last 7 days only) | Tests temporal decay; should ↑ Precision, ↓ Recall on old sessions |
| CM-A4 | Default retrieval → retrieval with chunk size × 2 | Tests context length effect on PUAC |
| CM-A5 | Full intake (every PostToolUse) → sampled intake (every 3rd) | Tests intake completeness vs. retrieval quality tradeoff |

### Shared / cross-system ablations

| Ablation ID | Variable changed | Expected direction |
|---|---|---|
| SH-A1 | Memory injected → memory removed (null condition B) | Primary counterfactual; required for PUAC computation |
| SH-A2 | Memory injected at position 0 (header) → position 2 (post-user-turn) | Tests "lost in the middle" injection position confound |
| SH-A3 | Temperature = 0 → temperature = 0.7 | Tests whether noisy memory degrades more at higher temperature (variance × noise interaction) |
| SH-A4 | English-only prompts → Korean/mixed-language prompts | Neutrality (MERIDIAN N dimension); CTX uses multilingual-e5 which should handle this |
| SH-A5 | Homograph query subset only | Tests surface-token-match failure in isolation across all systems |

---

## Verification Needed

The following claims in this document are [UNCERTAIN] and should be fact-checked by the research team before committing to this protocol:

1. [UNCERTAIN] The Gienapp et al. (2025) finding that *human pairwise judgment is more reliable than LLM pairwise* — this was shown on TREC RAG'24 (web-search tasks). Whether it replicates on *coding-agent memory* tasks (different domain, different annotators) is unknown. The Tier 3 cross-tier correlation (r ≥ 0.60 target) is the empirical test.

2. [UNCERTAIN] The 57% post-rationalization rate in Wallat et al. (2024) was measured on web-search RAG, not coding-agent memory. The rate for CTX's memory injections could be higher (since Claude knows Python/coding facts from pretraining) or lower (since CTX decision memory contains highly specific project-local facts not in pretraining).

3. [UNCERTAIN] PUAC formula weights (0.5 / 0.3 / -0.2 for CL / AR / PRR) are hypothesized, not empirically derived. They should be learned from the Tier 3 human labels in a small pilot (N=50 prompts, fit a logistic regression of human preference against CL/AR/PRR) before being fixed for the main run.

4. [UNCERTAIN] LongMemEval's cross-session queries are designed for conversational agents (chatbots), not coding agents. The query difficulty distribution may not represent real CTX usage. This requires inspection of LongMemEval's query types before committing to 100 queries from that source.

5. [UNCERTAIN] claude-memory-compiler's architecture is not yet fully characterized. The ablation matrix above covers claude-mem (thedotmack) and CTX. A third-system parallel requires understanding whether claude-memory-compiler uses a similar Chroma/FTS backend or a different approach.

---

*References (cited by arXiv ID or venue):*
- *Gienapp et al., arXiv:2504.15689, SIGIR 2025*
- *Es et al., arXiv:2309.15217, 2023 (RAGAS)*
- *Ru et al., arXiv:2408.08067, NeurIPS 2024 D&B (RAGChecker)*
- *Wallat et al., arXiv:2412.18004, ICTIR 2025*
- *Liu et al., arXiv:2307.03172, 2023 (Lost in the Middle)*
- *Singh (Mem0), mem0.ai blog, April 2025 (field notes extending arXiv:2505.xxxxx)*
