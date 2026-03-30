# CTX: Trigger-Driven Dynamic Context Loading for Code-Aware LLM Agents

[![PyPI version](https://img.shields.io/pypi/v/ctx-retriever)](https://pypi.org/project/ctx-retriever/)
[![PyPI downloads](https://img.shields.io/pypi/dm/ctx-retriever)](https://pypi.org/project/ctx-retriever/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://pypi.org/project/ctx-retriever/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![HuggingFace Demo](https://img.shields.io/badge/HuggingFace-Demo-orange)](https://huggingface.co/spaces/Be2Jay/ctx-demo)
[![Publish to PyPI](https://github.com/jaytoone/CTX/actions/workflows/publish.yml/badge.svg)](https://github.com/jaytoone/CTX/actions/workflows/publish.yml)

CTX classifies developer queries into four trigger types and routes each to a specialized retrieval pipeline. For dependency-sensitive queries, CTX traverses the codebase import graph to resolve transitive relationships that keyword and embedding methods miss. It achieves **1.9x higher Token-Efficiency Score** than BM25 while using only **5.2% of tokens**.

> **Key insight**: code import graphs encode structural dependency information that text-based RAG cannot capture. CTX achieves Recall@5 = 1.0 on implicit dependency queries vs 0.4 for BM25.

## Install

```bash
pip install ctx-retriever
```

Or from source:

```bash
git clone https://github.com/jaytoone/CTX
cd CTX
pip install -e .
```

## Quick Start

```python
from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

# Point at any codebase directory
retriever = AdaptiveTriggerRetriever("/path/to/your/project")

# Retrieve relevant files for any natural-language query
result = retriever.retrieve(
    query_id="my_query",
    query_text="how does authentication work?",
    k=5
)

for filepath in result.retrieved_files:
    print(filepath, result.scores[filepath])
```

## Claude Code Hook (Recommended)

CTX works best as a **live hook** that automatically injects relevant files into every Claude Code prompt:

```bash
# 1. Copy the hook to Claude Code hooks directory
cp hooks/ctx_real_loader.py ~/.claude/hooks/

# 2. Register in ~/.claude/settings.json
```

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python3 $HOME/.claude/hooks/ctx_real_loader.py" }] }
    ]
  }
}
```

After setup, CTX automatically injects relevant files as context on every prompt. See [`docs/claude_code_integration.md`](docs/claude_code_integration.md) for full setup guide.

**What you get in each prompt:**
```
[CTX] Trigger: EXPLICIT_SYMBOL | Query: AuthService | Confidence: 0.70 | Intent: judge from prompt
Code files (3/847 total):
• src/auth/service.py [score=1.000]
• src/auth/middleware.py [score=0.823]
• tests/test_auth.py [score=0.741]
(Use the prompt intent to decide how to treat this context.)
```

## Trigger Types

| Trigger | When Used | Mechanism |
|---------|-----------|-----------|
| `EXPLICIT_SYMBOL` | Query names a class/function | Symbol index lookup |
| `SEMANTIC_CONCEPT` | Query describes a concept | BM25 keyword scoring |
| `IMPLICIT_CONTEXT` | Dependency queries ("what uses X") | BFS import graph traversal |
| `TEMPORAL_HISTORY` | Recent changes / history | Session file tracker |

## Results

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

**TES** = Recall@5 / ln(1 + files_loaded). Higher = better token efficiency.

### COIR External Benchmark (CodeSearchNet Python)

| Strategy | Recall@1 | Recall@5 | MRR |
|----------|----------|----------|-----|
| Dense Embedding (MiniLM) | 0.960 | 1.000 | 0.978 |
| Hybrid Dense+CTX | 0.930 | 0.950 | 0.940 |
| BM25 | 0.920 | 0.980 | 0.946 |
| CTX Adaptive Trigger | 0.210 | 0.380 | 0.293 |

### Key Findings

- CTX achieves **1.9x higher TES** than BM25 with only 5.2% token usage
- CTX achieves **perfect Recall@5 (1.0)** on IMPLICIT_CONTEXT dependency queries
- Trigger classifier achieves **100% accuracy** (all 4 types F1=1.00) on synthetic benchmark
- Hybrid Dense+CTX achieves R@5=0.950 on COIR — best of both worlds
- No single strategy dominates all dimensions — workload determines optimal choice

## Running Experiments

```bash
# Synthetic benchmark
python run_experiment.py --dataset-size small --strategy all

# Real codebase
python run_experiment.py --dataset-source real --project-path /path/to/project --strategy all

# COIR external benchmark
python run_coir_eval.py --n-queries 100

# Ablation study
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
      bm25_retriever.py   # BM25 sparse retrieval
      dense_retriever.py  # TF-IDF dense retrieval
      chroma_retriever.py # ChromaDB + sentence-transformers
      graph_rag.py        # GraphRAG-lite baseline
      llamaindex_retriever.py # LlamaIndex AST-aware chunking
      full_context.py     # Full context baseline
    trigger/              # Trigger classifier (4 types)
    evaluator/            # Benchmark runner, metrics, COIR
    data/                 # Dataset generation, real codebase loader
  hooks/
    ctx_real_loader.py    # Claude Code UserPromptSubmit hook
    ctx_session_tracker.py # PostToolUse session tracker
  benchmarks/
    results/              # Experiment results and reports
  docs/
    claude_code_integration.md  # Claude Code setup guide
    paper/                # Paper draft (markdown + LaTeX)
```

## Paper

- Paper draft: [`docs/paper/CTX_paper_draft.md`](docs/paper/CTX_paper_draft.md)
- arXiv: TBD
- EMNLP 2026 submission: TBD

## License

MIT
