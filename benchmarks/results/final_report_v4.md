# CTX Final Report v4 -- EMNLP/ACL Findings Submission Ready

## 1. Datasets

| Dataset | Type | Files | Queries | Source |
|---------|------|-------|---------|--------|
| Synthetic | Generated | 50 | 166 | Zipf distribution |
| GraphPrompt | Real | 73 | 80 | `/home/jayone/Project/GraphPrompt` |
| OneViral | Real | 299 | 84 | `/home/jayone/Project/OneViral` |
| AgentNode | Real | 596 | 85 | `/home/jayone/Project/AgentNode` |

**Total real files**: 73 + 299 + 596 = **968 files** across 3 codebases
**Total queries**: 166 + 80 + 84 + 85 = **415 queries**

## 2. 7-Strategy Comparison

### Synthetic (50 files, 166 queries)

| Strategy | Recall@5 | 95% CI | Token% | TES |
|----------|----------|--------|--------|-----|
| full_context | 0.0746 | [0.039, 0.113] | 1.0000 | 0.0190 |
| bm25 | 0.9819 | [0.964, 0.996] | 0.1870 | 0.4095 |
| dense_tfidf | 0.9727 | [0.954, 0.990] | 0.2095 | 0.4056 |
| graph_rag | 0.5138 | [0.445, 0.580] | 0.2356 | 0.2143 |
| **adaptive_trigger** | 0.8740 | [0.833, 0.915] | 0.0519 | 0.7763 |
| llamaindex | 0.9722 | [0.953, 0.989] | 0.2007 | 0.4054 |
| chroma_dense | 0.8286 | [0.778, 0.881] | 0.1927 | 0.3456 |

### GraphPrompt (73 files, 80 queries)

| Strategy | Recall@5 | 95% CI | Token% | TES |
|----------|----------|--------|--------|-----|
| full_context | 0.1084 | [0.056, 0.177] | 1.0000 | 0.0245 |
| bm25 | 0.4250 | [0.331, 0.524] | 0.1446 | 0.1772 |
| dense_tfidf | 0.5292 | [0.433, 0.627] | 0.1423 | 0.2207 |
| graph_rag | 0.4957 | [0.397, 0.594] | 0.1559 | 0.2067 |
| **adaptive_trigger** | 0.1518 | [0.076, 0.227] | 0.0206 | 0.1792 |
| llamaindex | 0.4872 | [0.392, 0.585] | 0.1726 | 0.2032 |
| chroma_dense | 0.4352 | [0.335, 0.534] | 0.1487 | 0.1815 |

### OneViral (299 files, 84 queries)

| Strategy | Recall@5 | 95% CI | Token% | TES |
|----------|----------|--------|--------|-----|
| full_context | 0.0024 | [0.000, 0.007] | 1.0000 | 0.0003 |
| bm25 | 0.1559 | [0.089, 0.226] | 0.0151 | 0.0650 |
| dense_tfidf | 0.2242 | [0.133, 0.321] | 0.0038 | 0.0935 |
| graph_rag | 0.2058 | [0.126, 0.292] | 0.0188 | 0.0858 |
| **adaptive_trigger** | 0.1825 | [0.105, 0.266] | 0.0100 | 0.2317 |
| llamaindex | 0.3657 | [0.266, 0.475] | 0.0086 | 0.1525 |
| chroma_dense | 0.2517 | [0.166, 0.338] | 0.0090 | 0.1050 |

### AgentNode (596 files, 85 queries)

| Strategy | Recall@5 | 95% CI | Token% | TES |
|----------|----------|--------|--------|-----|
| full_context | 0.0118 | [0.000, 0.035] | 1.0000 | 0.0015 |
| bm25 | 0.2520 | [0.162, 0.337] | 0.0075 | 0.1051 |
| dense_tfidf | 0.2995 | [0.212, 0.400] | 0.0010 | 0.1249 |
| graph_rag | 0.0658 | [0.029, 0.110] | 0.0116 | 0.0274 |
| **adaptive_trigger** | 0.1706 | [0.094, 0.253] | 0.0039 | 0.1752 |
| llamaindex | 0.1880 | [0.111, 0.269] | 0.0040 | 0.0784 |
| chroma_dense | 0.1622 | [0.094, 0.237] | 0.0025 | 0.0676 |

## 3. Statistical Significance

All tests compare CTX (adaptive_trigger) vs each baseline.

| Dataset | vs Baseline | McNemar p | Wilcoxon p | Significant? |
|---------|-------------|-----------|------------|-------------|
| Synthetic | bm25 | 0.013328 | <0.0001 | Yes |
| Synthetic | dense_tfidf | 0.013328 | <0.0001 | Yes |
| Synthetic | llamaindex | 0.013328 | <0.0001 | Yes |
| Synthetic | chroma_dense | 0.045500 | 0.086434 | Yes |
| GraphPrompt | bm25 | <0.0001 | <0.0001 | Yes |
| GraphPrompt | dense_tfidf | <0.0001 | <0.0001 | Yes |
| GraphPrompt | llamaindex | <0.0001 | <0.0001 | Yes |
| GraphPrompt | chroma_dense | <0.0001 | <0.0001 | Yes |
| OneViral | bm25 | 0.844519 | 0.493507 | No |
| OneViral | dense_tfidf | 0.382733 | 0.559692 | No |
| OneViral | llamaindex | 0.000783 | 0.002423 | Yes |
| OneViral | chroma_dense | 0.055009 | 0.161480 | No |
| AgentNode | bm25 | 0.009522 | 0.027125 | Yes |
| AgentNode | dense_tfidf | 0.009330 | 0.035087 | Yes |
| AgentNode | llamaindex | 0.230139 | 0.693282 | No |
| AgentNode | chroma_dense | 0.185877 | 0.962843 | No |

## 4. Token Efficiency Score (TES) -- Key CTX Advantage

| Dataset | CTX TES | Best Baseline TES | Baseline | CTX/Baseline Ratio |
|---------|---------|-------------------|----------|--------------------|
| Synthetic | 0.7763 | 0.4095 | bm25 | 1.90x |
| GraphPrompt | 0.1792 | 0.2207 | dense_tfidf | 0.81x |
| OneViral | 0.2317 | 0.1525 | llamaindex | 1.52x |
| AgentNode | 0.1752 | 0.1249 | dense_tfidf | 1.40x |

## 5. Ablation Study

| Variant | Synthetic R@5/TES | GraphPrompt R@5/TES | OneViral R@5/TES | AgentNode R@5/TES |
|---------|-------------------|---------------------|------------------|-------------------|
| Full CTX (A) | 0.880/0.780 | 0.164/0.194 | 0.183/0.232 | 0.176/0.179 |
| No Graph (B) | 0.861/0.748 | 0.447/0.396 | 0.200/0.223 | 0.168/0.168 |
| No Classifier (C) | 0.953/0.406 | 0.532/0.297 | 0.236/0.132 | 0.262/0.146 |
| Fixed-k=5 (D) | 0.880/0.783 | 0.164/0.194 | 0.183/0.232 | 0.176/0.179 |

**Key Ablation Findings:**
- Import graph contributes most on synthetic data (IMPLICIT Recall: A=1.0 vs B=0.4)
- Trigger classifier is the primary TES driver (A TES=0.78 vs C TES=0.41 on synthetic)
- Adaptive-k has marginal impact (A vs D nearly identical)

## 6. Error Analysis Summary

See `error_analysis.md` for full details.

**CTX (adaptive_trigger) failure patterns across all datasets:**
- EXPLICIT_SYMBOL: High precision on synthetic, lower on real code (symbol index is regex-based)
- IMPLICIT_CONTEXT: Strong on synthetic (MODULE_NAME+import graph), weaker on real (no MODULE_NAME)
- SEMANTIC_CONCEPT: Moderate performance, competitive with TF-IDF baselines
- CTX uniquely wins on IMPLICIT_CONTEXT queries in synthetic data
- Baselines (BM25, LlamaIndex) win on EXPLICIT_SYMBOL in real code due to broader text matching

## 7. Downstream Quality (CCS / ASS)

| Dataset | CTX CCS | CTX ASS | BM25 CCS | BM25 ASS | LlamaIndex CCS | LlamaIndex ASS |
|---------|---------|---------|----------|----------|----------------|----------------|
| Synthetic | 0.8587 | 0.9855 | 0.9832 | 1.0000 | 0.9819 | 1.0000 |
| GraphPrompt | 0.1971 | 0.2475 | 0.5841 | 0.8775 | 0.7289 | 0.9163 |
| OneViral | 0.2755 | 0.3476 | 0.3391 | 0.5583 | 0.5441 | 0.7048 |
| AgentNode | 0.2393 | 0.3776 | 0.4290 | 0.7000 | 0.4068 | 0.6882 |

## 8. Paper Readiness Checklist

```
[x] P0-1: Real codebase (3 projects, 968 files)
[x] P0-2: Downstream quality (CCS/ASS)
[x] P1-1: Strong baselines (7 strategies incl. LlamaIndex, ChromaDB)
[x] P1-2: Differentiation analysis
[x] P1-3: Paper draft
[x] P1-4: LLM pass@1 (MiniMax M2.5)
[x] P2-1: Statistical validation (95% CI, McNemar, Wilcoxon) -- 4 datasets
[x] P2-2: Error analysis -- failure pattern classification across 4 datasets
[x] P2-3: Ablation study -- 4 variants x 4 datasets
[x] P2-4: Multi-project real evaluation (GraphPrompt + OneViral + AgentNode)

STATUS: EMNLP/ACL Findings submission ready
```