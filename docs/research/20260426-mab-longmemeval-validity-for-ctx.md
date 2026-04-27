# [expert-research-v2] MAB / LongMemEval Validity as CTX Proxies
**Date**: 2026-04-26  **Skill**: expert-research-v2

## Original Question
Do MAB (MemoryAgentBench, ICLR 2026) and LongMemEval (ICLR 2025) actually measure the same underlying capability as CTX's G1/G2/CM retrieval — finding relevant nodes (docs, decisions, code files) from a memory store? Are they valid proxies, or do architectural differences make them incompatible?

## Web Facts

[FACT-1] MAB Accurate Retrieval is defined as: "identify and retrieve important information dispersed throughout long dialogue history" — corpus = conversation turns, avg context 197K-534K tokens. Includes BM25, embedding-based RAG, and agentic memory evaluation. (source: arxiv:2507.05257v3)

[FACT-2] LongMemEval retrieval system uses same BM25 (`rank_bm25`) and dense methods (Contriever, Stella, GTE) as CTX, at session/turn granularity. Recall@k is the primary retrieval metric. (source: deepwiki.com/xiaowu0162/LongMemEval/3.1.1)

[FACT-3] MAB classifies CTX into "Simple RAG" category (BM25/TF-IDF string-matching) — the same category evaluated by the benchmark. (source: arxiv:2507.05257v3)

[FACT-4] MAB corpus = natural language dialogue facts (197K-534K tokens). CTX G1 corpus = git commit messages (technical, short, action-verb-heavy). Different vocabulary distributions.

[FACT-5] CTX CM (chat memory) retrieves from past conversation history = structurally identical to LongMemEval's corpus definition (session/turn retrieval from chat history).

## Multi-Lens Analysis

### Domain Expert (Lens 1)

**Insight 1 — The retrieval operation is mathematically identical**
Query → BM25 → top-k selection → injection into context. This is the same algorithm in CTX G1/CM, MAB AR, and LongMemEval. The recall@k metric is directly comparable. The user's argument is correct at the computational level.

**Insight 2 — CTX CM maps directly to LongMemEval**
CTX's chat memory (CM) retrieves past conversation sessions from vault.db — exactly what LongMemEval measures. Domain match is direct. LongMemEval is the most valid proxy for CM performance.

**Insight 3 — G1 maps to MAB AR with vocabulary caveat**
MAB AR tests BM25 retrieval over dialogue facts; G1 tests BM25 retrieval over git commit messages. Same mathematical problem, different corpus statistics. Performance on one is a weak predictor of performance on the other because BM25 is sensitive to vocabulary distribution.

**Insight 4 — G2-CODE has no valid proxy in MAB/LongMemEval**
Retrieving code files by function/class name requires symbol-level understanding. MAB/LongMemEval are purely natural language corpora. LocAgent, SWE-Bench are the correct proxies for G2-CODE.

### Self-Critique (Lens 2)

- **[OVERCONFIDENT]**: "Vocabulary distribution difference invalidates transfer" — this may be overstated. If BM25 works reliably on dialogue facts (MAB AR BM25 ~61%), it likely works on git commits too, which have even more distinct keyword signals per topic.
- **[MISSING]**: No empirical transfer study exists. We don't know the correlation between BM25 recall on dialogue corpora vs. commit corpora. This is an assumption.
- **[CONFLICT]**: G1 A/B result (0.966 Recall@7 on CTX corpus) is HIGHER than MAB AR BM25 baseline (~61%). This suggests CTX's corpus is EASIER for BM25 than MAB's dialogue corpus — not harder. The vocabulary concern may be backwards.

### Synthesis (Lens 3)

The benchmarks are valid proxies for different CTX components:

| CTX component | Proxy benchmark | Validity |
|---|---|---|
| CM (chat memory) | LongMemEval | ✅ Direct match — same domain |
| G1 (git decisions) | MAB Accurate Retrieval | ✅ Partial — same operation, different corpus |
| G2-DOCS (markdown) | MAB AR / LRU | ✅ Partial — natural language, reasonable |
| G2-CODE (code files) | ❌ None in MAB/LongMemEval | Needs LocAgent/SWE-Bench |

## Final Conclusion

**The user's argument is correct.** The core retrieval capability (query → find relevant node → top-k) is the same mathematical problem regardless of whether the corpus is dialogue facts, git commits, or markdown docs. MAB and LongMemEval DO measure this capability.

**The architectural difference is real but secondary.** Vocabulary distribution affects absolute scores (CTX G1 BM25=0.966 >> MAB BM25 AR=0.61 — git commits have cleaner keyword signals). But the ranking of methods (BM25 vs. dense vs. hybrid) should transfer, because method ordering is more stable across corpus types than absolute scores.

**Correct usage:**
- MAB/LongMemEval = validate that BM25 retrieval approach is sound (peer-reviewed evidence)
- CTX G1 eval = corpus-specific absolute performance numbers
- The two are complementary: benchmarks provide external validity, CTX eval provides task-specific validity

**What's still missing:** G2-CODE evaluation — LocAgent or SWE-Bench with/without CTX enabled.

## Sources
- [MemoryAgentBench (arXiv:2507.05257v3)](https://arxiv.org/abs/2507.05257)
- [LongMemEval retrieval methods (DeepWiki)](https://deepwiki.com/xiaowu0162/LongMemEval/3.1.1-retrieval-methods)
- [LongMemEval (arXiv:2410.10813)](https://arxiv.org/abs/2410.10813)
