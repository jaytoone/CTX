# CTX: Trigger-Driven Dynamic Context Loading for Code-Aware LLM Agents

CTX is a retrieval system for code-aware LLM agents that classifies developer queries into four trigger types (EXPLICIT_SYMBOL, SEMANTIC_CONCEPT, TEMPORAL_HISTORY, IMPLICIT_CONTEXT) and routes each to a specialized retrieval pipeline. For dependency-sensitive queries, CTX traverses the codebase import graph to resolve transitive relationships that keyword and embedding methods cannot capture. A three-tier hierarchical memory architecture (Working, Episodic, Semantic) organizes codebase knowledge for efficient access.

The key insight is that code import graphs encode structural dependency information that text-based RAG approaches miss entirely. On implicit dependency queries, CTX achieves Recall@5 of 1.0 compared to 0.4 for BM25, while consuming only 5.2% of total tokens.

## Quick Start

```bash
pip install -r requirements.txt
python run_experiment.py --dataset-size small --strategy all
```

## Results Summary (8 strategies, 4 datasets)

### Synthetic Benchmark (50 files, 166 queries)

| Strategy | Recall@5 | Token Usage | TES |
|----------|----------|-------------|-----|
| Full Context | 0.075 | 100.0% | 0.019 |
| BM25 | 0.982 | 18.7% | 0.410 |
| Dense TF-IDF | 0.973 | 21.0% | 0.406 |
| GraphRAG-lite | 0.523 | 24.0% | 0.218 |
| LlamaIndex | 0.972 | 20.1% | 0.405 |
| Chroma Dense | 0.829 | 19.3% | 0.346 |
| Hybrid Dense+CTX | 0.725 | 23.6% | 0.303 |
| **CTX (Ours)** | **0.874** | **5.2%** | **0.776** |

### COIR External Benchmark (CodeSearchNet Python)

| Strategy | Recall@1 | Recall@5 | MRR |
|----------|----------|----------|-----|
| Dense Embedding (MiniLM) | 0.960 | 1.000 | 0.978 |
| Hybrid Dense+CTX | 0.930 | 0.950 | 0.940 |
| BM25 | 0.920 | 0.980 | 0.946 |
| CTX Adaptive Trigger | 0.210 | 0.380 | 0.293 |

### Key Findings

- **CTX** achieves 1.9x higher TES than BM25 with only 5.2% token usage
- **CTX** achieves perfect Recall@5 (1.0) on IMPLICIT_CONTEXT dependency queries
- **Hybrid Dense+CTX** achieves R@5=0.950 on COIR, a 150% improvement over CTX alone
- No single strategy dominates all dimensions -- the optimal choice depends on workload

**TES** = Recall@5 / ln(1 + files_loaded). Higher is better.

## Running Experiments

### Prerequisites

```bash
pip install -r requirements.txt
```

### Synthetic Benchmark

```bash
python run_experiment.py --dataset-size small --strategy all
```

### Real Codebase

```bash
python run_experiment.py --dataset-source real --project-path /path/to/project --strategy all
```

### COIR External Benchmark

```bash
python run_coir_eval.py --n-queries 100
```

### Ablation Study

```bash
python run_experiment.py --dataset-size small --mode ablation
```

Results are written to `benchmarks/results/`.

## Project Structure

```
CTX/
  src/
    retrieval/            # Retrieval strategies (8 total)
      adaptive_trigger.py # CTX core: trigger-driven retrieval
      hybrid_dense_ctx.py # Hybrid: dense seed + graph expansion
      chroma_retriever.py # ChromaDB + sentence-transformers
      dense_retriever.py  # TF-IDF dense retrieval
      bm25_retriever.py   # BM25 sparse retrieval
      graph_rag.py        # GraphRAG-lite baseline
      llamaindex_retriever.py # LlamaIndex AST-aware chunking
      full_context.py     # Full context baseline
    trigger/              # Trigger classifier
    evaluator/            # Benchmark runner, metrics, COIR
    data/                 # Dataset generation, real codebase loader
    visualizer/           # Report generation
  benchmarks/
    datasets/             # Generated synthetic datasets
    results/              # Experiment results and reports
  docs/
    paper/                # Paper draft (markdown + LaTeX)
  run_experiment.py       # Main experiment runner
  run_coir_eval.py        # COIR benchmark runner
  requirements.txt        # Python dependencies
```

## Paper

- Paper draft: [`docs/paper/CTX_paper_draft.md`](docs/paper/CTX_paper_draft.md)
- LaTeX version: [`docs/paper/CTX_paper.tex`](docs/paper/CTX_paper.tex)
- arXiv link: TBD
- EMNLP 2026 submission: TBD
