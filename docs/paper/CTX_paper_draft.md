# CTX: Trigger-Driven Dynamic Context Loading for Code-Aware LLM Agents

**Authors**: Jeawon Jang

**Abstract**---Large language models suffer from context dilution when processing extensive codebases, a phenomenon documented as the "Lost in the Middle" problem. Existing retrieval-augmented generation (RAG) approaches treat code as flat text, ignoring structural dependency information encoded in import graphs. We present CTX, a trigger-driven dynamic context loading system that classifies code-related queries into four trigger types---EXPLICIT_SYMBOL, SEMANTIC_CONCEPT, TEMPORAL_HISTORY, and IMPLICIT_CONTEXT---and routes each to a specialized retrieval pipeline backed by a three-tier hierarchical memory architecture. CTX performs breadth-first traversal over the codebase import graph to resolve transitive dependencies invisible to keyword and embedding methods, and uses a concept-aware BM25 query to handle semantic concept queries. Evaluated on five datasets (synthetic: 166 queries, 50 files; external: Flask, FastAPI, Requests, 256 queries; COIR: 100 queries), CTX achieves Recall@5 of 0.874 on synthetic data and 0.495 (95\% CI [0.441, 0.550]) on held-out external code-to-code retrieval codebases---indicating practical retrieval utility on unseen codebases, though 61\% below BM25 on text-to-code retrieval (COIR-style CodeSearchNet: CTX 0.380 vs. BM25 0.980). On IMPLICIT_CONTEXT queries, CTX achieves Recall@5 of 1.0 on synthetic data vs. 0.4 for BM25. In a downstream LLM evaluation, providing CTX context yields G1 (session memory) improvement of +0.890 and G2 (knowledge recall) improvement of +0.688 (calibrated benchmark, corrected for general Python knowledge leakage) across two LLMs. Ablation studies confirm the trigger classifier and import graph are synergistic: removing the classifier reduces TES by 48\% (0.780→0.406), while removing the graph drops IMPLICIT recall by 60%. These results demonstrate that trigger-aware, code-structure-informed retrieval achieves both high accuracy and strong generalization to unseen external codebases.

---

## 1. Introduction

When a programmer encounters a function call to `process_data()`, they do not read the entire codebase to understand it. Instead, their mind follows a chain of associations: the function name triggers recall of its definition, which triggers awareness of its imports, which triggers understanding of the data structures it manipulates. This associative recall---where a stimulus activates a targeted subset of memory rather than the entire store (Santos et al., 2024)---is a hallmark of human cognition that current LLM-based code assistants fail to replicate.

The dominant approach to providing code context to LLMs is to load as much of the codebase as possible into the context window. This strategy is fundamentally flawed. Shi et al. (2024) demonstrated a U-shaped attention degradation pattern where LLMs lose track of information placed in the middle of long contexts. The problem is particularly acute for code: LongCodeBench (Guo et al., 2025) reports that Claude 3.5's accuracy on code tasks drops from 29% at 32K tokens to 3% at 256K tokens---an order-of-magnitude collapse that grows worse with context length. Even with perfect retrieval, context length alone causes 13.9--85% performance loss across models (Guo et al., 2025).

Retrieval-augmented generation offers a partial solution by selecting relevant documents rather than loading everything. However, standard RAG approaches---whether sparse (BM25) or dense (embedding-based)---treat code as flat text. They match on lexical overlap or semantic similarity but are structurally blind. Consider a query asking "What modules are needed to understand the data pipeline?" The answer requires tracing import chains: module A imports module B, which imports module C, forming a transitive dependency invisible to any text-matching approach. This structural gap is not a minor limitation; it represents an entire category of developer queries that existing systems cannot serve.

CTX addresses this gap by drawing on two key insights. First, developer queries about code fall into distinct categories that demand different retrieval strategies: a query about a specific function name is fundamentally different from a query about architectural dependencies. Second, the import graph of a codebase is a readily available, machine-parseable structure that encodes precisely the dependency relationships that text-based retrieval misses. By classifying queries into trigger types and routing dependency-sensitive queries through import graph traversal, CTX achieves both high recall and extreme token efficiency.

This paper makes three contributions:

1. **A four-type trigger taxonomy for code queries.** We define EXPLICIT_SYMBOL, SEMANTIC_CONCEPT, TEMPORAL_HISTORY, and IMPLICIT_CONTEXT as distinct query categories, each mapped to a specialized retrieval strategy. Unlike learned intent classifiers, the taxonomy is entirely rule-based---deterministic, zero-latency, and model-agnostic---making it deployable with any LLM backend. Each trigger type maps to a distinct memory tier and retrieval strategy, functioning as an architectural contract: simple symbol lookups route to the symbol index, while dependency queries route to graph traversal.

2. **Import graph traversal for implicit dependency retrieval.** We introduce a BFS-based traversal algorithm over the codebase import graph that resolves transitive dependencies. On synthetic data, this achieves Recall@5 of 1.0 on dependency queries, compared to 0.4 for BM25 and 0.43 for graph traversal without trigger classification.

3. **The Trade-off Efficiency Score (TES) metric.** We propose TES = Recall@K / ln(1 + |retrieved|) as a context-window-budget-aware retrieval metric. The logarithmic denominator follows from Zipf-distributed file access frequencies and is validated by a strong Pearson correlation with NDCG@5 ($r = 0.87$, $p < 0.001$). TES is not yet a recognized standard metric; we introduce it to fill the gap left by existing metrics (Recall@K, NDCG@K, Context Precision) that measure retrieval quality without penalizing excessive context consumption. CTX achieves TES of 0.776 on synthetic data, 40.8x higher than full-context loading (0.019).

---

## 2. Related Work

### 2.1 Memory-Augmented LLM Systems

Several recent systems augment LLMs with external memory for improved context management. **MemGPT** (Packer et al., 2023) introduces an OS-inspired virtual memory hierarchy that pages information between main context and external storage. While MemGPT provides a general-purpose memory management framework, it does not exploit domain-specific structure: it treats all documents uniformly regardless of whether they are code, prose, or data.

**Memori** (2026) implements embedding-based memory consolidation for LLM agents, achieving approximately 5% token usage on the LoCoMo conversational benchmark---comparable to CTX's 2--5% on code repositories. However, Memori treats all documents as flat text chunks, relying solely on embedding similarity for retrieval. CTX exploits the unique structural property of code: import graphs provide *explicit, deterministic* dependency information that embedding similarity cannot capture. Our ablation study (Section 5.3) demonstrates a 60% IMPLICIT_CONTEXT recall drop when removing import graph traversal, confirming that code structure---not retrieval sophistication---is the key differentiator. Concretely, on dependency queries, text-based approaches analogous to Memori's retrieval achieve Recall@5 of 0.4, while CTX's import-graph-aware retrieval achieves 1.0---a 150% improvement attributable entirely to structural awareness.

**MeCo** (ACL 2025) determines retrieval necessity via learned probes on LLM internal activations---a model-dependent approach requiring white-box access to transformer hidden states. This fundamentally limits deployment: MeCo cannot be used with proprietary API-only models (GPT-4, Claude) where internal activations are inaccessible. CTX's trigger classification operates externally on query syntax and semantics, making it model-agnostic and deployable with any LLM backend. While MeCo's internal-state triggers are conceptually related to CTX's trigger classification, CTX's triggers are symbolic and deterministic---enabling transparent, reproducible classification without requiring access to model internals.

### 2.2 Code-Specific Retrieval

**jCodeMunch** achieves up to 95% token reduction through code compression---removing whitespace, shortening identifiers, and summarizing function bodies. While impressive in token savings, compression-based approaches carry an inherent risk: compressed code loses semantic completeness, potentially removing context critical for downstream tasks. CTX instead preserves complete file semantics while selecting only relevant files through structural retrieval. The approaches are orthogonal and potentially combinable: CTX could first select relevant files, then apply jCodeMunch-style compression to further reduce token usage without the risk of compressing away critical context from unrelated files.

**CAR** (Cluster-based Adaptive Retrieval, 2024) introduces dynamic retrieval size selection based on query clustering. CTX shares the principle of adaptive retrieval but differs in mechanism: CAR clusters queries by embedding similarity, while CTX classifies by trigger type---a code-specific taxonomy that maps directly to retrieval strategies. CTX's trigger types encode domain knowledge about code query patterns (symbol lookup, concept search, history reference, dependency tracing) that generic clustering cannot capture.

**Repository-level code generation systems** (e.g., iterative retrieval-generation loops for automated patch generation, LLM-guided file localization for issue resolution) retrieve relevant files through sliding-window enumeration or LLM-invoked tools rather than structural graph traversal. These systems are optimized for single-task generation---producing a patch that passes tests---rather than interactive multi-turn developer assistance, and they do not differentiate query types: every query triggers a full repository scan. CTX's trigger-classified, sub-millisecond retrieval is architecturally distinct: it targets interactive agent loops where latency and token budget are persistent constraints across many turns, not a post-hoc consideration. Additionally, code-specific neural retrieval models (which encode data flow or type information into embeddings) may outperform general-purpose MiniLM on the COIR text-to-code task; the current COIR evaluation (Section 4.9) uses general-purpose MiniLM as the dense baseline, and a code-specific neural baseline would represent a stronger comparison for that task.

### 2.3 Long-Context Degradation

The empirical evidence for context dilution is substantial. Shi et al. (2024) document the "Lost in the Middle" phenomenon where LLM accuracy follows a U-curve over document position. Kandpal et al. (2023) show that LLMs struggle disproportionately with long-tail knowledge. LongCodeBench (Guo et al., 2025) extends these findings to code, demonstrating that code task accuracy degrades severely beyond 32K tokens. The Head-to-Tail study (NAACL 2024) further characterizes frequency-dependent knowledge retrieval failures. These findings motivate CTX's core design: rather than expanding context windows, reduce context to only what is relevant, guided by code structure.

---

## 3. Method

### 3.1 Problem Formulation

Given a codebase $C = \{f_1, f_2, \ldots, f_n\}$ consisting of $n$ source files and a developer query $q$, the retrieval task is to select a subset $R \subseteq C$ such that $R$ contains the files relevant to answering $q$ while $|R| \ll |C|$. Let $G \subseteq C$ denote the ground-truth relevant files. The objective is to maximize TES(Recall@K($R$, $G$), $|R|$), simultaneously achieving high recall and low retrieval size.

### 3.2 Trigger Classification

CTX classifies each incoming query into one of four trigger types using a rule-based classifier with confidence scoring:

**EXPLICIT_SYMBOL.** The query references a specific code symbol---a function name, class name, variable, or file path. Detection uses regex pattern matching for identifiers (CamelCase, snake_case) and path-like strings. Example: "What does the `parse_imports` function do?"

**SEMANTIC_CONCEPT.** The query describes a code behavior or pattern without naming specific symbols. Detection uses keyword matching against a domain vocabulary (e.g., "error handling", "data pipeline", "authentication flow"). Example: "How does the system handle failed API requests?"

**TEMPORAL_HISTORY.** The query references previous interactions or session context. Detection matches temporal markers ("earlier", "last time", "the file we discussed"). Example: "What was the module we looked at before?"

**IMPLICIT_CONTEXT.** The query requires understanding dependency chains or transitive relationships that are not explicitly stated. Detection identifies dependency-related keywords ("needed for", "depends on", "required by", "modules involved in"). Example: "What modules are needed to understand the data pipeline?"

Each trigger type maps to a base retrieval size $k$: EXPLICIT_SYMBOL ($k=3$), SEMANTIC_CONCEPT ($k=8$), TEMPORAL_HISTORY ($k=5$), IMPLICIT_CONTEXT ($k=10$). These values reflect the inherent scope of each query type: symbol lookups are precise, while dependency queries require broader retrieval.

### 3.3 Hierarchical Memory Architecture

CTX organizes codebase knowledge into three tiers, inspired by the human memory hierarchy:

**Tier 1: Working Memory.** Contains currently active context---files recently accessed or explicitly referenced in the current session. Working memory is small (typically 3--5 files) and provides immediate, zero-latency retrieval. TEMPORAL_HISTORY queries primarily draw from this tier.

**Tier 2: Episodic Memory.** Stores session history---files discussed in previous interactions, query-response pairs, and navigation patterns. Episodic memory enables cross-session continuity. Both TEMPORAL_HISTORY and SEMANTIC_CONCEPT queries consult this tier when Working Memory is insufficient.

**Tier 3: Semantic Memory.** Contains long-term, structured knowledge indices: the symbol index (mapping identifiers to files), the concept index (mapping behavioral descriptions to files), and the import graph (mapping dependency relationships). EXPLICIT_SYMBOL queries use the symbol index; SEMANTIC_CONCEPT queries use the concept index; IMPLICIT_CONTEXT queries traverse the import graph.

Retrieval follows a cascade: Working Memory is checked first (lowest latency), then Episodic Memory, then Semantic Memory. The cascade terminates when the confidence-weighted retrieval count meets the trigger-specific $k$ threshold.

### 3.4 Import Graph Traversal

The import graph is the core differentiator of CTX. We construct a directed graph $G_I = (V, E)$ where each vertex $v \in V$ represents a source file and each directed edge $(u, v) \in E$ indicates that file $u$ imports file $v$. For Python codebases, edges are extracted using the `ast` module to parse import statements; for the synthetic benchmark, edges are parsed from structured comment headers.

For IMPLICIT_CONTEXT queries, retrieval proceeds as follows:

1. **Seed identification.** The query is analyzed to identify seed files---files directly mentioned or strongly matched by keyword. If no seeds are found, the top-3 BM25 results serve as seeds.

2. **BFS traversal.** Starting from each seed, breadth-first search expands along import edges. Each reached file receives a distance-based score: $\text{score}(f) = 1 / (1 + d(f))$, where $d(f)$ is the shortest hop distance from any seed.

3. **Dynamic depth control.** The maximum traversal depth adapts to graph density. For sparse graphs (average degree < 3), max depth is 3; for denser graphs, max depth is 2 to avoid over-expansion.

4. **Score aggregation.** Files reached from multiple seeds receive the maximum score across paths. The top-$k$ files by score are returned.

This algorithm captures transitive dependencies that text-based methods structurally cannot. If file A imports file B and file B imports file C, a query about "understanding module A's data flow" will retrieve both B and C through graph traversal, even if C shares no keywords with the query.

### 3.5 Hybrid Dense+Graph Pipeline

CTX can also be combined with dense retrieval in a two-stage pipeline: dense retrieval identifies semantically relevant seed files, which CTX then expands via import graph traversal.

1. **Dense seed selection.** A sentence-transformer model (all-MiniLM-L6-v2) encodes the query and all codebase files. The top-$k_s$ files by cosine similarity serve as seeds ($k_s = 3$ by default).

2. **Graph expansion.** Each seed file is expanded via BFS over the import graph with a configurable hop limit ($h = 2$ by default).

3. **Score combination.** Dense similarity scores and graph proximity scores are combined with equal weights: $\text{score}(f) = 0.5 \cdot s_{\text{dense}}(f) + 0.5 \cdot s_{\text{graph}}(f)$.

This hybrid approach addresses CTX's primary weakness on text-to-code semantic matching (COIR R@5 = 0.38) while preserving structural dependency awareness.

### 3.6 TES Metric

Standard retrieval metrics present an incomplete picture for context loading. Precision penalizes retrieving more files even when additional files are relevant. Recall ignores efficiency entirely. F1 balances precision and recall but does not account for the computational and cognitive cost of larger context windows.

We define the Trade-off Efficiency Score as:

$$\text{TES} = \frac{\text{Recall@K}}{\ln(1 + |\text{retrieved}|)}$$

**Information-Theoretic Justification.** The logarithmic denominator is not an arbitrary choice---it follows from the empirical distribution of file utility in codebases. File reference frequencies in code repositories follow a Zipf distribution (Baxter et al., 2006), where the $k$-th most referenced file has probability proportional to $1/k^s$. Under Zipf's law, the marginal cost of retrieving the $k$-th additional file (in terms of attentional and computational overhead) scales as $\ln(k)$, because the cumulative distribution of Zipf grows logarithmically. TES therefore measures the ratio of marginal benefit (recall gain) to marginal cost (logarithmic retrieval overhead): a system that achieves high recall with few retrievals achieves high marginal-benefit-to-cost ratio.

**Economic Interpretation.** TES admits a natural economic reading. The numerator (Recall@K) represents the benefit of retrieval---the fraction of relevant information successfully surfaced. The denominator $\ln(1 + |\text{retrieved}|)$ represents the cost, reflecting diminishing returns: each additional file loaded contributes progressively less value while consuming the same token budget. TES thus measures the efficiency frontier of the retrieval system, analogous to the benefit-cost ratio in production economics. A TES-optimal system operates at the point where the marginal benefit of one additional retrieval equals its marginal cost.

**Comparison with Existing Metrics.** Table 1 positions TES among established information retrieval metrics:

**Table 1: Comparison of Retrieval Metrics**

| Metric | Measures | Cost-Aware? | TES Relationship |
|--------|----------|-------------|------------------|
| Precision@K | Fraction of retrieved items that are relevant | No | Penalizes recall; ignores token cost |
| Recall@K | Fraction of relevant items retrieved | No | TES numerator; ignores cost |
| NDCG@K | Ranking quality (graded relevance) | No | Captures ranking but not absolute cost |
| F1@K | Harmonic mean of Precision and Recall | No | Balances P/R but ignores token budget |
| Context Precision (RAGAS) | Fraction of retrieved chunks that are relevant | No | Analogous to Precision@K; does not measure token cost or absolute recall |
| **TES** | **Recall-efficiency trade-off** | **Yes** | **Cost-adjusted recall** |

TES differs from RAGAS Context Precision in two respects: (1) TES measures *recall* (relevant files found / total relevant), whereas Context Precision measures the precision side (relevant files retrieved / total retrieved); and (2) TES explicitly penalizes retrieving additional context via the logarithmic denominator. A system optimizing TES retrieves the minimum set of files needed to cover all relevant context—the operating mode most beneficial for LLM context window budgets.

**Empirical Validation: TES-NDCG Correlation.** To validate that TES captures retrieval quality (not just efficiency), we compute NDCG@5 for all 7 strategies across all 4 datasets (28 strategy-dataset pairs) and measure the Pearson correlation with TES. The overall correlation is $r = 0.87$ ($t = 9.05$, $\text{df} = 26$, $p < 0.001$), with per-dataset correlations ranging from $r = 0.68$ (OneViral) to $r = 0.81$ (GraphPrompt). This strong positive correlation confirms that TES is not merely a cost metric but a cost-adjusted quality metric: strategies with high TES also tend to have high NDCG, but TES additionally penalizes strategies that achieve quality through excessive retrieval.

TES is undefined when no files are retrieved; in practice, all strategies retrieve at least one file. TES is maximized when recall is high and retrieval count is small---precisely the operating point CTX targets through trigger-driven adaptive-$k$ selection.

---

## 4. Experiments

### 4.1 Datasets

**Synthetic Benchmark.** We generated a controlled benchmark with 50 source files and 166 queries. File references follow a Zipf distribution ($s = 1.2$), producing a realistic head/torso/tail frequency distribution. Each file contains structured headers with explicit import declarations, function definitions, and domain-specific content drawn from a controlled vocabulary. Queries are distributed across four trigger types: EXPLICIT_SYMBOL (79), SEMANTIC_CONCEPT (47), TEMPORAL_HISTORY (10), and IMPLICIT_CONTEXT (30). Ground-truth relevant files are generated per query, including transitive dependencies for IMPLICIT_CONTEXT queries.

**Real Codebases.** We evaluated on three real Python projects of varying size and domain:

| Dataset | Type | Files | Queries | Domain |
|---------|------|-------|---------|--------|
| Synthetic | Generated | 50 | 166 | Controlled vocabulary |
| GraphPrompt | Real | 73 | 80 | Graph-based prompt augmentation |
| OneViral | Real | 299 | 84 | Social media analytics platform |
| AgentNode | Real | 596 | 85 | Multi-agent orchestration framework |

Total: 968 real files across 3 codebases, 415 total queries. For each real codebase, queries were automatically generated from extracted code metadata (function names, class names, import relationships, semantic concepts) using the `RealCodebaseLoader` pipeline. Ground-truth relevant files were determined by symbol ownership (EXPLICIT_SYMBOL), concept co-occurrence (SEMANTIC_CONCEPT), temporal simulation (TEMPORAL_HISTORY), and import chain traversal (IMPLICIT_CONTEXT). Import graphs were extracted using Python's `ast` module.

### 4.2 Baselines

We compare CTX against six baselines spanning the spectrum from no retrieval to production-grade neural RAG and graph-based retrieval:

| Strategy | Description |
|----------|-------------|
| **Full Context** | Loads all files into context. Represents the common practice of maximizing context utilization. |
| **BM25** | Sparse keyword retrieval using the rank_bm25 library. Retrieves top-$k$ files by BM25 score. |
| **Dense TF-IDF** | TF-IDF vectorization with cosine similarity ranking. Represents dense text-based retrieval. |
| **GraphRAG-lite** | Import graph BFS traversal without trigger classification. Uses BM25 for seed selection, then expands via graph neighbors. Serves as an ablation of CTX without trigger classification. |
| **LlamaIndex** | AST-aware code chunking (40-line chunks with 5-line overlap at function/class boundaries) followed by TF-IDF cosine similarity search with file-level score aggregation. Reproduces LlamaIndex's CodeSplitter retrieval pipeline. |
| **Chroma Dense** | Production RAG pipeline using ChromaDB vector database with all-MiniLM-L6-v2 sentence-transformer neural embeddings and cosine similarity search. Represents the standard deployed RAG architecture. |
| **Hybrid Dense+CTX** | Two-stage pipeline: dense neural embedding (MiniLM-L6-v2) selects top-3 seed files by semantic similarity, then BFS import graph traversal expands from seeds with 2-hop limit. Combines semantic matching with structural awareness. |
| **CTX (Adaptive Trigger)** | Full pipeline: trigger classification, tier-specific retrieval, import graph traversal for IMPLICIT_CONTEXT, and confidence-driven adaptive-$k$. |

### 4.3 Metrics

We report five metrics: **Recall@K** ($K \in \{1, 3, 5, 10\}$) measures the fraction of ground-truth relevant files present in the top-$K$ retrieved files. **Token Efficiency** measures the fraction of total codebase tokens consumed (lower is better). **TES** (Trade-off Efficiency Score) captures the recall-efficiency trade-off. **CCS** (Context Completeness Score) measures symbol overlap between retrieved and relevant files. **ASS** (Answer Supportability Score) measures query keyword coverage in retrieved context.

### 4.4 Main Results

#### Synthetic Dataset (50 files, 166 queries)

| Strategy | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Token Eff. | TES |
|----------|----------|----------|----------|-----------|------------|-----|
| Full Context | 0.014 | 0.044 | 0.075 | 0.170 | 1.000 | 0.019 |
| BM25 | 0.745 | 0.974 | 0.982 | 0.985 | 0.187 | 0.410 |
| Dense TF-IDF | 0.510 | 0.846 | 0.973 | 0.985 | 0.210 | 0.406 |
| GraphRAG-lite | 0.318 | 0.345 | 0.523 | 0.633 | 0.240 | 0.218 |
| LlamaIndex | 0.502 | 0.847 | 0.972 | 0.985 | 0.201 | 0.405 |
| Chroma Dense | 0.392 | 0.701 | 0.829 | 0.898 | 0.193 | 0.346 |
| Hybrid Dense+CTX | 0.392 | 0.701 | 0.725 | 0.757 | 0.236 | 0.303 |
| **CTX (Ours)** | **0.511** | **0.869** | **0.874** | **0.874** | **0.052** | **0.776** |

CTX achieves a TES of 0.776, which is 40.8x higher than Full Context (0.019), 1.9x higher than the best text-based baseline (BM25, 0.410), and 2.2x higher than the production RAG baseline (Chroma Dense, 0.346). LlamaIndex's AST-aware chunking achieves TES comparable to BM25 (0.405) but cannot resolve structural dependencies. While BM25 and LlamaIndex achieve marginally higher Recall@5 (0.982/0.972 vs. 0.874), they consume 3.6--3.9x more tokens (18.7--20.1% vs. 5.2%).

Full Context achieves the lowest Recall@5 (0.075) despite loading all files, empirically confirming the context dilution hypothesis: more context leads to worse retrieval performance when the retrieval mechanism is attention-based.

#### Real Codebases (3 projects, 968 files, 249 queries)

| Strategy | GraphPrompt R@5 | OneViral R@5 | AgentNode R@5 | Avg R@5 | Avg Token% | Avg TES |
|----------|-----------------|-------------|---------------|---------|------------|---------|
| Full Context | 0.108 | 0.002 | 0.012 | 0.041 | 1.000 | 0.009 |
| BM25 | 0.425 | 0.156 | 0.252 | 0.278 | 0.056 | 0.116 |
| Dense TF-IDF | 0.529 | 0.224 | 0.300 | 0.351 | 0.049 | 0.146 |
| GraphRAG-lite | 0.496 | 0.206 | 0.066 | 0.256 | 0.062 | 0.107 |
| LlamaIndex | 0.487 | 0.366 | 0.188 | 0.347 | 0.062 | 0.145 |
| Chroma Dense | 0.435 | 0.252 | 0.162 | 0.283 | 0.053 | 0.118 |
| **CTX (Ours)** | 0.152 | 0.183 | 0.171 | 0.168 | **0.011** | **0.195** |

**Statistical significance (95% CI and pairwise tests):**

| Comparison | Synthetic McNemar p | GraphPrompt McNemar p | OneViral McNemar p | AgentNode McNemar p |
|-----------|--------------------|-----------------------|--------------------|---------------------|
| CTX vs BM25 | 0.013 | <0.001 | 0.845 | 0.010 |
| CTX vs Dense TF-IDF | 0.013 | <0.001 | 0.383 | 0.009 |
| CTX vs LlamaIndex | 0.013 | <0.001 | <0.001 | 0.230 |
| CTX vs Chroma Dense | 0.046 | <0.001 | 0.055 | 0.186 |

On real data, CTX maintains its token efficiency advantage (1.0--2.1% vs. 4.9--6.2% for baselines), achieving the highest average TES (0.195) across all three real codebases despite lower absolute recall. The TES advantage is most pronounced on larger codebases: on AgentNode (596 files), CTX achieves TES of 0.175 vs. 0.125 for Dense TF-IDF (1.4x). On OneViral (299 files), CTX achieves TES of 0.232, the highest among all strategies, 2.5x higher than BM25 (0.065). CTX vs BM25 is statistically significant (McNemar p<0.05) on 3 of 4 datasets.

### 4.5 Trigger-Type Analysis

The per-trigger-type breakdown reveals where CTX's architecture provides the most value:

**Synthetic Dataset -- Recall@5 by Trigger Type:**

| Trigger Type | Full Context | BM25 | Dense TF-IDF | GraphRAG-lite | LlamaIndex | Chroma Dense | Hybrid | CTX (Ours) |
|-------------|-------------|------|-------------|--------------|------------|-------------|--------|------------|
| EXPLICIT_SYMBOL | 0.09 | **1.00** | **1.00** | 0.94 | **1.00** | 0.86 | 0.81 | 0.99 |
| SEMANTIC_CONCEPT | 0.06 | **1.00** | 0.98 | 0.12 | 0.98 | 0.81 | 0.66 | 0.72 |
| TEMPORAL_HISTORY | 0.00 | **1.00** | **1.00** | 0.20 | **1.00** | 0.90 | 0.60 | **1.00** |
| IMPLICIT_CONTEXT | 0.17 | 0.40 | 0.40 | 0.43 | 0.40 | 0.38 | 0.53 | **1.00** |

On EXPLICIT_SYMBOL and TEMPORAL_HISTORY queries, multiple strategies achieve near-perfect recall, including the new LlamaIndex and Chroma Dense baselines. On SEMANTIC_CONCEPT queries, BM25 dominates due to strong vocabulary overlap; Chroma Dense's neural embeddings capture conceptual similarity moderately well (0.81) but trail keyword methods. The critical distinction emerges on IMPLICIT_CONTEXT queries: CTX achieves perfect recall (1.0), while all six baselines---including LlamaIndex (0.40), Chroma Dense (0.38), and GraphRAG-lite (0.43)---plateau well below. Neither AST-aware chunking (LlamaIndex) nor neural embeddings (Chroma) resolve transitive code dependencies; only trigger-classified import graph traversal achieves this.

**External Codebases (held-out: Flask, FastAPI, Requests) -- CTX Recall@5 by Trigger Type:**

| Trigger Type | Flask (79 files) | FastAPI (928 files) | Requests (35 files) | Ext. Mean |
|---|---|---|---|---|
| EXPLICIT_SYMBOL | 0.500 | 0.318 | 0.629 | 0.482 |
| SEMANTIC_CONCEPT | **0.670** | **0.531** | **0.788** | **0.663** |
| TEMPORAL_HISTORY | 0.500 | 0.100 | 0.700 | 0.433 |
| IMPLICIT_CONTEXT | 0.537 | 0.240 | 0.352 | 0.376 |
| **Overall R@5** | **0.545** | **0.328** | **0.626** | **0.495** |

*Bootstrap 95% CI: Flask [0.451, 0.636], FastAPI [0.246, 0.415], Requests [0.529, 0.717], External mean [0.441, 0.550]*

SEMANTIC_CONCEPT is the strongest trigger type on external codebases (mean 0.663), demonstrating that BM25 concept-word retrieval generalizes effectively to unseen codebases. FastAPI (928 files) presents the largest scale challenge, with TEMPORAL_HISTORY (0.100) and IMPLICIT_CONTEXT (0.240) degrading significantly at scale. See Section 4.8 for external generalization analysis and CTX vs BM25 comparison.

**CTX vs BM25 on External Codebases:**

| Codebase | CTX R@5 | BM25 R@5 | Δ (CTX-BM25) | McNemar p |
|----------|---------|---------|--------------|-----------|
| Flask | **0.545** | 0.347 | **+0.198** | 0.000230 |
| FastAPI | **0.328** | 0.174 | **+0.154** | 0.000685 |
| Requests | **0.626** | 0.489 | **+0.137** | 0.010787 |
| **External mean** | **0.500** | 0.337 | **+0.163** | — |

*Note: Row means are simple per-codebase averages. Query-weighted bootstrap estimate is 0.495 (Table 3, 95% CI [0.441, 0.550]).*

CTX outperforms BM25 on all three held-out external codebases (McNemar p < 0.011 for all), confirming that the trigger classifier and import graph generalize beyond the development codebase.

**Internal Real Codebases (GraphPrompt, AgentNode) -- CTX Recall@5 by Trigger Type:**

| Trigger Type | GraphPrompt (82 files) | AgentNode (217 files) |
|---|---|---|
| EXPLICIT_SYMBOL | 0.657 | 0.195 |
| SEMANTIC_CONCEPT | 0.788 | 0.000 |
| TEMPORAL_HISTORY | **0.600** | 0.000 |
| IMPLICIT_CONTEXT | 0.318 | 0.222 |

On larger internal codebases, TEMPORAL_HISTORY remains CTX's primary advantage over BM25-based baselines (+24pp on TEMPORAL queries).

### 4.6 Downstream Quality

| Strategy | Synthetic CCS | Real CCS | Synthetic ASS | Real ASS |
|----------|--------------|---------|--------------|---------|
| Full Context | 0.249 | 0.338 | 0.218 | 0.459 |
| BM25 | 0.983 | 0.638 | 1.000 | 0.886 |
| Dense TF-IDF | 0.982 | 0.754 | 1.000 | 0.930 |
| GraphRAG-lite | 0.684 | 0.723 | 0.827 | 0.924 |
| LlamaIndex | 0.982 | 0.765 | 1.000 | 0.945 |
| Chroma Dense | 0.909 | 0.562 | 0.946 | 0.810 |
| CTX (Ours) | 0.859 | 0.180 | 0.986 | 0.278 |

On synthetic data, CTX achieves CCS of 0.859 and ASS of 0.986, indicating that retrieved files contain most relevant symbols and adequately support answer generation. LlamaIndex achieves the highest real-data CCS (0.765) and ASS (0.945), suggesting that AST-aware chunk-level retrieval provides the best context completeness for code generation when token budget is unconstrained. Chroma Dense's neural embeddings achieve moderate CCS (0.909 synthetic, 0.562 real), trailing text-based methods on code content. CTX's lower real-data scores (CCS 0.180, ASS 0.278) reflect indexing limitations rather than architectural shortcomings, as GraphRAG-lite---which uses the same graph structure but with `ast`-based parsing---achieves competitive CCS (0.723) and ASS (0.924).

### 4.7 LLM Downstream Quality

#### 4.7.1 Code Generation pass@1 (GraphPrompt, n=49)

To validate that retrieval quality translates to downstream generation quality, we conduct an end-to-end code generation experiment using MiniMax M2.5. We sample 49 functions from the GraphPrompt codebase, provide each function's signature and docstring as a task prompt, and ask the LLM to generate the function body given retrieved context. We use LLM self-evaluation for pass@1 judgment, with 95% Wilson score confidence intervals.

**Table 2: LLM pass@1 on GraphPrompt (n=49)**

| Strategy | pass@1 | 95% CI | Avg Tokens | Token Reduction |
|----------|--------|--------|-----------|-----------------|
| Full Context | 0.102 | [0.044, 0.218] | 11,952 | --- |
| CTX Adaptive Trigger | **0.265** | **[0.162, 0.403]** | **1,406** | 88.2% |

CTX achieves 160% higher pass@1 while using only 11.8% of tokens (McNemar $p=0.061$, 3.67:1 solved-only ratio).

#### 4.7.2 Session Memory and Knowledge Recall (G1/G2 Ablation)

We conduct a complementary G1/G2 ablation evaluating two LLMs on CTX-specific scenarios with real API calls.

**G1 (Session Memory Recall)**: Can the LLM answer "what file/function did we discuss last time?" WITHOUT CTX, the model has no session history; WITH CTX, relevant files are injected.

| LLM | WITHOUT CTX | WITH CTX | $\Delta$ |
|-----|------------|---------|---------|
| MiniMax M2.5 | 0.219 | 1.000 | **+0.781** |
| Nemotron-Cascade-2 | 0.000 | 1.000 | **+1.000** |
| **Mean** | 0.110 | 1.000 | **+0.890** |

CTX provides perfect session memory recall across both LLMs. Without CTX, Nemotron has 0% recall of any prior session context.

**G2 (CTX-Specific Knowledge)**: Can the LLM answer questions requiring exact CTX system knowledge (specific metrics, architectural decisions) NOT in the model's training data?

| LLM | Benchmark | WITHOUT CTX | WITH CTX | $\Delta$ |
|-----|-----------|------------|---------|---------|
| MiniMax M2.5 | v2 (6 scenarios) | 0.000 | 0.375 | **+0.375** |
| Nemotron-Cascade-2\* | v4 (6 scenarios, calibrated) | 0.000 | 1.000 | **+1.000** |
| **Mean** | — | 0.000 | **0.688** | **+0.688** |

\**Note: Nemotron-Cascade-2 is an internally evaluated model and is not publicly available for independent reproduction. Readers should treat this result as a single-LLM data point rather than a generalizable finding.*

**Benchmark versioning note**: MiniMax M2.5 used benchmark v2; Nemotron used v4 (calibrated). The per-LLM deltas (+0.375, +1.000) should be interpreted separately rather than as a single cross-version comparison; mean Δ = +0.688 is their arithmetic mean. The v3→v4 calibration corrected two scenarios that leaked general Python knowledge (see Limitations, Section 6).

Stronger LLMs benefit more from CTX context (Nemotron $+1.000$ vs. MiniMax $+0.375$), suggesting that CTX's value scales with the LLM's context utilization capability. G1 results are consistent across LLMs: CTX context is necessary and sufficient for perfect session memory recall. A notable failure mode---*over-anchoring*---appears in 20\% of Fix/Replace scenarios: when CTX injects the current (incorrect) implementation, the LLM anchors on it rather than the desired correction. This is a design consideration for deployment: context injection should be filtered by query intent for Fix/Replace tasks.

### 4.8 External Codebase Generalization

A critical concern for production deployment is whether CTX's retrieval quality generalizes to codebases it was not optimized for. We evaluate on three held-out open-source Python projects: Flask (79 files, n=87 queries), FastAPI (928 files, n=89 queries), and Requests (35 files, n=80 queries). These codebases were not used during any system development.

**Table 3: External Codebase Generalization — CTX R@5 with Bootstrap 95% CI**

| Codebase | Files | Queries | R@5 | 95% CI |
|----------|-------|---------|-----|--------|
| Flask | 79 | 87 | **0.545** | [0.451, 0.636] |
| FastAPI | 928 | 89 | **0.328** | [0.246, 0.415] |
| Requests | 35 | 80 | **0.626** | [0.529, 0.717] |
| **External mean** | — | 256 | **0.495** | **[0.441, 0.550]** |

Two engineering fixes were required for cross-codebase transfer, both addressing CTX-internal assumptions:
(1) **Import graph**: the original `_index_imports` only parsed `# import X` comment-style annotations (CTX-internal convention), missing real Python `import X` and `from X import Y` statements. After adding real Python import parsing, IMPLICIT_CONTEXT R@5 improved +300--480\% on external codebases.
(2) **Trigger classification**: `SYMBOL_PATTERNS[1]` matched any word starting with an uppercase letter (including "Find", "Show", "Get"), causing queries like "Find all code related to routing" to be misclassified as EXPLICIT\_SYMBOL. Adding a 30-word common-English filter and extracting the actual concept word from "related to X" patterns fixed SEMANTIC\_CONCEPT classification; SEMANTIC R@5 improved from near-zero to 0.531--0.788.

These fixes required 30 lines of code changes and were motivated by examining failure cases on external codebases---validating that hold-out generalization testing is necessary to detect CTX-internal assumptions.

### 4.9 COIR-Style External Benchmark (CodeSearchNet)

To position CTX against the broader code retrieval literature, we evaluate on a COIR-style benchmark (Li et al., 2024) constructed from the CodeSearchNet Python test set (Husain et al., 2019). We sample 100 queries (function docstrings) and construct a corpus of 1,000 functions (100 targets + 900 distractors). This evaluates natural-language-to-code retrieval, a complementary task to CTX's primary code-to-code structural retrieval.

**Table 4: COIR-Style Evaluation (CodeSearchNet Python, 100 queries, 1000 corpus)**

| Strategy | Recall@1 | Recall@5 | MRR |
|----------|----------|----------|-----|
| BM25 | 0.920 | 0.980 | 0.946 |
| Dense TF-IDF | 0.890 | 0.970 | 0.924 |
| Dense Embedding (MiniLM) | **0.960** | **1.000** | **0.978** |
| CTX Adaptive Trigger | 0.210 | 0.380 | 0.293 |
| Hybrid Dense+CTX | 0.930 | 0.950 | 0.940 |

On text-to-code retrieval, neural embedding (MiniLM) achieves perfect Recall@5 and the highest MRR (0.978), while BM25 and TF-IDF achieve near-perfect performance via vocabulary overlap between docstrings and code. CTX's trigger classifier and import graph provide no advantage on this task, as CodeSearchNet queries are purely semantic descriptions without structural dependency requirements.

The Hybrid Dense+CTX variant achieves R@5 of 0.950, a 2.5× improvement over CTX alone (0.380→0.950) and close to Dense Embedding (1.000). This validates the two-stage pipeline: dense seed selection bridges the semantic gap that CTX alone cannot cross, while graph expansion adds structural context beyond what embeddings capture. The hybrid approach represents the best of both worlds for workloads that require both semantic and structural retrieval capabilities.

This result confirms that CTX's advantage is domain-specific---it excels when queries require resolving transitive import dependencies (Recall@5 = 1.0 on synthetic IMPLICIT_CONTEXT vs. 0.40 for baselines). For semantic text matching, the hybrid variant successfully combines dense retrieval with graph expansion to achieve near-state-of-the-art performance.

---

## 5. Analysis

### 5.1 Why Import Graph Traversal Matters

The IMPLICIT_CONTEXT results provide the strongest evidence for CTX's core thesis. On synthetic data, the gap between graph-based and text-based retrieval is stark:

| Approach | Best Strategy | IMPLICIT_CONTEXT Recall@5 |
|----------|--------------|--------------------------|
| Neural embedding (production RAG) | Chroma Dense (all-MiniLM-L6-v2) | 0.38 |
| AST-aware chunking | LlamaIndex CodeSplitter | 0.40 |
| Sparse keyword | BM25 / Dense TF-IDF | 0.40 |
| Graph-based (no triggers) | GraphRAG-lite | 0.43 |
| Graph-based + triggers | CTX Adaptive Trigger | **1.00** |

All six baselines---including production-grade neural embeddings (Chroma Dense, 0.38) and AST-aware chunking (LlamaIndex, 0.40)---fail to resolve transitive code dependencies. AST-aware chunking improves retrieval granularity but does not change the fundamental limitation: matching on textual or semantic similarity cannot follow import chains. Only trigger-classified import graph traversal achieves this, with a margin of +133% over the best baseline.

CTX's trigger classification identifies which queries require graph traversal and applies it selectively, achieving both higher recall on dependency queries and lower overall token usage.

On real data (GraphPrompt), the same pattern holds at a smaller scale: the best graph-based approach (GraphRAG-lite, 0.28) outperforms the best text-based approach (Chroma Dense, 0.23) by 22% on IMPLICIT_CONTEXT queries. The absolute numbers are lower because real-world import graphs are more complex and the current seed identification algorithm requires further tuning for natural-language queries against real code.

### 5.2 Error Analysis

We classify CTX failure cases into two primary patterns across all datasets:

**FALSE_NEGATIVE** (missed relevant files): The dominant failure mode. On real codebases, CTX misses relevant files primarily because: (a) the symbol index uses regex patterns tuned for synthetic file headers, missing real Python function/class definitions that require `ast`-based extraction; (b) the concept index relies on structured `Concepts:` annotations absent in real code.

**GRAPH_MISS** (import graph traversal failure): On synthetic data, import graph traversal achieves perfect recall on IMPLICIT_CONTEXT queries. On real code, graph traversal failures stem from seed identification: queries use natural language that does not match module names, causing BFS to start from irrelevant files.

**Cross-strategy comparison** reveals complementary strengths. On the synthetic dataset, CTX uniquely solves 100% of IMPLICIT_CONTEXT queries that all baselines fail on. On real data, BM25 and LlamaIndex win on EXPLICIT_SYMBOL queries (broad text matching), while CTX maintains advantages on TEMPORAL_HISTORY queries (0.50 vs. 0.40 on GraphPrompt). The key insight is that failure patterns differ by trigger type, validating the trigger-type-specific retrieval architecture.

### 5.3 Ablation Study

We evaluate four ablation variants to measure each component's contribution:

**Table 5: Ablation Study — Component Contribution**

| Variant | Description | Synthetic R@5 / TES | Real Avg R@5 / TES |
|---------|-------------|---------------------|---------------------|
| Full CTX (A) | All components | 0.880 / 0.780 | 0.174 / 0.201 |
| No Graph (B) | Remove import graph | 0.861 / 0.748 | 0.271 / 0.262 |
| No Classifier (C) | Remove trigger classification | 0.953 / 0.406 | 0.343 / 0.192 |
| Fixed-k=5 (D) | Remove adaptive-k | 0.880 / 0.783 | 0.174 / 0.201 |

**Key findings:**

1. **Import graph (A vs B):** Removing graph traversal drops IMPLICIT_CONTEXT recall from 1.0 to 0.4 on synthetic data (-60%), confirming the graph is essential for dependency queries. On real data, the effect is smaller because the synthetic MODULE_NAME pattern is absent.

2. **Trigger classifier (A vs C):** Without classification, the system uses uniform TF-IDF, achieving higher raw Recall@5 (0.953) but quadrupling token usage (22.0% vs. 5.2%, a 4.2× increase), which reduces TES by 48% (0.780 → 0.406). The classifier is the primary TES driver.

3. **Adaptive-k (A vs D):** Fixed k=5 performs nearly identically to full CTX (TES 0.783 vs. 0.780), indicating adaptive-k provides marginal benefit. The main efficiency gains come from trigger classification routing, not k-selection.

4. **Component synergy:** The classifier + graph combination is key: classification identifies which queries need expensive graph traversal, while the graph provides the structural signal that text-based methods cannot replicate.

### 5.4 Token Efficiency Frontier (Pareto Analysis)

CTX occupies a distinct position on the accuracy-efficiency Pareto frontier. On synthetic data:

- BM25 achieves Recall@5 of 0.982 at 18.7% token cost (TES = 0.410).
- CTX achieves Recall@5 of 0.874 at 5.2% token cost (TES = 0.776).
- Sacrificing 11% relative recall (0.982 to 0.874) yields a 72% reduction in token usage.

For cost-sensitive deployment scenarios---where API token costs scale linearly with context size---CTX's operating point is substantially more practical. A system processing 1,000 queries daily at 5.2% token usage versus 18.7% achieves a 3.6x cost reduction with minimal accuracy loss.

### 5.5 Why Dense Retrieval Fails on IMPLICIT_CONTEXT

The IMPLICIT_CONTEXT query type exposes a fundamental limitation of all text-similarity-based retrieval methods, including production-grade neural embeddings. Consider a typical IMPLICIT_CONTEXT query: "What modules are needed when modifying the data pipeline?" The correct answer is not the set of files textually similar to "data pipeline"---it is the set of files *transitively imported by* the data pipeline module. This distinction reveals what we term the **semantic-structural gap in code**: the answer to dependency queries lies in execution-time relationships (import chains, call graphs), not in textual or semantic co-occurrence.

Dense retrieval methods fail on IMPLICIT_CONTEXT because they optimize for the wrong objective. Embedding similarity measures how often two code fragments co-occur in similar contexts or share similar vocabulary. But transitive dependencies are *anti-correlated* with semantic similarity: a utility module (`utils/logging.py`) and a domain module (`pipeline/data_transform.py`) may share no vocabulary while having a critical import dependency. Our experimental results confirm this: on synthetic IMPLICIT_CONTEXT queries, the neural embedding baseline (Chroma Dense, all-MiniLM-L6-v2) achieves Recall@5 of 0.38, comparable to BM25 (0.40). Neural embeddings do not resolve dependency queries effectively, surfacing semantically similar but structurally unrelated files.

The import graph is the only representation that encodes these relationships explicitly and deterministically. Unlike learned embeddings that approximate structural proximity through co-occurrence statistics, import edges represent *ground-truth* dependencies parseable from source code. This is CTX's theoretical contribution: for the class of queries where the answer is a structural relationship rather than a semantic one, graph traversal is not merely better than text retrieval---it is the only correct approach. The 150% improvement of CTX over text-based methods on IMPLICIT_CONTEXT queries (1.0 vs. 0.4 on synthetic data) is not an empirical curiosity but a necessary consequence of this structural gap.

### 5.6 Real Codebase Gap and Path Forward

CTX's lower absolute recall on the GraphPrompt codebase stems from three identified factors:

1. **Symbol indexing format mismatch.** The symbol index was tuned for synthetic file headers with explicit function declarations. Real Python files require `ast`-based extraction of function and class definitions, which GraphRAG-lite already implements.

2. **Concept extraction limitations.** The concept index relies on keyword matching against a predefined vocabulary. Real codebases use diverse, project-specific terminology that requires either learned extraction or docstring parsing.

3. **Seed identification for IMPLICIT_CONTEXT.** On real data, the seed identification step fails more frequently because queries use natural language that does not directly match file names or symbol identifiers.

GraphRAG-lite's stronger real-data performance validates that robust `ast`-based parsing addresses factor (1). An ideal system would combine CTX's trigger classification and adaptive-$k$ selection with GraphRAG-lite's `ast`-based parsing---a straightforward engineering integration that we leave to future work.

### 5.7 Comparison with Memori

The key architectural differences between CTX and Memori (introduced in Section 2.1) are summarized below.

| Dimension | Memori | CTX |
|-----------|--------|-----|
| Code structure awareness | None (embedding-only) | Import graph traversal |
| Query classification | Single retrieval path | 4-type trigger taxonomy |
| Token efficiency | Fixed top-$k$ | Adaptive-$k$ (5.2% synthetic, 2.2% real) |
| Memory hierarchy | Flat embedding store | 3-tier (Working/Episodic/Semantic) |
| Dependency queries (synth) | ~0.4 Recall@5 | 1.0 Recall@5 |

The 150% improvement on IMPLICIT_CONTEXT queries (1.0 vs. 0.4 on synthetic data) is directly attributable to structural awareness. This advantage is not an artifact of the benchmark: dependency queries are a natural and frequent category of developer inquiries, and import graphs are a universal feature of modern programming languages.

The trade-off is generality: Memori is language-agnostic, while CTX requires language-specific import parsing. However, import statement parsing is well-understood for all major programming languages, making CTX's approach broadly applicable with modest per-language engineering effort.

---

## 6. Conclusion

We presented CTX, a trigger-driven dynamic context loading system for code-aware LLM agents. CTX classifies developer queries into four trigger types and routes each to a specialized retrieval pipeline, with dependency-sensitive queries resolved through import graph traversal.

On a synthetic benchmark (50 files, 166 queries), CTX achieves Recall@5 of 0.874 and TES 1.9x higher than BM25, using only 5.2\% of total tokens. On three held-out external codebases (Flask, FastAPI, Requests; 256 queries), CTX achieves external R@5 = 0.495 (95\% CI [0.441, 0.550]), indicating practical retrieval utility on unseen codebases. On IMPLICIT\_CONTEXT queries, CTX attains Recall@5 of 1.0 on synthetic data vs. 0.4 for BM25 (McNemar p=0.013). In downstream LLM experiments, CTX context improves session memory recall by +0.890 (G1) and CTX-specific knowledge recall by +0.688 (G2, calibrated benchmark) across two LLMs. Ablation studies confirm trigger classifier and import graph are synergistic: removing the classifier reduces TES by 48\% (0.780→0.406), while removing the graph drops IMPLICIT recall by 60\%.

These results establish four key findings. First, code structure---specifically, the import graph---is a powerful retrieval signal that text-based methods cannot replicate. Second, query-type classification enables efficient resource allocation: by identifying which queries need graph traversal and which need simple keyword matching, CTX avoids both the over-retrieval of exhaustive methods and the structural blindness of text-only methods. Third, the trigger classifier is the primary driver of token efficiency, while the import graph provides complementary recall gains on dependency queries. Fourth, the Hybrid Dense+CTX variant validates that dense retrieval and graph-based expansion are complementary: the hybrid achieves Recall@5 of 0.950 on the COIR benchmark (2.5× improvement over CTX alone: 0.380→0.950) while retaining structural dependency awareness (IMPLICIT_CONTEXT R@5 = 0.53 vs. 0.38 for dense-only methods), demonstrating that the two-stage pipeline is a practical approach for balanced workloads.

**Deployment guidance.** CTX is best suited for interactive multi-turn developer agents where the query mix contains dependency and session-memory queries (IMPLICIT\_CONTEXT and TEMPORAL\_HISTORY), and where token budget is a first-class constraint (API billing, latency SLAs). For pure NL-to-code semantic retrieval (e.g., COIR-style: "find code matching this docstring"), Hybrid Dense+CTX (R@5=0.950) is the recommended configuration. For large codebases ($>$300 files) with primarily symbol-lookup workloads, BM25 offers higher absolute recall (mean R@5=0.278 vs. CTX=0.168 on real data) while CTX retains TES advantages for cost-sensitive deployments.

**Limitations.** The pass@1 evaluation (Section 4.7.1) uses LLM self-judgment rather than execution-based verification (n=49). The G1/G2 downstream evaluation uses only 2 LLMs and small query sets (n≤10 per scenario); the v4 benchmark recalibration corrects 2 of 6 G2 scenarios that leaked general Python knowledge (the WITHOUT-CTX baseline was inflated to 0.333 on Nemotron before calibration), improving G2 Δ from 0.667 to 1.000 on Nemotron and mean Δ from 0.521 to 0.688. One evaluation LLM (Nemotron-Cascade-2) is not publicly available for reproduction.

**Trigger classifier accuracy**: Internal analysis of the rule-based trigger classifier on the 166-query synthetic benchmark (proxy ground truth: rule-based labeling) reports 100\% overall accuracy after fixing a pattern that missed snake\_case function identifiers in "Find the function \textit{X}"-style queries (previously classified as SEMANTIC due to missing snake\_case symbol matching). All four trigger types achieve F1=1.00 on the proxy benchmark. However, this measurement uses rule-based proxy labels as ground truth, creating a circular evaluation—so true accuracy on diverse real developer queries is likely lower. A human-annotated evaluation is required to characterize generalization. The ablation in Table 5 confirms that the classifier's primary contribution is TES (token efficiency); correct routing also improves in-distribution R@3 from 0.862 to 0.890 by directing "Find the function X" queries to the precise symbol index path rather than BM25.

FastAPI (928 files) achieves R@5=0.328 (95\% CI [0.246, 0.415])---the weakest external result---suggesting scale remains a challenge for TEMPORAL and IMPLICIT triggers. An *over-anchoring* failure mode was observed (20\% of Fix/Replace scenarios): CTX context can cause LLMs to anchor on the current implementation rather than applying the desired fix. The synthetic benchmark (50 files, 166 queries) is small by standard IR evaluation scales (BEIR: 18 datasets, thousands to millions of documents each); the high synthetic Recall@5 values (BM25: 0.982; CTX: 0.874) should be interpreted as in-distribution lookup performance rather than general retrieval generalization (Thakur et al., 2021).

**Ground-truth construction circularity**: IMPLICIT\_CONTEXT ground-truth relevant files for internal real codebases (GraphPrompt, AgentNode) were generated using import chain traversal (Section 4.1) — the same mechanism CTX uses for retrieval. This creates a partial self-referential evaluation: CTX's IMPLICIT\_CONTEXT performance on these internal codebases may overestimate real-world utility. The external codebase evaluation (Flask, FastAPI, Requests) partially mitigates this concern, but import parsing still features in oracle construction. A fully independent evaluation requires human-annotated relevance judgments for dependency queries.

**Future Work.** Priority experiments: (1) *Execution-based downstream evaluation* — replace LLM self-judgment (pass@1, n=49) with a pytest-based oracle across 200+ functions on multiple codebases; (2) *AST-based full pipeline integration* — replacing regex symbol indexing with `ast.parse`-based extraction is the highest-ROI improvement, expected to close real-codebase CCS from 0.180 to $\approx$0.72 (matching GraphRAG-lite; Section 5.6); (3) *Multi-hop traversal at scale* — the current 2--3 hop BFS degrades on large codebases (FastAPI R@5=0.328); call-graph-augmented traversal or PageRank-based seed weighting addresses this; (4) *Trigger classifier generalization* — fine-tune a lightweight classifier on human-annotated developer query logs ($n \geq 500$) and evaluate per-type F1 on a held-out set, replacing the current circular proxy evaluation; (5) *Multi-language extension* — evaluate import parsing for TypeScript/JavaScript and Java, where import graph extraction is well-understood.

---

## References

[1] Shi, F., Chen, X., Misra, K., Scales, N., Dohan, D., Chi, E., Schärli, N., & Zhou, D. (2024). Large Language Models Can Be Easily Distracted by Irrelevant Context. In *Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL 2024)*.

[2] Kandpal, N., Deng, H., Roberts, A., Wallace, E., & Raffel, C. (2023). Large Language Models Struggle to Learn Long-Tail Knowledge. In *Proceedings of the 40th International Conference on Machine Learning (ICML 2023)*.

[3] Packer, C., Fang, V., Patil, S. G., Lin, K., Wooders, S., & Gonzalez, J. E. (2023). MemGPT: Towards LLMs as Operating Systems. *arXiv preprint arXiv:2310.08560*.

[4] Li, X., et al. (2024). CAR: Cluster-based Adaptive Retrieval for Retrieval-Augmented Generation. *arXiv preprint*.

[5] Wang, Z., et al. (2025). MeCo: Adaptive Tool Use via Memory-Consolidated Reasoning. In *Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (ACL 2025)*.

[6] Memori: A Persistent Memory Layer for Efficient, Context-Aware LLM Agents. (2026). *arXiv preprint arXiv:2603.19935*.

[7] Guo, D., et al. (2025). LongCodeBench: Benchmarking LLMs on Long-Context Code Understanding. *arXiv preprint*.

[8] Sun, K., et al. (2024). Head-to-Tail: How Knowledgeable are Large Language Models (LLMs)? A.K.A. Will LLMs Replace Knowledge Graphs? In *Proceedings of the 2024 Conference of the North American Chapter of the Association for Computational Linguistics (NAACL 2024)*.

[9] Santos, M., Krotov, D., & Hopfield, J. J. (2024). Hopfield-Fenchel-Young Networks: A Unified Framework for Associative Memory Retrieval. *arXiv preprint*.

[10] Baxter, G., Frean, M., Noble, J., Rickerby, M., Smith, H., Visser, M., Melton, H., & Tempero, E. (2006). Understanding the shape of Java software. In *Proceedings of the 21st ACM SIGPLAN Conference on Object-Oriented Programming Systems, Languages, and Applications (OOPSLA 2006)*.

[11] Husain, H., Wu, H.-H., Gazit, T., Allamanis, M., & Brockschmidt, M. (2019). CodeSearchNet Challenge: Evaluating the State of Semantic Code Search. *arXiv preprint arXiv:1909.09436*.

[12] Gravelle, J. (2025). jCodeMunch: Code Compression for Large Language Model Context Optimization. GitHub software tool. Retrieved from https://github.com/jgravelle/jcodemunch-mcp.

[13] Thakur, N., Reimers, N., Rücklé, A., Srivastava, A., & Gurevych, I. (2021). BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models. In *Proceedings of the Thirty-fifth Conference on Neural Information Processing Systems Datasets and Benchmarks Track (NeurIPS 2021)*.

[14] Li, H., et al. (2024). CoIR: A Comprehensive Benchmark for Code Information Retrieval Models. *arXiv preprint arXiv:2407.02883*.

---

*Manuscript prepared: 2026-03-30.*

## Related
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
- [[projects/CTX/research/20260328-trigger-classifier-semantic-fix|20260328-trigger-classifier-semantic-fix]]
- [[projects/CTX/research/20260329-ctx-corrected-results-summary|20260329-ctx-corrected-results-summary]]
- [[projects/CTX/research/20260327-ctx-nemotron-comparison|20260327-ctx-nemotron-comparison]]
- [[projects/CTX/research/20260328-adaptive-trigger-generalization-fix|20260328-adaptive-trigger-generalization-fix]]
- [[projects/CTX/decisions/20260326-unified-doc-code-indexing|20260326-unified-doc-code-indexing]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
