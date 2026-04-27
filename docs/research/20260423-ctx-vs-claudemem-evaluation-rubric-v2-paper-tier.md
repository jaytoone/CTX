# Evaluation Rubric v2 — Paper-tier CTX vs claude-mem Comparison

**Date**: 2026-04-23
**Status**: Proposal / unshipped
**Supersedes**: the informal 4-axis rubric in `20260422-ctx-vs-claudemem-paper-tier-comparison.docx` §2
**Target venues**: NeurIPS / ACL / SIGIR / EMNLP datasets & benchmarks tracks, CHI LBW, or a strong industrial track (e.g. NAACL Industry)

---

## 0. What's wrong with v1 (the 4-axis rubric)

v1 measured `accuracy, lift, latency, cost` with hand-picked 30/35/15/20 weights and a single scalar composite. Problems:

1. **Weights are arbitrary** — no theoretical or empirical basis. A reviewer asks "why 35% on lift?" and we have no answer.
2. **Lift is under-specified** — what *is* a task? What's the judge? What's the null hypothesis?
3. **Latency normalization is naive** — linear min-max scaling across systems of wildly different architectural classes (1 ms BM25 vs 6000 ms Chroma cold-start) makes the normalized score either saturate or collapse.
4. **No statistical protocol** — no pre-registration, no correction for multiple hypotheses, no effect-size reporting.
5. **Missing dimensions** — robustness, fairness across query types, calibration, determinism, privacy, drift.
6. **Single-judge LLM lift evaluation** — well-known bias vector; reviewers will cite LLM-judge-bias papers against us (Zheng et al. 2023; Huang et al. 2024).

Top-tier reviewers expect **pre-registered, multi-metric, confidence-interval-reported, effect-size-driven, adversarially-judged** benchmarks. v2 delivers that.

---

## 1. Framework: MERIDIAN — seven orthogonal dimensions

Rename the rubric. "MERIDIAN" is memorable and its letters force distinct axes:

| Letter | Dimension | One-line definition |
|---|---|---|
| **M** | **Memory recall quality** | How well does the system surface the right past context when queried? |
| **E** | **Effectiveness on downstream tasks** | Does injected context improve an independent agent's task success? |
| **R** | **Responsiveness** | How quickly does context arrive at the model? |
| **I** | **Intake completeness** | What fraction of "significant session events" does the system capture? |
| **D** | **Determinism & reproducibility** | Same query twice → same output? Same state after replay? |
| **I** | **Integrity under drift** | Performance as index ages / workload shifts / adversarial inputs |
| **A** | **Accounting** | $ per session + compute cost, fully attributed |
| **N** | **Neutrality (fairness)** | Performance parity across query types, languages, repo sizes, task difficulties |

Each dimension has:
- A **primary metric** (single number)
- **Secondary metrics** (distributional view)
- **Pre-registered threshold** (what counts as a meaningful difference)
- **Statistical test** (chosen before seeing data)

---

## 2. Per-dimension specification

### M — Memory recall quality

| | Spec |
|---|---|
| Primary metric | **Recall@5** on labeled gold set |
| Secondary | Recall@{1,3,10}, MRR, NDCG@10, nDCG with graded relevance labels |
| Gold set | N≥500 queries, third-party, see §3 |
| Stratification | by query type (keyword / paraphrase / multi-hop / cross-session), by topic, by age of target |
| Statistical test | Wilson 95% CI on Recall@K; paired bootstrap (n=10k) for system delta with BH-corrected p-values |
| Pre-registered threshold | Δ Recall@5 ≥ 0.05 with 95% CI lower bound > 0 — otherwise "practical tie" |

### E — Effectiveness on downstream tasks

| | Spec |
|---|---|
| Primary metric | **Task completion rate** on held-out agent tasks |
| Secondary | pass@1, pass@3, weighted-by-difficulty success |
| Task set | ≥150 tasks from 3+ independent sources: SWE-bench-Lite subset, a repo-navigation set (DevQA-style), a multi-session memory set (LongMemEval subset) |
| Conditions | 4-way: {neither, CTX-only, claude-mem-only, both} — within-subjects design |
| Agent | single fixed model + system prompt + temperature=0 across all conditions |
| Judge | **triple-judge Krippendorff-α ≥ 0.7 protocol**: task-specific deterministic oracle where possible (tests pass / exact match), LLM-judge ONLY as tiebreaker |
| Statistical test | McNemar's test for paired binary outcomes; Cohen's h for effect size |
| Pre-registered threshold | Δ completion rate ≥ 0.10 with McNemar p<0.05 after BH correction |

### R — Responsiveness

| | Spec |
|---|---|
| Primary metric | **p95 retrieval-to-model latency** (ms) |
| Secondary | p50, p99, cold-start latency (first-of-session), distribution shape (CV) |
| Measurement | wall-clock time from UserPromptSubmit hook start to context-injection returned to stdout |
| Protocol | 1000 trials per system per session-cold-state, run on both low-end (4-core) and reference (16-core) hardware |
| Statistical | Mann-Whitney U on latency distributions; Hodges-Lehmann estimator for median shift with 95% CI |
| Pre-registered threshold | Report both raw numbers and the normalized latency-utility curve per Pedraza et al. 2024 style — no single threshold (latency is a constraint not a score) |

### I₁ — Intake completeness

| | Spec |
|---|---|
| Primary metric | **coverage** = fraction of independently-annotated "significant events" captured as retrievable memory within the session |
| Secondary | precision (% captured items rated as "significant" by annotators), F1 |
| Gold set | 50 full Claude Code session transcripts, double-annotated with "significant decision/finding" labels, Krippendorff-α ≥ 0.67 required |
| Measurement | after session end, query each system for known-significant items; count hits |
| Statistical | paired bootstrap 10k resamples; report recall-precision trade-off curves |
| Pre-registered threshold | Δ F1 ≥ 0.10 with 95% CI lower bound > 0 |

### D — Determinism & reproducibility

| | Spec |
|---|---|
| Primary metric | **replay divergence rate** — fraction of replayed queries that return non-identical outputs |
| Secondary | Jaccard similarity of result sets across replays; top-1 stability |
| Protocol | record 200 queries + full context state; replay 3 times per system; diff outputs |
| Why it matters for papers | reviewers increasingly require reproducibility; a non-deterministic baseline is easy to critique |
| Pre-registered threshold | No formal threshold — report raw divergence rates; expected CTX ≈ 0, claude-mem > 0 (LLM-based intake introduces nondeterminism) |

### I₂ — Integrity under drift

| | Spec |
|---|---|
| Primary metric | **Recall@5 at t=30 days** after index freeze (synthetic aging on fixed corpus) |
| Secondary | recall decay curve at t ∈ {1, 7, 14, 30} days; behavior when queried for events post-freeze |
| Protocol | freeze index at T, continue injecting new events into "ground truth" only, query for both pre/post-freeze targets |
| Robustness suite | BEIR-style adversarial queries (typos, Q→K paraphrase, mined hard negatives), multilingual mix, length shifts |
| Pre-registered threshold | Report recall decay slope with bootstrapped CI; flag any system with t=30 recall < 0.5 × t=1 recall as "fragile" |

### A — Accounting

| | Spec |
|---|---|
| Primary metric | **$ per successfully-completed task** (cost-efficiency) |
| Secondary | $ per session, $ per retrieved-and-used context item, token breakdown (input/output/cached) |
| Protocol | instrument every LLM call with token counts + model tier; multiply by published price tables; report BOTH Anthropic and open-weights (via Together) prices |
| Why in paper | reviewers now demand explicit cost — especially for industrial-flavor venues |
| Pre-registered threshold | Report as a Pareto frontier alongside E (effectiveness) — don't reduce to a scalar |

### N — Neutrality (fairness across slices)

| | Spec |
|---|---|
| Primary metric | **worst-slice Recall@5** across {query_type, language, repo_size_bucket, difficulty_tier} |
| Secondary | Gini coefficient over per-slice performance; heatmap |
| Why it matters | top-tier reviewers penalize papers that average-away weaknesses; a system with 0.9 mean and 0.3 worst-slice is worse than 0.7 mean and 0.6 worst-slice for many real use cases |
| Pre-registered threshold | worst-slice Recall@5 must be ≥ 0.70 × mean Recall@5 to claim "robust" — otherwise report as "uneven" |

---

## 3. Gold set construction — the hard part

### 3.1 Sourcing

| Source | N | Why | License |
|---|---|---|---|
| **COIR** (NL→code) | 200 | Public, third-party, CTX already tested | MIT |
| **LongMemEval** (long-session memory) | 200 | Third-party, targets the cross-session claim | Apache-2.0 |
| **SWE-bench-Lite** (repo navigation subset) | 100 | Real-world task grounding | MIT |
| **Hand-labeled** (your own 50 real Claude Code sessions) | 100 | Ecological validity — real queries you actually asked | N/A (your data) |
| **Adversarial** (typo + paraphrase + cross-lingual) | 100 | Stress test, expose fragility | generated, release with publication |

**Total N ≥ 700** → Wilson 95% CI half-width ≤ 0.037 on proportions

### 3.2 Annotation protocol

- **≥ 2 annotators per item**; conflicts arbitrated by a 3rd
- **Krippendorff's α ≥ 0.67** required for a dimension's labels to be used
- **Label schema**: `relevant={0,1,2}` (graded), `difficulty={easy,med,hard}`, `query_type={keyword,paraphrase,multi-hop,cross-session}`, `language={en,ko,other}`
- **Release**: de-identified gold set + annotation guidelines + inter-annotator agreement stats published with the paper (common requirement for benchmark-track acceptance)

### 3.3 Held-out discipline

- Split 70/30 → **dev** (iteration) / **test** (single-use)
- Test set evaluated **once** per system, numbers locked
- Any re-query of test requires a new split (pre-registered)

---

## 4. Statistical hygiene

### 4.1 Pre-registration

- All thresholds, tests, and analyses above declared **before** first test-set evaluation
- Commit the protocol to a timestamped hash (e.g. OSF pre-registration, or just a signed git commit)
- Any deviation must be disclosed as exploratory

### 4.2 Multiple-hypothesis correction

- 8 dimensions × ~3 metrics each × 4 system conditions = ≥96 tests
- Apply **Benjamini-Hochberg** (FDR ≤ 0.05) across all primary tests
- Report raw p, adjusted p, and effect sizes

### 4.3 Effect sizes always reported

For every significant-in-p result, also report:
- Cohen's d (continuous) or Cohen's h (proportions)
- 95% bootstrap CI around the effect size
- Minimum detectable effect given sample size (power analysis)

### 4.4 Sensitivity analysis

- Vary judge-model choice → does E-dimension verdict flip?
- Vary gold-set subset (bootstrap 100x) → does worst-slice claim hold?
- Vary agent temperature (0, 0.3, 0.7) for E → reproducibility under stochasticity

---

## 5. Adversarial & fairness audit — the "reviewer won't shoot this down" layer

Top-tier reviewers in 2026+ routinely demand:

### 5.1 Anti-gaming checks

- Does either system memorize gold-set items? Test by evaluating on held-out mutations of each query (paraphrase + typo-injection). If recall doesn't drop, suspect memorization.
- Does CTX's git-log intake trivially win on commit-message queries? Isolate this slice and report separately.

### 5.2 Failure-mode taxonomy

- For each error in E dimension, classify: {retrieval-miss, retrieval-correct-but-ignored, over-anchoring, hallucination-in-agent, judge-disagreement}
- Proportion table per system

### 5.3 Cross-lingual check

- Report N dimension sliced by English / Korean / Chinese / code-heavy vs prose-heavy
- Expose whether CTX's hardcoded synonym map (Korean-English) provides unfair advantage on the Korean slice — if yes, disable it and re-measure as ablation

### 5.4 Privacy + leakage

- Compute % of captured observations containing PII (secrets, tokens, personal names)
- Both systems should be evaluated — claude-mem has LLM-generated narratives that may inadvertently include more context

---

## 6. Ablation matrix (mandatory for top-tier)

For CTX:
- CTX full
- CTX without semantic rerank (BM25-only)
- CTX without git-log (G2-docs-only)
- CTX without synonym map
- CTX without query-type router

For claude-mem:
- claude-mem with Chroma
- claude-mem FTS-only (no vector)
- claude-mem without LLM-summarized observations (raw tool-output intake)

Each variant evaluated on test set → provides the "which component contributes what" table reviewers expect.

---

## 7. Fairness protocol in comparison execution

Both systems must operate under **identical external conditions**:

| Condition | How enforced |
|---|---|
| Same session transcripts as input | replay from recorded `.jsonl` files |
| Same clock time for ingestion | replay uses fixed `T0`, skip real wall clock |
| Same hardware | containerized; 4-core / 16GB VM for each run |
| Same model for downstream E | same Claude Sonnet 4.5 snapshot, same system prompt, temp=0 |
| No re-tuning between dev and test | any hyperparameter changes after dev = new experiment |
| Both systems cold-started N=1000 times | controls for warm-cache bias |
| claude-mem's Chroma cold-start "defect" | **included** in latency measurement (don't hide with warmup hook during eval) |
| CTX's visible-failure warnings | **counted** as a feature, not noise — separate metric if useful |

---

## 8. Reporting template (paper-tier)

The comparison paper's results section should read approximately:

> "Across MERIDIAN's eight dimensions, CTX outperformed claude-mem on M (ΔR@5=0.11 [0.06, 0.16], p_adj < 0.001), N (worst-slice 0.72 vs 0.58), and R (3 ms vs 6000 ms cold-start), was statistically equivalent on E (task completion Δ=0.02 [−0.04, 0.08], p_adj=0.41), and underperformed on I₂ paraphrase robustness (0.61 vs 0.74). Ablation shows CTX's 0.11 recall advantage depends on git-log intake (ΔR@5 drops to 0.03 without). In cost-adjusted terms (A), CTX's effectiveness-per-$ is 18× claude-mem's because the latter spends an average $0.82 per session on intake LLM calls (N=150 sessions). Neither system consistently beats a mid-sized dense retriever fine-tuned on the dev set (BGE-reranker-base at 0.68 R@5 mean), suggesting retrieval-quality is not the dominant factor — the differentiator is cross-session persistence and visible-failure design (both unique to CTX)."

---

## 9. Minimum viable implementation timeline

To actually publish this, estimated work (conservative):

| Week | Work |
|---|---|
| 1 | Pre-register protocol; set up replay harness; implement both systems in paired-eval mode |
| 2 | Build gold set (COIR + LongMemEval + SWE-Lite ingestion; write annotation guidelines) |
| 3–4 | Annotate 700 items with 2+ annotators; compute α; arbitrate disagreements |
| 5 | Run M + R + D dimensions on full test set |
| 6 | Run E (agent tasks) — most expensive, needs real LLM budget (~$500) |
| 7 | Run I₁, I₂, N, ablations |
| 8 | Statistical analysis + figure generation |
| 9 | Draft paper |
| 10 | Internal review, revision |
| 11–12 | Submit + supplementary materials |

~3 months solo; 6 weeks with 2 annotators working in parallel.

---

## 10. What to execute first

1. **Pre-register this document** (commit + date-stamp) — defends against p-hacking accusations
2. **Build the paired-eval harness** — the most reusable piece, useful even if the paper falls through
3. **Hand-label 100 real sessions** — fastest path to having ANY third-party-grade gold data
4. **Pilot run on that 100** — sanity-check the full pipeline before investing in N=700

Stop here if pilot results are decisively one-sided (either direction). Continue to full N=700 only if pilot shows meaningful contested dimensions.

---

## Appendix A — Mapping v1 rubric to v2

| v1 axis | v2 location | Change |
|---|---|---|
| Retrieval accuracy | **M** | Added slicing (N), adversarial (I₂), gold-set expansion 500→700 |
| Downstream lift | **E** | Single-judge → triple-judge + oracle primary; added paired design; added effect size reporting |
| Latency | **R** | Added cold-start as first-class; reported as constraint, not normalized score |
| Cost | **A** | Unchanged concept; now reported as Pareto frontier with E, not a composite component |
| — | **I₁** (intake) | NEW |
| — | **D** (determinism) | NEW |
| — | **I₂** (drift) | NEW |
| — | **N** (fairness) | NEW |

v2 increases measurement burden ~3x but produces a result a top-tier reviewer can't easily dismiss.

## Appendix B — References for review cross-checks

- **Zheng et al. 2023** — LLM-as-judge biases (MT-Bench). Use triple-judge to mitigate.
- **Huang et al. 2024** — position bias in LLM judges. Use randomized option ordering.
- **Benjamini & Hochberg 1995** — FDR control. Apply across all primary tests.
- **Krippendorff 2018** — inter-annotator agreement. α ≥ 0.67 for labels to be usable.
- **Wilson 1927** — binomial CI. Use for all proportion metrics.
- **Pedraza et al. 2024** — latency-utility trade-off curves for retrieval papers. Use instead of raw latency scalar.

## Related
- [[projects/CTX/research/20260421-ctx-distribution-research-replay|20260421-ctx-distribution-research-replay]]
- [[projects/CTX/research/20260329-ctx-corrected-results-summary|20260329-ctx-corrected-results-summary]]
- [[projects/CTX/research/20260426-mab-longmemeval-validity-for-ctx|20260426-mab-longmemeval-validity-for-ctx]]
- [[projects/CTX/paper/CTX_paper_draft|CTX_paper_draft]]
- [[projects/CTX/research/20260426-g2-docs-eval-corpus-drift-fix|20260426-g2-docs-eval-corpus-drift-fix]]
- [[projects/CTX/benchmark/g1_g2_publication_framework|g1_g2_publication_framework]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260326-ctx-vs-industry-comparison|20260326-ctx-vs-industry-comparison]]
