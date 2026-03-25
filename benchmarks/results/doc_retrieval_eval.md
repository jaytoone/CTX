# CTX Document Retrieval Evaluation

**Project**: /home/jayone/Project/CTX
**Date**: 2026-03-25
**Metric**: Recall@3
**Queries**: 10

## Summary

| Method | Recall@3 |
|--------|-----------|
| CTX-doc (heading + keyword) | **0.600** |
| Random baseline | 0.000 |

**Lift over random**: random baseline = 0 (CTX-doc strictly better)

## Per-Query Results

| Query | Ground Truth | Hit@3 | Top-1 Result |
|-------|-------------|---------|-------------|
| trigger accuracy 실험 결과 | trigger_accuracy.md | MISS | hf_space/README.md |
| external codebase evaluation Flask FastAPI | external_codebase_eval.md | HIT | benchmarks/results/doc_retrieval_eval.md |
| LLM pass@1 openrouter gemini | llm_quality_openrouter.md | HIT | benchmarks/results/llm_quality_openrouter.md |
| repobench cross-file retrieval | repobench_eval.md | HIT | benchmarks/results/repobench_eval.md |
| CTX paper arXiv submission | paper_draft_outline.md | MISS | docs/paper/README.md |
| hybrid dense retrieval evaluation | hybrid_evaluation.md | HIT | benchmarks/results/hybrid_evaluation.md |
| ablation study variants | ablation_results.md | MISS | benchmarks/results/RESULTS_INDEX.md |
| error analysis failure patterns | error_analysis.md | HIT | benchmarks/results/RESULTS_INDEX.md |
| claude code hook integration | claude_code_integration.md | HIT | docs/claude_code_integration.md |
| differentiation CTX vs Memori | differentiation_analysis.md | MISS | docs/DOC_INDEX.md |

## Analysis

**Hits (6)**: external_codebase_eval.md, llm_quality_openrouter.md, repobench_eval.md, hybrid_evaluation.md, error_analysis.md, claude_code_integration.md

**Misses (4)**:
- Query: `trigger accuracy 실험 결과`
  Expected: `benchmarks/results/trigger_accuracy.md`
  Got: ['hf_space/README.md', 'benchmarks/results/differentiation_analysis.md', 'benchmarks/results/final_report_v2.md']
- Query: `CTX paper arXiv submission`
  Expected: `docs/paper_draft_outline.md`
  Got: ['docs/paper/README.md', 'docs/DOC_INDEX.md', 'docs/research/20260324-ctx-paper-worthiness.md']
- Query: `ablation study variants`
  Expected: `benchmarks/results/ablation_results.md`
  Got: ['benchmarks/results/RESULTS_INDEX.md', 'benchmarks/results/doc_retrieval_eval.md', 'docs/DOC_INDEX.md']
- Query: `differentiation CTX vs Memori`
  Expected: `benchmarks/results/differentiation_analysis.md`
  Got: ['docs/DOC_INDEX.md', 'docs/paper/README.md', 'benchmarks/results/repobench_eval.md']

## Method Description

CTX-doc uses a two-stage retrieval:
1. **Heading match**: Exact/partial match against document headings (Markdown `##`, YAML keys, TOML sections)
2. **Keyword fallback**: ASCII keyword frequency scoring across document content

Random baseline: uniformly sample 3 files from the 10-query corpus.