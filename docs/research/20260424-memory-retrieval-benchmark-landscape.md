# Memory & Retrieval Benchmark Landscape for LLM/Agent Systems (2025–2026)

**Date**: 2026-04-24
**Purpose**: Pre-paper survey — identify cite-able benchmarks for a CTX vs. claude-mem comparison paper targeting NeurIPS D&B / SIGIR / EMNLP venues.
**Scope**: NEW benchmarks not already in the paper draft, with focus on (a) human-eval components, (b) cross-session memory, (c) coding-agent specificity.

---

## 1. Benchmarks Already in the Paper Draft (Do Not Re-Research)

Listed here only as orientation anchors:

| Name | Venue | Already in draft? |
|------|-------|-------------------|
| NIAH (gkamradt) | community | yes |
| BABILong | NeurIPS 2024 | yes |
| NeedleBench (OpenCompass) | OpenReview 2024 | yes |
| MRCR | Google/OpenAI 2024 | yes |
| LongMemEval | ICLR 2025 | yes |
| SWE-bench / SWE-bench-Lite | ICLR 2024 | yes |
| COIR | ACL 2025 | yes |
| MERIDIAN (ours) | pre-registered | yes |

---

## 2. NEW Benchmarks — Detailed Survey

### 2.1 MemoryAgentBench (ICLR 2026)

**Citation**: Hu, Wang & McAuley. "Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions." arXiv:2507.05257. Accepted ICLR 2026.
**URL**: https://arxiv.org/abs/2507.05257 | https://github.com/HUST-AI-HYZ/MemoryAgentBench

**What it measures**: Four competencies derived from cognitive-science memory theory:
1. Accurate retrieval — recall stored facts under paraphrase and distractor pressure
2. Test-time learning — update beliefs as new contradictory information arrives
3. Long-range understanding — reason across items spread across long interaction histories
4. Conflict resolution (selective forgetting) — resolve contradictions between earlier and later facts

**Evaluation protocol**: Incremental multi-turn interactions; segments existing long-context datasets (e.g., ScrollS, NarrativeQA) into sequential chunks fed to the agent, simulating real-time memory updates. Two new datasets introduced: EventQA (retrieval) and FactConsolidation (conflict resolution). Evaluation is fully automatic: exact-match and F1 on held-out question sets.

**Human eval component**: NO — automatic only (exact match / F1). No human raters or Likert scores.

**Cross-session relevance**: HIGH — the "test-time learning" and "conflict resolution" axes directly model what happens when a developer's decision reverses over multiple sessions (e.g., "we chose BM25, then we chose dense, then we reverted"). This is CTX vs. claude-mem's core battleground.

**Top-tier cite-ability**: HIGH — ICLR 2026 accepted. Hu/McAuley pedigree. Dataset on Hugging Face.

**Gap vs. MERIDIAN**: MemoryAgentBench is domain-agnostic (chat + narrative), not coding-specific. CTX's git-log-derived decision memory maps onto competencies 1 and 3 directly; claude-mem's LLM-summarized intake maps onto competency 2. A reviewer who knows MemoryAgentBench will expect you to map MERIDIAN dimensions onto these four competencies in the related work section.

---

### 2.2 AMA-Bench (ICLR 2026 Memory Workshop)

**Citation**: AMA-Bench team. "AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications." arXiv:2602.22769. ICLR 2026 MemAgents Workshop.
**URL**: https://arxiv.org/abs/2602.22769 | https://ama-bench.github.io/

**What it measures**: Long-horizon agentic memory where the "context" is a stream of agent-environment interaction traces (tool calls, observations, responses), NOT human-agent dialogue. Two tracks:
- Real-world track: actual agentic trajectories from representative applications, paired with expert-curated QA
- Synthetic track: procedurally generated trajectories at arbitrary scale, paired with rule-based QA

**Evaluation protocol**: Expert-curated QA pairs evaluated via exact-match and LLM-judge (with human expert as ground truth). The real-world track uses **expert human annotation** for QA construction — making this one of the few benchmarks with genuine human judgment in the eval pipeline, even if the final scoring is automatic.

**Human eval component**: PARTIAL — human experts write the QA pairs in the real-world track (construction-time human judgment). Final scoring is automatic. No live human raters at evaluation time.

**Cross-session relevance**: HIGH — AMA-Bench explicitly targets the gap between dialogue-centric benchmarks and real agentic workflows. The trajectories include tool use, file operations, and multi-step reasoning — very close to what CTX and claude-mem observe via PostToolUse hooks.

**Top-tier cite-ability**: MEDIUM-HIGH — workshop paper, not main track. But the ICLR 2026 MemAgents workshop is the designated venue for this class of work; reviewers at NeurIPS D&B will recognize it. GPT-5.2 achieves only 72.26% accuracy, leaving headroom for memory-system comparisons.

**Key differentiator from MERIDIAN**: AMA-Bench evaluates the memory module's ability to transform raw trajectories into retrievable structure (what MERIDIAN calls I₁ — Intake completeness). This is the dimension where CTX (deterministic git-log extraction) and claude-mem (LLM-summarized PostToolUse) most fundamentally differ. AMA-Bench gives you a public framing for that claim.

---

### 2.3 MemoryArena (Feb 2026, Stanford Digital Economy Lab)

**Citation**: "MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks." arXiv:2602.16313.
**URL**: https://arxiv.org/abs/2602.16313 | https://memoryarena.github.io/

**What it measures**: Four agentic task domains with explicitly interdependent subtasks across multiple sessions. The critical design property: tasks cannot be completed without correctly recalling outcomes from prior sessions. Domains include web shopping, group travel planning, progressive information search, and sequential formal reasoning. Average 57 action steps per task, 40k+ tokens of reasoning trace.

**Evaluation protocol**: Task completion rate (binary pass/fail per subtask chain). Compares three agent classes: long-context agents (no external memory), RAG-augmented agents, and external-memory-coupled agents under a unified harness.

**Human eval component**: NO automatic scoring only via task completion oracle. But the tasks themselves were **human-crafted** (unlike LoCoMo or NIAH which are procedurally generated). This gives the scenarios ecological validity that pure synthetic benchmarks lack.

**Cross-session relevance**: VERY HIGH — MemoryArena is structurally the closest existing benchmark to what MERIDIAN targets. The "interdependent multi-session" design is exactly the scenario where CTX's cross-session decision memory (G1) adds value: session 2 cannot succeed without retrieving a decision made in session 1.

**Top-tier cite-ability**: MEDIUM — arXiv only as of April 2026, Stanford affiliation adds credibility. The finding that "state-of-the-art agents exhibit low task completion rates despite strong existing-benchmark performance" is a direct argument for why MERIDIAN's E dimension (downstream task completion) is more diagnostic than retrieval-only metrics.

**Gap vs. MERIDIAN**: MemoryArena's domains are generic (shopping, travel), not coding. However, the "progressive information searching" domain has structural similarity to codebase navigation tasks.

---

### 2.4 MEMTRACK (NeurIPS 2025 SEA Workshop, Patronus AI)

**Citation**: Patronus AI. "MEMTRACK: Evaluating Long-Term Memory and State Tracking in Multi-Platform Dynamic Agent Environments." arXiv:2510.01353. NeurIPS 2025 Scaling Environments for Agents (SEA) Workshop.
**URL**: https://arxiv.org/abs/2510.01353 | https://www.patronus.ai/blog/memtrack

**What it measures**: Long-term memory and state tracking in multi-platform organizational workflows. Each benchmark instance interleaves events from Slack, Linear (issue tracker), and Git — creating a scenario where an agent must reconstruct project state from noisy, cross-platform, temporally interleaved information. Metrics: Correctness, Efficiency (memory operations count), and Redundancy.

**Evaluation protocol**: Mixed — expert-designed scenarios (manual) augmented by scalable agent-based synthesis. Evaluation is automatic via correctness scoring. Best-performing model (GPT-5) achieves only 60% correctness. No human raters at evaluation time.

**Human eval component**: NO at scoring time. YES at scenario design time (expert-driven design for a subset).

**Cross-session relevance**: HIGH — MEMTRACK is the most **coding-adjacent** of the new benchmarks. Slack + Linear + Git is exactly the multi-platform context that CTX partially indexes (git log) and claude-mem partially captures (PostToolUse observations from coding sessions). The Slack/Linear gap is a known limitation of both systems.

**Top-tier cite-ability**: MEDIUM — NeurIPS workshop track, Patronus AI origin (industry lab). Main-track NeurIPS reviewers will know Patronus but may push back on workshop-only status. Use as supporting citation rather than primary benchmark.

**Uniquely relevant claim**: MEMTRACK's "Efficiency" metric (memory operations count) is structurally equivalent to MERIDIAN's A (Accounting) dimension. This gives you external validation for the cost-of-intake framing: claude-mem's one-LLM-call-per-tool-use model will show high Efficiency cost in MEMTRACK-style measurement.

---

### 2.5 MemoryBench (Oct 2025, THUIR / Tsinghua)

**Citation**: "MemoryBench: A Benchmark for Memory and Continual Learning in LLM Systems." arXiv:2510.17281. OpenReview submission.
**URL**: https://arxiv.org/abs/2510.17281 | https://huggingface.co/datasets/THUIR/MemoryBench

**What it measures**: Memory and continual learning — how well LLM systems improve from user feedback over time. Categorizes memory along declarative (facts) vs. procedural (skill/process) axes, with explicit and implicit feedback signals. Multi-domain, multi-language dataset.

**Evaluation protocol**: Simulated user feedback via a User Simulator module; performance evaluated on held-out test queries after N feedback interactions. Fully automatic.

**Human eval component**: NO — all simulated. The User Simulator approximates human feedback behavior but is not actual human annotation.

**Cross-session relevance**: MEDIUM — focuses on within-system learning/updating rather than retrieval of past decisions. More relevant to claude-mem's LLM-summarized observation approach (which could theoretically update its summaries) than to CTX's static BM25 index.

**Top-tier cite-ability**: MEDIUM — arXiv + OpenReview, Tsinghua affiliation is credible. No conference acceptance confirmed as of this survey.

**Key finding relevant to CTX/claude-mem**: "Existing memory systems are not good at utilizing procedural knowledge to improve performance." Procedural memory is CTX's G1 layer — knowing *how* decisions were made, not just *what* was decided. This finding supports the claim that neither system is solved and motivates MERIDIAN's I₁ (Intake completeness) dimension.

---

### 2.6 EngramaBench (Apr 2026)

**Citation**: "EngramaBench: Evaluating Long-Term Conversational Memory with Structured Graph Retrieval." arXiv:2604.21229.
**URL**: https://arxiv.org/abs/2604.21229

**What it measures**: Five conversational memory query types across 5 personas, 100 multi-session conversations, 150 queries:
- `single_space`: simple factual recall within one conversation thread
- `cross_space`: integration of facts from multiple conversation threads
- `temporal_cross_space`: temporally-ordered reasoning across multiple threads
- `adversarial`: abstention when no stored memory supports the answer
- `emergent_insight`: synthesis of implicit conclusions not explicitly stated in any session

**Evaluation protocol**: Comparison of Engrama (graph-structured memory) vs. GPT-4o full-context vs. Mem0 (vector retrieval). Scoring appears to be LLM-judge based — no confirmed human rater protocol.

**Human eval component**: UNCLEAR from available sources — no explicit human annotation methodology confirmed. The five query types are the most granular taxonomy seen in this survey.

**Cross-session relevance**: HIGH — the `adversarial` and `emergent_insight` categories directly test failure modes of both CTX and claude-mem: CTX will hallucinate retrieval on adversarial queries (BM25 cannot abstain); claude-mem's LLM summaries may fabricate implicit conclusions for emergent_insight.

**Top-tier cite-ability**: LOW-MEDIUM — arXiv April 2026, no venue confirmed. However, the five-type taxonomy is more granular than LongMemEval's five axes and may be worth citing for the query-type stratification methodology alone.

**Key insight**: The `adversarial` category (correct abstention) maps directly to MERIDIAN's I₂ (Integrity under drift) — the ability to say "I don't know" when the memory is stale or absent. Neither CTX nor claude-mem currently implements abstention signaling. This is a paper contribution opportunity.

---

### 2.7 LoCoMo (CVPR 2024, Snap Research) — Precise Axes

**Citation**: "Evaluating Very Long-Term Conversational Memory of LLM Agents." arXiv:2402.17753. CVPR 2024.
**URL**: https://arxiv.org/abs/2402.17753 | https://snap-research.github.io/locomo/

**What it measures** (precise axes — this was previously known by name only):
- 300 turns, ~9K tokens, up to 35 sessions per conversation
- Three task types:
  1. QA with five reasoning subtypes: single-hop, multi-hop, temporal, commonsense, adversarial
  2. Event Graph Summarization (causal + temporal understanding of conversation arc)
  3. Multimodal Dialog Generation

**Human ceiling**: QA task human F1 = 87.9. Open LLMs (Mistral-7B through GPT-4) achieve 13.9–32.1 F1 — a massive gap.
**Conversation data**: Human-verified and human-edited for long-range consistency. This makes LoCoMo one of the few benchmarks where the underlying data has genuine human annotation.

**Human eval component**: PARTIAL — human annotators verified and edited the conversations. Evaluation scoring is automatic (F1 for QA, ROUGE/BLEU for summarization). No human preference or Likert scoring at eval time.

**Cross-session relevance**: HIGH for G1 (decision memory recall across sessions). The temporal QA subtype directly tests what CTX's G1 is designed for. The adversarial subtype exposes when a memory system confidently retrieves wrong information.

**Top-tier cite-ability**: HIGH — CVPR 2024 (top vision conference, but long-context memory is evaluated there). Snap Research origin. Mem0 reports 66.9% on LoCoMo vs. 52.9% for OpenAI memory, giving you a public baseline to position against.

**Key precision for MERIDIAN**: LoCoMo's temporal QA subtype is a strict superset of MERIDIAN M-dimension keyword recall — it requires not just retrieving a past decision but placing it in the correct temporal order relative to other decisions. If you run CTX on LoCoMo's temporal QA subset, you can directly compare against the Mem0 66.9% baseline.

---

### 2.8 GitGoodBench (arXiv 2025)

**Citation**: "GitGoodBench: Evaluating LLMs on Git History Understanding." arXiv:2505.22583.
**URL**: https://arxiv.org/html/2505.22583v1

**What it measures**: LLM ability to reason over git history for interactive rebase operations. Four axes evaluated by LLM-as-Judge:
1. Commit message quality
2. Logical cohesion within commits
3. Logical progression across commits
4. Commit granularity

**Human eval component**: NO — LLM-as-Judge throughout. However, the tasks (interactive rebase with commit dependency reasoning) are inherently coding-specific.

**Cross-session relevance**: MEDIUM-HIGH — GitGoodBench is the only benchmark surveyed that uses git history as the evaluation substrate directly. CTX's G1 layer is entirely git-log-derived; GitGoodBench provides external validation that git history is a meaningful information source for LLM tasks.

**Top-tier cite-ability**: LOW — arXiv only, no conference placement confirmed. Use as supporting evidence for the design choice of git-log-derived memory, not as a primary benchmark.

---

### 2.9 Memstate Coding Agent Benchmark (Mar 2026, industry blog)

**Citation**: Sandelin, M. "The First Controlled Benchmark of AI Memory in Coding Agents." Medium, March 2026.
**URL**: https://medium.com/@mrsandelin/the-first-controlled-benchmark-of-ai-memory-in-coding-agents-8e0bb776d39e | https://memstate.ai/blog/ai-memory-benchmark-2026

**What it measures**: Multi-session coding agent tasks on a production Python/FastAPI/PostgreSQL codebase (4,895-line main module, 158 Python source files). Three conditions: Memstate (structured versioned memory), Mem0 (vector search), naive vector RAG, no memory. Metrics: fact recall rate, conflict detection rate, task completion efficiency.

**Human eval component**: NONE confirmed — automated evaluation.

**Cross-session relevance**: VERY HIGH — this is the only public benchmark specifically designed for coding agent cross-session memory. Memstate scores 5.3x higher than Mem0 on fact recall (92.2% vs. 17.5%) and 4.7x better on conflict detection (95.0% vs. 20.2%).

**Top-tier cite-ability**: LOW — industry blog post, no peer review. However, the experimental design (controlled conditions on a real codebase with automated metrics) is what MERIDIAN aspires to. You can cite it as "the only prior controlled coding-agent memory benchmark" and then note its limitations (no human eval, single codebase, vendor-authored).

**Critical methodological note**: Memstate's benchmark is authored by Memstate's own team — the same self-authored bias problem the CTX paper explicitly addresses for itself (§8.5). Citing this in the related work section actually strengthens the paper's motivation: "Existing coding-agent memory benchmarks are either absent or vendor-authored; MERIDIAN is the first third-party evaluation."

---

## 3. Precise Axes for Previously Known Benchmarks

### 3.1 NeedleBench (OpenCompass) — Precise Axes

Three task types (V1 and V2):
- **Single-Needle Retrieval (S-RT)**: one fact hidden at varying depth in a long document. Evaluation: exact string match on the extracted needle.
- **Multi-Needle Retrieval (M-RT)**: multiple facts hidden; model must retrieve ALL of them. Evaluation: exact match on each needle independently.
- **Multi-Needle Reasoning (M-RS)**: multiple facts hidden; model must integrate them to answer a derived question. Evaluation: exact match on the final answer. V2 upgrade replaces real-world needles with fictional information to eliminate innate-knowledge bias.

**Strictly automatic**: YES — all three tasks use exact-match scoring. No graded relevance, no human raters.

**Cross-session relevance**: LOW — NeedleBench tests within-context retrieval (one document, one session). It is not a cross-session benchmark. It measures the memory of a context window, not the memory of a retrieval system. Relevant only for testing whether CTX's context injection itself is faithfully consumed by the LLM (i.e., "did the model read what CTX injected?"), not whether CTX retrieved the right item.

**Verdict for MERIDIAN**: Useful as a sanity check for the LLM backend (if the model cannot pass NeedleBench with the injected context as the haystack, then E-dimension failures are the model's fault, not the memory system's). Not a primary benchmark for CTX vs. claude-mem comparison.

---

### 3.2 BABILong (NeurIPS 2024) — Precise Axes

**Design**: Embeds structured reasoning tasks (bAbI-style: path finding, counting, spatial reasoning, temporal ordering, argument resolution) inside noise text that scales from 1K to 50M tokens. 20 task types.

**Strictly automatic**: YES — exact match on fact retrieval and compositional reasoning answers. No graded relevance.

**Multi-needle / adversarial variant**: YES — the "distractor" noise contains semantically similar but wrong facts, creating an adversarial retrieval challenge that surfaces false positive retrieval.

**Cross-session relevance**: NONE — entirely single-session (in-context). Like NeedleBench, BABILong tests context-window utilization, not cross-session external memory retrieval.

**Verdict for MERIDIAN**: Not directly applicable. Can be used as a methodological reference for "noise-injected adversarial retrieval" design, which MERIDIAN's adversarial suite (§4.7) borrows from.

---

### 3.3 MRCR (Multi-Round Coreference Resolution) — Precise Axes

**Design**: Long conversations where multiple similar requests appear across rounds; model must retrieve the specific response from the correct round without confusing it with similar responses from other rounds. The "needle" is a prior model output, not a static fact — making MRCR the most dialogue-native of the NIAH family.

**Scoring**: Hybrid — the retrieved string prefix is evaluated by **exact match** (hard constraint), but the rest of the response is scored by **similarity score** (soft constraint). This makes MRCR one of the few benchmarks in this class with partial-credit scoring.

**Variants**: MRCR V2 (2-needle, 8-needle variants, up to 1M context window). The 8-needle variant is the closest existing public benchmark to multi-session memory with multiple competing candidates.

**Cross-session relevance**: MEDIUM — MRCR is within-context (very long conversations), not cross-session. However, the "multiple competing similar outputs" structure directly models the challenge CTX faces when multiple git commits discuss similar topics (e.g., three separate "switched to BM25" commits) and the model must retrieve the most recent/relevant one.

**Strictly automatic**: MOSTLY — exact match on prefix + similarity score on suffix. No human raters.

**Verdict for MERIDIAN**: The MRCR 8-needle variant is the best existing public benchmark for testing CTX's ability to disambiguate among multiple similar memories. Recommend including a MRCR-inspired "competing memories" adversarial subset in the MERIDIAN adversarial suite (§4.7).

---

### 3.4 LongMemEval (ICLR 2025) — Precise Axes (Completed)

Five dimensions (already known), now with precise evaluation protocol details:

| Dimension | Evaluation method | Human eval? |
|-----------|------------------|-------------|
| Information extraction | F1 on specific fact recall | NO — automatic F1 |
| Multi-session reasoning | F1 on questions requiring synthesis across sessions | NO — automatic F1 |
| Temporal reasoning | F1 on time-ordered fact questions | NO — automatic F1 |
| Knowledge updates | Accuracy on "what is the current value after updates" | NO — automatic |
| Abstention | Accuracy on "I don't know" responses to unanswerable questions | NO — automatic |

**Human annotation**: Used to construct the benchmark (human annotators conducted the sessions and created the Q&A pairs) but not at evaluation time. Human ceiling on QA: ~87-90% accuracy; commercial systems achieve ~60-70%.

**Cross-session design**: YES — explicitly multi-session. The benchmark simulates a user interacting with an assistant across many sessions over time, then asking questions that require recalling information from earlier sessions.

**Coding-specific**: NO — conversational domain (personal assistant tasks, not coding). However, the multi-session temporal reasoning dimension is directly adaptable to coding decision memory.

**For MERIDIAN**: LongMemEval's Abstention dimension is the highest-priority unmapped dimension in MERIDIAN. Neither CTX nor claude-mem currently implements abstention — they will both confidently return wrong results when queried for information they never captured.

---

## 4. Human Evaluation Protocols — Inventory

Of all benchmarks surveyed, only the following include genuine human judgment at evaluation time (not just at construction time):

| Benchmark | Human eval type | What humans judge |
|-----------|----------------|-------------------|
| LoCoMo | Construction-time annotation | Conversation coherence and consistency |
| AMA-Bench (real track) | Construction-time QA authoring | Expert-written ground truth |
| MemoryArena | Construction-time task design | Task interdependency design |
| LongMemEval | Construction-time session authoring | Session naturalness and Q&A correctness |

**Finding**: There are currently NO published memory benchmarks with live human preference evaluation (Likert scales, pairwise A/B preferences, or "would you have wanted to recall this?" judgments) at evaluation time. This is a genuine gap.

**Implication for MERIDIAN**: The human-in-the-loop component described in the MERIDIAN design (§4.5 human arbitration, §4.2 double annotation) is genuinely novel for this benchmark class. A reviewer from the NLP/IR community will recognize this as a contribution. The "피부로 와닿는" (user-felt quality) dimension simply does not exist in any current benchmark.

---

## 5. Cross-Session Memory Benchmarks — Alternatives to LongMemEval

| Benchmark | Sessions | Domain | Human eval | Cite-able at top tier |
|-----------|----------|--------|-----------|----------------------|
| LongMemEval | Multi (up to 500 questions) | Conversational | Construction-time | HIGH (ICLR 2025) |
| LoCoMo | Up to 35 sessions | Conversational | Construction-time | HIGH (CVPR 2024) |
| MemoryAgentBench | Multi-turn incremental | Domain-agnostic | None | HIGH (ICLR 2026) |
| MemoryArena | Multi-session (4 domains) | Agentic (generic) | Construction-time | MEDIUM (arXiv) |
| AMA-Bench | Long-horizon agentic | Agentic (generic) | Expert QA construction | MEDIUM (ICLR 2026 workshop) |
| EngramaBench | 100 conversations × 5 personas | Conversational | Unclear | LOW-MEDIUM (arXiv) |
| MEMTRACK | Multi-platform timeline | Coding-adjacent (Slack+Git) | Expert scenario design | MEDIUM (NeurIPS 2025 workshop) |
| Memstate benchmark | Multi-session coding tasks | Coding-specific | None | LOW (industry blog) |

**Recommended alternatives to LongMemEval** for cross-session memory eval:
1. **LoCoMo** — the only top-tier (CVPR) multi-session conversational memory benchmark with human-verified data. Use for G1 temporal reasoning comparison against Mem0's 66.9% public baseline.
2. **MemoryArena** — the only benchmark measuring memory within actual agent-environment interaction loops (not dialogue). Use to demonstrate MERIDIAN's E-dimension design is consistent with community methodology.

---

## 6. "User-Felt" Memory — Gap Analysis

**Finding**: No published RCT, within-subjects user study, or controlled experiment with real developer subjects evaluating coding-agent memory quality exists as of April 2026. The closest examples:

1. **Memstate blog post (Mar 2026)**: Controlled conditions on a real codebase, but automated metrics only, vendor-authored.
2. **Cursor's CursorBench** (blog post): Uses "Cursor Blame" to trace committed code back to agent requests, measuring whether the agent's contribution was accepted. Closest to real-world developer preference signal, but not a memory benchmark.
3. **MemoryBench (THUIR)**: Has a User Simulator that approximates human feedback but is not actual human annotation.

**The gap is real and is a MERIDIAN contribution**: The 100 hand-labeled real sessions in MERIDIAN §4.1 (with the "피부로 와닿는" criterion — "a human reading the retrieved memory should be able to say yes, this is what I would have wanted") constitute the field's first ecological validity component for cross-session coding-agent memory. No existing benchmark provides this.

---

## 7. Benchmark Coverage Summary

| MERIDIAN dimension | Best existing public benchmark | Gap |
|--------------------|-------------------------------|-----|
| M (Memory recall) | LongMemEval, LoCoMo (temporal QA) | Chat domain, not coding decisions |
| E (Effectiveness / downstream) | SWE-bench-Lite, MemoryArena | Not memory-isolated (memory confounded with agent capability) |
| R (Responsiveness / latency) | None | No latency dimension in any memory benchmark |
| I₁ (Intake completeness) | AMA-Bench (real track) | Not coding-specific |
| D (Determinism) | None | No existing benchmark measures replay divergence |
| I₂ (Integrity under drift) | LongMemEval (knowledge updates + abstention), EngramaBench (adversarial) | Not coding-specific |
| A (Accounting / cost) | MEMTRACK (Efficiency metric) | Not cost-in-dollars |
| N (Neutrality / worst-slice) | None | No existing benchmark explicitly reports worst-slice |

---

## 8. Recommendations — 3–4 Benchmark Stack

### Recommendation: Four-Benchmark Protocol

This stack optimizes for both (a) NLP reviewer citation recognition and (b) user-felt quality ("피부로 와닿는"):

#### Tier A — Primary (cite in abstract and results section)

**1. LongMemEval (ICLR 2025)**
- Rationale: Highest-credibility venue for cross-session memory. Five axes (extraction, multi-session reasoning, temporal, knowledge updates, abstention) map cleanly onto MERIDIAN M + I₂. 500 questions gives statistical power.
- Use: Run CTX and claude-mem on LongMemEval's temporal reasoning and multi-session reasoning subsets (converting the dialogue-domain sessions into simulated coding sessions via a domain adapter). Compare against Mem0's 66.9% LoCoMo baseline as external anchor.
- Reviewer lens: An ICLR/NeurIPS reviewer will immediately recognize LongMemEval. It gives your paper an anchor to community-standard numbers.

**2. MemoryAgentBench (ICLR 2026)**
- Rationale: Best technical match to the CTX/claude-mem architectural split. The "conflict resolution" (Competency 4) axis is the exact scenario where LLM-summarized memory (claude-mem) is expected to degrade: when a developer reverses a prior decision. Automatic evaluation, well-specified, publicly available.
- Use: Map MERIDIAN's four conditions ({neither, CTX, claude-mem, both}) onto MemoryAgentBench's conflict resolution subset. Claim that CTX's deterministic BM25 returns the LATEST git commit (correct after reversal) while claude-mem's LLM-summarized summary may average the two decisions (incorrect).
- Reviewer lens: ICLR 2026 acceptance gives top-tier credibility. The paper's own claims about "current memory agents exhibit substantial limitations" support MERIDIAN's motivation.

#### Tier B — Supporting (cite in related work + methodology)

**3. MemoryArena (Feb 2026, Stanford)**
- Rationale: Only benchmark measuring memory within agent-environment interaction loops rather than dialogue. The multi-session interdependence design is structurally identical to MERIDIAN's E-dimension (downstream task completion). Stanford affiliation adds credibility. The finding that "agents perform well on existing memory benchmarks but fail at multi-session task completion" directly justifies MERIDIAN's inclusion of an E dimension beyond standard Recall@K.
- Use: Cite in §2 (related work) as evidence that retrieval-only benchmarks are insufficient. Optionally run a MemoryArena-inspired mini-experiment with coding-domain tasks to validate MERIDIAN's E-dimension design.
- Reviewer lens: Not yet top-tier (arXiv only), but Stanford affiliation and the adversarial finding will be recognized.

**4. MEMTRACK (NeurIPS 2025 workshop, Patronus AI)**
- Rationale: Only benchmark with a coding-adjacent substrate (Slack + Linear + Git). The Efficiency metric (memory operations count) validates MERIDIAN's A (Accounting) dimension independently. The 60% ceiling on GPT-5 demonstrates the task is not trivially solved. Patronus AI is a credible AI safety/evaluation organization.
- Use: Cite in §2 to motivate MEMTRACK-style Efficiency as a cost proxy. Use the Slack+Git substrate as an argument that coding-agent memory systems need to handle multi-platform information, which CTX currently only partially covers (git-only intake vs. claude-mem's PostToolUse intake).
- Reviewer lens: NeurIPS workshop, not main track. Use as supporting citation, not primary benchmark. The Patronus affiliation adds industry credibility.

### What This Stack Achieves

| Goal | How addressed |
|------|--------------|
| Rigorous / cite-able | LongMemEval (ICLR 2025) + MemoryAgentBench (ICLR 2026) are both top-tier accepted papers |
| "피부로 와닿는" (user-felt) | MERIDIAN's own 100 hand-labeled real sessions remain the ONLY user-felt component in any existing benchmark; this stack situates MERIDIAN as advancing the field |
| Adversarial reviewer: "these numbers are cherry-picked" | MemoryArena's finding that agents fail on interdependent tasks (despite high single-metric scores) pre-empts this concern |
| Adversarial reviewer: "you're comparing a research system to a production system unfairly" | MEMTRACK's Efficiency metric gives an independent, non-CTX-authored framing for the cost argument |

---

## 9. Verification Needed (Items Marked [UNCERTAIN] in This Survey)

1. **EngramaBench human eval protocol**: The paper (arXiv:2604.21229) was not fetched in full — human annotation methodology is unconfirmed. Recommend fetching the full paper to verify before citing.

2. **AMA-Bench expert QA authorship details**: The claim that the real-world track uses "expert-curated QA" implies human authorship, but the degree of human involvement (fully human-written vs. human-verified LLM-generated) is not confirmed from search results alone.

3. **LoCoMo evaluation metric for QA**: Confirmed as F1, but the exact tokenization and stopword handling may affect comparability. Fetch the official scoring script from https://snap-research.github.io/locomo/ before running CTX on the benchmark.

4. **Mem0 LoCoMo 66.9% reproducibility**: Multiple practitioners have reported inability to reproduce this number locally; Mem0's co-founder stated the benchmark requires evaluation only on Categories 1–4. Confirm which categories before using as a comparison baseline.

5. **MemoryAgentBench's coding-domain adaptation**: The benchmark repurposes existing NLP datasets (not coding datasets). Confirm whether the EventQA and FactConsolidation datasets can be adapted to coding-decision scenarios before claiming direct comparability.

---

## Sources

- [LongMemEval (ICLR 2025)](https://arxiv.org/abs/2410.10813)
- [MemoryAgentBench (ICLR 2026)](https://arxiv.org/abs/2507.05257) | [GitHub](https://github.com/HUST-AI-HYZ/MemoryAgentBench)
- [AMA-Bench (ICLR 2026 workshop)](https://arxiv.org/abs/2602.22769) | [Project page](https://ama-bench.github.io/)
- [MemoryArena (Feb 2026)](https://arxiv.org/abs/2602.16313) | [Project page](https://memoryarena.github.io/)
- [MEMTRACK (NeurIPS 2025 SEA workshop)](https://arxiv.org/abs/2510.01353) | [Patronus AI blog](https://www.patronus.ai/blog/memtrack)
- [MemoryBench (Oct 2025)](https://arxiv.org/abs/2510.17281) | [Dataset](https://huggingface.co/datasets/THUIR/MemoryBench)
- [EngramaBench (Apr 2026)](https://arxiv.org/abs/2604.21229)
- [LoCoMo (CVPR 2024)](https://arxiv.org/abs/2402.17753) | [Project page](https://snap-research.github.io/locomo/)
- [GitGoodBench](https://arxiv.org/html/2505.22583v1)
- [NeedleBench V2 (OpenCompass)](https://github.com/open-compass/opencompass/blob/main/opencompass/configs/datasets/needlebench_v2/readme.md)
- [Memstate AI Coding Agent Benchmark (Mar 2026)](https://memstate.ai/blog/ai-memory-benchmark-2026)
- [ICLR 2026 MemAgents Workshop](https://openreview.net/pdf?id=U51WxL382H)

## Related
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
- [[projects/CTX/research/20260426-ctx-retrieval-benchmark-synthesis|20260426-ctx-retrieval-benchmark-synthesis]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|20260426-g1-hybrid-rrf-dense-retrieval]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260426-ctx-research-critical-evaluation|20260426-ctx-research-critical-evaluation]]
