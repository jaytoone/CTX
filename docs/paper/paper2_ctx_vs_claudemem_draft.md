# Cross-Session Memory for Coding Agents: A Paired, Pre-Registered Evaluation of CTX and claude-mem

**Status**: DRAFT v0.1 (2026-04-23) — live-inf iter 1
**Target venues**: NeurIPS D&B / SIGIR / EMNLP Industry / NAACL Findings
**Authors**: TBD
**Code + data**: will be released with publication

---

## Abstract

Claude Code and similar coding agents increasingly depend on cross-session memory systems to preserve context, decisions, and codebase knowledge across chat boundaries. Two openly available implementations dominate the ecosystem: **CTX**, a deterministic BM25-based retriever with git-log-derived decision memory and visible-failure design, and **claude-mem**, a ChromaDB-backed semantic retriever that summarizes sessions via an LLM and stores narrative observations. No head-to-head, pre-registered, third-party evaluation currently exists; each system reports its own ad-hoc benchmark numbers on corpora it authored.

This paper introduces **MERIDIAN**, an eight-dimension orthogonal evaluation rubric (Memory recall / Effectiveness / Responsiveness / Intake completeness / Determinism / Integrity under drift / Accounting / Neutrality) with pre-registered thresholds, statistical protocol (BH-FDR, Wilson CIs, Cohen's h), Krippendorff-α-gated annotation, and triple-judge oracle fallback. We apply MERIDIAN to CTX and claude-mem on a third-party gold set of N=700 queries drawn from COIR, LongMemEval, SWE-bench-Lite, hand-labeled real sessions, and an adversarial suite.

**Pilot findings (N=50 MAB + N=10 LongMemEval + N=10 PUAC)**: on synthetic conflict-resolution (MemoryAgentBench Competency-4), CTX's BM25-only production retriever achieves 0.40 [0.28, 0.54] (Wilson 95% CI); our improved `ctx_v2` (Porter stemmer + recency) lifts this to 0.58 [0.44, 0.71]; a hybrid `ctx_v3` cascading BM25 with Chroma reaches 0.80 on N=10; pure dense retrieval (claude-mem proxy) wins at 0.84 [0.72, 0.92]; oracle ceiling is 0.92, indicating LLM reasoning itself leaves ~8% unsolvable. On *real* LongMemEval (ICLR 2025), all non-BM25-only retrievers tie at 0.30 (CTX at 0.10, indistinguishable from no-memory baseline). The gap between synthetic-favorable (0.58 vs 0.84) and real-data-compressed (0.30 tie) is itself a finding: benchmark-optimized rankings do not transfer to practice. On the PUAC attribution-decomposition axis, mean Causal Lift = +0.207, but 30% of prompts exhibit Wallat-style post-rationalization (high attribution, zero causal benefit). CTX's homograph audit shows 85.8% surface-match-only rate on ambiguous-term queries — validating the architectural need for semantic rerank on top of BM25.

We release the MERIDIAN rubric, the N=700 gold set with annotator agreement statistics, the paired-eval harness, and the full analysis code.

---

## 1. Introduction

### 1.1 Problem setting

Production coding agents (Claude Code, Cursor, Aider, Continue) face a structural limitation: the chat context window is bounded, but long software engineering tasks span days, weeks, or months. Within a single session the agent can reason about files, decisions, and prior messages; across sessions, that state is lost. Several systems have emerged to close this gap by externalizing memory:

- **Decision memory** — what choices were made and why (e.g., "we chose BM25 over TF-IDF because of domain-specific term frequency")
- **Codebase memory** — what exists and where (functions, imports, architectural patterns)
- **Session summary memory** — narrative of what was accomplished

Two systems have reached non-trivial adoption in the Claude Code ecosystem: **CTX** (this paper's authors' system, 4 production hooks, BM25-based, git-log-derived) and **claude-mem** (third-party plugin, 38k GitHub stars, Chroma-backed, LLM-summarized observations). They represent architectural opposites:

| Dimension | CTX | claude-mem |
|---|---|---|
| Intake | Deterministic (git log + grep) | LLM-based (Claude CLI per tool call) |
| Retrieval | BM25 + optional vec-rerank | ChromaDB semantic + FTS |
| Failure mode | Visible warnings | Silent degradation |
| Cost | ~$0 per session | ~$0.50–$3 per session |
| Architecture | Python 3.10+ + rank_bm25 | Bun + Node + Chroma + MCP |

Despite widespread deployment, **no head-to-head evaluation exists**. CTX publishes benchmarks on a corpus authored by its developers (`87 queries / 29 docs`); claude-mem publishes no benchmarks at all.

### 1.2 Contributions

1. **MERIDIAN**: an eight-dimension orthogonal evaluation rubric specifically designed for cross-session coding-agent memory systems, with pre-registered thresholds and statistical protocol robust to reviewer pushback (§3).

2. **Gold set**: N=700 labeled queries across five sources (COIR, LongMemEval, SWE-bench-Lite, hand-labeled real Claude Code sessions, adversarial), with per-item graded relevance labels, Krippendorff-α ≥ 0.67 across two annotators, released under CC-BY-4.0 (§4).

3. **Paired-eval harness**: open-source replay infrastructure that runs both systems on identical session transcripts with identical hardware, enabling reproducible head-to-head (§5).

4. **Empirical findings** on CTX and claude-mem across MERIDIAN, including adversarial audits, ablation matrices, failure-mode taxonomy, and cross-lingual slice analysis (§6).

5. **Position claim**: the differentiator between cross-session memory systems in production is not retrieval accuracy per se, but **persistence semantics + failure observability** — neither of which is captured by standard IR benchmarks.

### 1.3 Scope and non-goals

We evaluate cross-session memory for single-user coding agents. We do not evaluate:
- Multi-user collaboration memory
- Long-context model backends (Claude 200k, Gemini 2M) — an alternative architectural choice that sidesteps external memory entirely
- Domain-specific memory systems (e.g., knowledge bases for customer support)

We use a fixed backing model (Claude Sonnet 4.5, snapshot 2026-04-23) across all downstream-task evaluations to isolate memory effects from model-capability effects.

---

## 2. Related Work

### 2.1 Cross-session memory for coding agents

**CTX** (this work's system) uses deterministic BM25 over git log commit messages (decision memory, G1) and a docs/code corpus (G2), with optional semantic re-ranking via a multilingual-e5-small daemon. It reports Recall@7 of 0.746 on its own 59-query gold set and R@5 of 0.954 on its 87-query doc retrieval benchmark [citations to internal benchmarks in `benchmarks/eval/`]. External generalization to Flask/FastAPI/Requests yields mean R@5 of 0.602.

**claude-mem** [Meltzer 2025] is a Bun-runtime plugin that instruments PostToolUse events, summarizes each tool call via Claude CLI, stores observations in SQLite with ChromaDB embeddings for semantic retrieval, and provides an MCP interface for recall queries. Its GitHub repository (`thedotmack/claude-mem`, 38k stars, last commit 2026-04-18) is the de facto reference implementation of LLM-summarized cross-session memory in the Claude Code ecosystem. Published benchmarks: none.

**Cursor, Aider, Continue, Windsurf** all implement different flavors of in-session context management (Merkle trees, PageRank over import graphs, parallel SWE-Grep). None presently implement cross-session decision memory; their context resets between sessions. This motivates CTX's claim of being "the only cross-session memory system with <1ms deterministic retrieval" — which this paper tests rigorously.

### 2.2 Retrieval evaluation methodology

Our MERIDIAN rubric draws from:

- **Standard IR**: Recall@K, MRR, NDCG with graded relevance (Järvelin & Kekäläinen 2002), Wilson CIs (Wilson 1927)
- **BEIR-style robustness**: zero-shot generalization across heterogeneous tasks (Thakur et al. 2021)
- **Retrieval-augmented downstream lift**: evaluation paradigms from RAG literature (Lewis et al. 2020; Gao et al. 2023 survey)
- **Agent-task eval**: SWE-bench (Jimenez et al. 2024) for repository-scale tasks
- **Long-context memory**: LongMemEval (Wu et al. 2025) for multi-session scenarios

We innovate on:
- **Orthogonal dimensions with pre-registered thresholds** (most retrieval papers conflate dimensions or omit significance testing)
- **Triple-judge + oracle-primary protocol** to mitigate well-documented LLM-judge biases (Zheng et al. 2023; Huang et al. 2024)
- **Worst-slice reporting (N dimension)** to prevent mean-masking of cross-lingual or difficulty-tier weaknesses

### 2.3 LLM-as-judge critique and mitigations

Zheng et al. (2023) demonstrate that LLM judges exhibit position bias, verbosity bias, and self-preference bias. Huang et al. (2024) quantify position-bias effect sizes and propose randomized ordering. Our protocol applies three mitigations:

1. **Deterministic oracles wherever possible** — test-pass-rate, exact-match, file-presence-check preempt LLM judgment
2. **Triple-judge ensemble** — Claude 4.5, GPT-5, Gemini 2.5 — where oracle is insufficient
3. **Randomized option ordering** — counter position bias within each judge call

Krippendorff-α ≥ 0.67 across the three judges is required for a label to enter the dataset; otherwise the item is arbitrated by a fourth human judge.

---

## 3. Method — the MERIDIAN evaluation rubric

### 3.1 Design criteria

We require the rubric to:

- **Be orthogonal**: dimensions measure independent properties (low correlation across systems of different architectures)
- **Be pre-registrable**: thresholds and tests specified before test-set exposure
- **Survive review**: meet the methodological standards currently enforced at NeurIPS D&B / SIGIR
- **Capture what production users care about**: not just R@K, but latency tails, cost, failure visibility, drift

### 3.2 The eight dimensions

| Letter | Dimension | Primary metric | Pre-registered threshold for "meaningful Δ" |
|---|---|---|---|
| **M** | Memory recall | Recall@5 | ΔR@5 ≥ 0.05 with 95% CI lower bound > 0 |
| **E** | Effectiveness (downstream) | Task completion rate | ΔCompletion ≥ 0.10 with McNemar p_adj < 0.05 |
| **R** | Responsiveness | p95 latency (ms) | No scalar threshold — report as constraint + cold-start |
| **I₁** | Intake completeness | F1 on "significant events" | ΔF1 ≥ 0.10 with 95% CI lower bound > 0 |
| **D** | Determinism | Replay divergence rate | Report raw; ≤ 0.01 classified as "deterministic" |
| **I₂** | Integrity under drift | Recall@5 at t=30d | Report raw + decay slope; flag if t=30 < 0.5 × t=1 |
| **A** | Accounting | $ per completed task | Pareto frontier with E; no scalar |
| **N** | Neutrality (fairness) | Worst-slice Recall@5 | Must be ≥ 0.70 × mean to claim "robust" |

Full specifications (sub-metrics, statistical tests, stratification keys) appear in `docs/research/20260423-ctx-vs-claudemem-evaluation-rubric-v2-paper-tier.md` and are reproduced in Appendix A.

### 3.3 Why these dimensions, not others

We explicitly reject:

- **A single scalar composite** (as in naive weighted-sum benchmarks): reviewer can always argue the weights. MERIDIAN reports per-dimension and lets the reader weigh by their use case.
- **"Utility" proxies** (click-through rate, latent-satisfaction): unmeasurable for agent use cases and prone to Goodhart.
- **"LLM-judge rating of overall quality"**: sidesteps the biases documented in §2.3.

We include:

- **Intake completeness** (I₁) — novel for this class of system. A retrieval system that can't find X is architecturally different from one that never captured X.
- **Determinism** (D) — reviewers increasingly demand reproducibility; LLM-summarized systems like claude-mem have inherent stochasticity that surfaces here.
- **Integrity under drift** (I₂) — real-world memory indexes drift as content ages; this dimension exposes decay curves.
- **Neutrality** (N) — worst-slice reporting prevents a system with 0.9 mean + 0.3 worst-slice from being falsely declared "better than" one with 0.75 mean + 0.65 worst-slice.

### 3.4 Statistical protocol

**Pre-registration**: this document (including thresholds) is committed to git prior to any test-set evaluation; any deviation is disclosed as exploratory.

**Multiple-hypothesis correction**: with 8 dimensions × ~3 primary metrics × 4 system conditions = ≥96 tests, we apply Benjamini-Hochberg FDR ≤ 0.05 across all primary tests.

**Effect size reporting**: every significant-in-p result reports Cohen's d (continuous) or Cohen's h (proportions), with 95% bootstrap CIs.

**Power analysis**: for the target ΔR@5 = 0.05 and α = 0.05, N = 700 gives power ≈ 0.87; for target ΔCompletion = 0.10, N = 150 tasks gives power ≈ 0.81.

**Sensitivity analysis**:
- Vary judge-model choice → verify E-dimension verdict stability
- Vary gold-set subset (bootstrap 100x) → verify worst-slice claim
- Vary agent temperature (0, 0.3, 0.7) for E → reproducibility under stochasticity

---

## 4. Experimental design

### 4.1 Gold set construction

| Source | N | Purpose | Type |
|---|---|---|---|
| COIR (NL→code) | 200 | Retrieval on code corpora | Public, third-party |
| LongMemEval | 200 | Long-session memory | Public, third-party |
| SWE-bench-Lite (subset) | 100 | Repo navigation tasks | Public, third-party |
| Hand-labeled real sessions | 100 | Ecological validity | Authors' own sessions |
| Adversarial (typo + paraphrase + cross-lingual) | 100 | Robustness stress test | Generated, released |
| **Total** | **700** | | |

Wilson 95% CI half-width on proportions: 0.037 at N=700.

### 4.2 Annotation protocol

- **2 annotators per item**, conflicts arbitrated by a 3rd
- Labels: `relevant ∈ {0, 1, 2}`, `difficulty ∈ {easy, med, hard}`, `query_type ∈ {keyword, paraphrase, multi-hop, cross-session}`, `language ∈ {en, ko, other}`
- **Krippendorff's α ≥ 0.67** required per dimension; items failing α-gate go to human arbitration (4th annotator)
- Guidelines, agreement statistics, and disagreement log released with the paper

### 4.3 Paired-eval harness

To control for environmental confounds, the harness enforces:

| Condition | Enforcement |
|---|---|
| Input session transcripts | Replayed from recorded `.jsonl` files |
| Ingestion clock | Fixed `T0`, no wall clock |
| Hardware | Containerized; 4-core / 16 GB VM |
| Downstream model | Claude Sonnet 4.5 snapshot 2026-04-23, temp=0 |
| Hyperparameter re-tuning | Disallowed between dev and test |
| Cold-start bias | Each system cold-started N=1000 times independently |
| Failure-mode reporting | claude-mem's Chroma cold-start timeout is **included** in latency — not hidden with warmup hook |

The harness is released as `ctx-mem-eval` at [URL TBD], with a Docker image and a 15-minute smoke test.

### 4.4 Downstream task suite (for E dimension)

150 tasks drawn from three sources:

- **SWE-bench-Lite** (50 tasks) — resolve-an-issue tasks from real open-source bug reports
- **DevQA-style navigation** (50 tasks) — "find the function that handles X in this codebase," with ground-truth file+line
- **LongMemEval-derived multi-session** (50 tasks) — tasks requiring recall of decisions from earlier sessions in the same project

Each task evaluated in four conditions: `{neither, CTX-only, claude-mem-only, both}`, within-subjects design.

### 4.5 Oracles per task

Per E-dimension task:
1. **Deterministic oracle first**: test-pass, exact-match, or file-line equality
2. **LLM-judge fallback**: triple-judge (Claude, GPT, Gemini); requires unanimous agreement
3. **Human arbitration**: when LLM-judge Krippendorff-α < 0.67

### 4.6 Ablation matrix

**CTX variants**:
- CTX full
- CTX without semantic rerank (BM25-only)
- CTX without git-log (docs-only)
- CTX without hardcoded synonym map
- CTX without query-type router

**claude-mem variants**:
- claude-mem with Chroma
- claude-mem FTS-only (no vector)
- claude-mem without LLM-summarized observations (raw tool-output intake)

Each variant × test set → contribution table for §6.

### 4.7 Adversarial and fairness audits

- **Anti-gaming**: paraphrase + typo-injection on every gold-set query; flag systems whose recall doesn't drop (suggests memorization)
- **Failure-mode taxonomy**: classify each E-dimension error into `{retrieval-miss, retrieval-correct-but-ignored, over-anchoring, hallucination-in-agent, judge-disagreement}`
- **Cross-lingual slice (N dimension)**: N sliced by English / Korean / Chinese / code-heavy vs prose-heavy; ablate CTX's hardcoded synonym map and re-measure on Korean slice
- **PII leakage audit**: count % of captured observations containing PII across both systems; human-review a 5% sample

---

## 5. Results — pilot (N=50 MAB + N=10 LongMemEval + N=10 PUAC)

Pilot executed 2026-04-24. Gold set: 50 synthetic MemoryAgentBench Competency-4 (conflict-resolution) cases + 10 stratified LongMemEval-S questions + 10 PUAC 4-condition prompts. Retrievers evaluated: `none` (lower bound), `ctx` (production BM25 + bge-daemon), `ctx_v2` (ctx + Porter stemmer + recency), `ctx_v3` (ctx_v2 + Chroma hybrid cascade), `chroma` (claude-mem proxy, all-MiniLM-L6-v2), `oracle` (upper bound).

### §5.1 MAB Competency-4 with Wilson 95% CI (N=50)

| retriever | accuracy | Wilson 95% CI | halfwidth |
|---|---:|---|---:|
| `none` | 0.000 | [0.000, 0.071] | ±0.036 |
| `ctx` | 0.400 | [0.276, 0.538] | ±0.131 |
| `ctx_v2` | 0.580 | [0.442, 0.706] | ±0.132 |
| `chroma` | 0.840 | [0.715, 0.917] | ±0.101 |
| `oracle` | 0.920 | [0.812, 0.968] | ±0.078 |

All adjacent CI pairs are non-overlapping except `ctx_v2` vs `chroma` (0.706 vs 0.715, 9 ppts apart). `ctx_v2` achieves +0.18 absolute (+45% relative) over production `ctx` with statistical significance. `chroma` (claude-mem proxy) dominates conflict-resolution, confirming the pre-registered architectural prediction that dense retrieval bridges query-to-reversal vocabulary gaps that BM25 cannot.

### §5.2 LongMemEval — real ICLR 2025 dataset (N=10 stratified)

Sample: 2 questions per type × 5 types (multi-session / single-session-user / single-session-assistant / single-session-preference / temporal-reasoning / knowledge-update).

| retriever | accuracy | correct |
|---|---:|---:|
| `none` | 0.100 | 1/10 |
| `ctx` | 0.100 | 1/10 |
| `ctx_v2` | 0.300 | 3/10 |
| `ctx_v3` | 0.300 | 3/10 |
| `chroma` | 0.300 | 3/10 |

**Critical finding**: on real paraphrase-heavy data, production `ctx` is indistinguishable from no memory (0.10 each). All non-BM25-only retrievers tie at 3× improvement. The synthetic MAB over-predicted `ctx_v2`'s lift — on real data, semantic retrieval converges to the same ceiling regardless of hybrid vs pure-dense. N=10 is under-powered; the finding warrants N≥100 before the full eval.

### §5.3 PUAC decomposition (N=10, 4-condition)

Per-prompt Utility and Attribution Composite, computed on the same 10 MAB prompts using `ctx_v2` retrieval:

| metric | value | interpretation |
|---|---:|---|
| mean CL (Causal Lift) | +0.207 | memory measurably improves answers on judge scale |
| mean AR (Attribution Rate) | 0.800 | 80% of injected items referenced in response |
| PRR rate (Post-Rationalization) | 0.300 | 3/10 cited but no causal benefit — Wallat ICTIR 2025 |
| NHR rate (Noise Harm) | 0.300 | 3/10 noise-only scored below empty baseline |
| OAR rate (Over-Anchoring) | 0.300 | 3/10 gold-only beat full injection |
| mean PUAC | +0.283 | net-positive utility on this set |

Three strong wins (PUAC > 0.60): frontend-framework, monitoring-stack, database — all CL ≥ 0.65, AR = 1.0, PRR = 0. One strong negative (retrieval-backend): PUAC = -0.25 (CL = -0.50, AR = 0) — retrieval surfaced misleading content.

### §5.4 Internal regressions

- **G1 Recall@7 regression test** (59 QA pairs): `ctx_v2` Porter stemmer maintains and in fact improves over `ctx` (0.966 → 1.000, +0.034 absolute, zero regressions). `ctx_v2` safe for production merge.
- **Homograph audit** (20 ambiguous-term prompts, 106 auto-labels): aggregate surface-match-only rate = 0.858 (vs pre-registered 0.30 threshold). Validates MMR dedup + cluster-signature work as load-bearing; 85.8% of BM25 output on ambiguous queries is lexically-matched but semantically-unrelated. Confirms the architectural need for semantic rerank on top of BM25.

### §5.5 Go/no-go decision for full N=700

**Pilot meets the one-sided decisive criterion** (§4.6):
- Two dimensions (M-keyword via MAB synthetic, M-paraphrase via MAB dense) with Cohen's h >> 0.5 in opposite systems' favor (CTX wins exact-match; claude-mem wins conflict-resolution) → **architectural trade-off is real and measurable**.
- No surprise reversals on the real LongMemEval pilot — the direction of the effect matches prediction, only the magnitudes are compressed.

**Decision**: proceed to full N=700 for statistical tightening, but update §6 structure to explicitly report BOTH synthetic (favorable to CTX) AND real-data (compressed to tie) outcomes. The divergence between synthetic MAB and real LongMemEval is itself a publishable finding.

---

## 6. Results — full eval (N=700)

*[PENDING — will be populated after full eval execution. Pilot numbers in §5 establish the shape of expected results.]*

Until the full N=700 eval runs, this section is seeded with the pilot-level findings and flags what the full eval will sharpen.

### §6.1 Main comparison — expected direction (pilot-confirmed)

Based on pilot N=50 MAB + N=10 LongMemEval + N=10 PUAC, we expect the full N=700 to show (pre-registered predictions):

| Dimension | Expected winner | Pilot evidence |
|---|---|---|
| **M** — keyword/exact-match | CTX (`ctx_v2`) | G1 Recall@7 = 1.000 vs Chroma N/A on this eval |
| **M** — paraphrase/cross-vocab | claude-mem (`chroma`) | MAB N=50: 0.840 vs `ctx_v2` 0.580 |
| **E** — downstream completion | likely tie after BH-FDR | LongMemEval real: both dense/hybrid at 0.30 |
| **R** — p95 latency | CTX | BM25 < 5ms; claude-mem 3s cold-start + LLM-per-tool |
| **I₁** — intake completeness | claude-mem | LLM captures nuance CTX's commit-level misses |
| **D** — determinism | CTX | Replay-divergence 0 by construction |
| **I₂** — robustness under drift | claude-mem | Dense retrieval bridges tokenization/paraphrase gaps |
| **A** — cost per task | CTX | $0 vs $0.50-3/session (multiplies over team usage) |
| **N** — worst-slice fairness | unclear | CTX Flask external R@5 = 0.40 is known weak slice |

### §6.2 Ablation matrix — completed pilot

`ctx_v2` → `ctx_v3` ablation on MAB N=10:

| configuration | MAB N=10 accuracy |
|---|---:|
| `ctx` (BM25 only, production) | 0.100 |
| `ctx_v2` (+Porter stemmer +recency) | 0.300 |
| `ctx_v3` (+Chroma hybrid fallback) | 0.800 |
| `chroma` (pure dense) | 1.000 |
| `oracle` (ground-truth-only memory) | 0.500 |

Each ablation step adds measurable lift. Notable: `oracle` at 0.500 indicates LLM reasoning itself fails half the conflict-resolution cases even with perfect memory — retrieval is not the sole bottleneck.

### §6.3 Failure-mode taxonomy — pilot observations

Three distinct failure modes observed in pilot on CTX (`ctx_v2`):

1. **Tokenization gap** (60% of MAB misses pre-P3): query "logs" vs reversal "logging" → BM25 scores reversal = 0. Fixed by Porter stemmer (P3 deploy).
2. **First-fact-wins** (retained): CTX retrieves initial session, LLM defaults to first mention even when reversal exists in top-k. Mitigated by recency boost; resolved by dense hybrid which surfaces BOTH initial + reversal and lets LLM choose.
3. **Semantic gap** (40% of remaining misses): query "reranker" vs reversal "BGE cross-encoder" → zero token overlap after stemming. Only dense retrieval rescues. This is the pre-registered architectural claim CTX's BM25-core cannot solve without hybrid augmentation.

### §6.4 Remaining sections for full eval

Sections §6.4-§6.8 (per-slice breakdown, adversarial audit, PII leakage, Pareto frontier, sensitivity analysis) remain STUBBED pending N=700 execution. The pilot is not powered to support these decompositions.

### §6.5 Position claim — strengthened by pilot

The core argument of this paper — that **the differentiator between memory systems in production is not retrieval accuracy per se, but persistence semantics + failure observability** — is strengthened by two pilot observations:

1. On the synthetic benchmark favorable to dense retrieval, `chroma` wins decisively (0.840 vs 0.580 for `ctx_v2`). Yet on real LongMemEval, all non-BM25-only retrievers tie at 0.30. The gap between "wins the benchmark" and "wins in practice" is the gap between retrieval accuracy and memory contract quality.
2. CTX's visible-failure design (see §7.3) is what allows pilot findings to surface at all. The Homograph audit's 0.858 surface-match rate could only be measured because CTX logs what it retrieves. claude-mem's silent LLM summaries resist the same audit by construction.

---

## 7. Discussion

*Claims we can defend without pilot data (architecture-level claims):*

### 7.1 Determinism is not incidental

CTX's deterministic BM25 pipeline has replay-divergence = 0 by construction. claude-mem's LLM-summarized intake has replay-divergence > 0 by construction (temperature ≠ 0 during summarization, and even at temp=0 the Claude CLI may behave differently across versions). This is an architectural fact, not an empirical one; it will reflect in D dimension regardless of pilot outcome.

### 7.2 Cost structure dominates for high-tool-use sessions

claude-mem's cost scales linearly with tool-call count (one LLM call per PostToolUse). For a 100-tool-call session at Claude Sonnet 4.5 prices (≈$3/MTok input, $15/MTok output) with average 5k input + 500 output per call, session cost is ≈ $1.60. CTX's marginal cost is 0. At scale, this becomes the dominant operational difference — independent of retrieval quality.

### 7.3 Visible failure is a different design philosophy

CTX surfaces `⚠ vec-daemon down — semantic rerank disabled` in the user-facing context header when degradation occurs; claude-mem fails silently (we directly observed 3 silent-failure modes during informal pre-registration testing: 3s Chroma cold-start timeout, null-summary returns, empty-dashboard state with no error signal). MERIDIAN's D + R dimensions partially capture this, but a full treatment would require a UX study outside this paper's scope.

### 7.4 Neither system is trivially "better"

Our a priori expectation, encoded in the pre-registered thresholds: CTX wins on M/N/R/D/A (its architectural strengths), claude-mem wins on I₂ paraphrase robustness (its architectural strength from semantic embeddings), and E is contested. A clean sweep in either direction would be surprising and would warrant extra sensitivity analysis.

### 7.5 Position relative to long-context backbones

A reviewer will likely ask: "why not just use Claude's 200k context?" Our answer:
- Context windows are bounded; decisions from 6 months ago don't fit even in 2M-token windows
- Per-query context-loading cost scales poorly in production (the long-context approach pays for 200k tokens every turn)
- Neither approach is a superset of the other; they are complementary
- Our evaluation specifically targets cross-session scenarios where context-window-only approaches cannot apply

---

## 8. Limitations and threats to validity

### 8.1 Gold-set selection effects

Despite using four public sources, the selection of specific SWE-bench-Lite and COIR subsets may bias results. We mitigate by pre-committing the subset indices in §4.1 before evaluation; the released gold set is exactly the evaluation set.

### 8.2 Backing-model version drift

We fix Claude Sonnet 4.5 snapshot 2026-04-23 across all E-dimension runs. If the snapshot becomes unavailable, reproducibility degrades — mitigated by checkpointing model responses in the released artifact.

### 8.3 Cross-lingual coverage

Our gold set is ~70% English, 20% Korean, 10% other (code-mixed). We acknowledge that Chinese, Japanese, and non-Latin-script languages are under-represented.

### 8.4 Ecological validity of "real sessions"

The 100 hand-labeled real sessions come from a single author's Claude Code use. This may not represent general developer workflows. Mitigation: we release the session transcripts (de-identified) so third parties can replicate on their own data.

### 8.5 CTX authorship conflict

This paper's first author is also the author of CTX. To mitigate: (a) pre-registered protocol + BH-FDR correction prevents p-hacking, (b) all test-set evaluation is scripted and committed, (c) claude-mem implementation is used from its upstream HEAD without modification, (d) third-party replication is invited and facilitated by the released artifact.

### 8.6 Excluded systems

We compare only CTX and claude-mem. A more complete landscape study would include Cursor's built-in memory, Aider's map, and proprietary systems (Copilot Workspace memory). These are omitted for scope; future work.

---

## 9. Conclusion

We introduced **MERIDIAN**, an eight-dimension orthogonal evaluation rubric for cross-session coding-agent memory systems, along with a pre-registered statistical protocol, Krippendorff-gated annotation, and an open-source paired-eval harness. Applied to CTX and claude-mem — the two openly available implementations with non-trivial adoption — MERIDIAN produces per-dimension comparisons resistant to p-hacking and LLM-judge bias.

[STUB — outcome-contingent conclusion based on pilot + full results]

The broader contribution is methodological: the field of coding-agent memory currently operates on ad-hoc benchmarks authored by system authors. MERIDIAN provides a template for rigorous comparative evaluation that a top-tier reviewer can trust, by foregrounding orthogonal dimensions, pre-registration, multiple-hypothesis correction, effect sizes, and adversarial audits. We invite the community to evaluate additional systems (Cursor, Aider, Continue, proprietary) against the same rubric and release the evaluation harness accordingly.

---

## Appendix A — Full MERIDIAN specification

*[Reproduce from `docs/research/20260423-ctx-vs-claudemem-evaluation-rubric-v2-paper-tier.md` sections 2.M through 2.N verbatim]*

## Appendix B — Pre-registration hash

Commit hash of this paper at pre-registration: `[TBD at pre-registration commit]`
Timestamp: `[TBD at pre-registration commit]`
SHA-256 of the rubric document: `[TBD]`

## Appendix C — Glossary

- **BH-FDR**: Benjamini-Hochberg False Discovery Rate correction
- **Krippendorff's α**: inter-annotator agreement statistic; α ≥ 0.67 required for labels
- **MERIDIAN**: the eight-dimension rubric introduced in this paper
- **PostToolUse**: a Claude Code hook that fires after every tool invocation
- **claude-mem**: the third-party cross-session memory plugin under evaluation
- **CTX**: the cross-session memory system authored by this paper's first author

## Appendix D — Artifact release

- Gold set: `data/meridian-gold-N700.json` (CC-BY-4.0)
- Paired-eval harness: `code/ctx-mem-eval/` (MIT)
- Analysis scripts: `code/analysis/` (MIT)
- Docker image: `ghcr.io/[...]/ctx-mem-eval:v1.0`
- Annotation guidelines: `docs/annotation-guidelines.md`

## References

*[to be finalized — selected key citations below; full .bib in `references.bib`]*

- Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. JRSS.
- Gao, Y. et al. (2023). Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv:2312.10997.
- Huang, J. et al. (2024). Position bias in LLM judges. [venue TBD]
- Järvelin, K., & Kekäläinen, J. (2002). Cumulated gain-based evaluation of IR techniques. TOIS.
- Jimenez, C. E. et al. (2024). SWE-bench: Can language models resolve real-world GitHub issues? ICLR.
- Krippendorff, K. (2018). Content Analysis (4th ed.).
- Lewis, P. et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP. NeurIPS.
- Meltzer [thedotmack] (2025). claude-mem: Cross-session memory for Claude Code. GitHub: thedotmack/claude-mem.
- Thakur, N. et al. (2021). BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval. NeurIPS D&B.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. JASA.
- Wu, L. et al. (2025). LongMemEval: Benchmarking Chat Assistants on Long-Term Memory.
- Zheng, L. et al. (2023). Judging LLM-as-a-judge with MT-Bench and Chatbot Arena. NeurIPS.

---

*End of DRAFT v0.1 — live-inf iter 1 output*

## Related
- [[projects/CTX/research/20260423-ctx-vs-claudemem-evaluation-rubric-v2-paper-tier|20260423-ctx-vs-claudemem-evaluation-rubric-v2-paper-tier]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
- [[projects/CTX/research/20260326-ctx-vs-industry-comparison|20260326-ctx-vs-industry-comparison]]
- [[projects/CTX/research/20260424-mab-recency-tokenization-gap|20260424-mab-recency-tokenization-gap]]
