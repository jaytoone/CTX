# CTX LLM Downstream Quality Report v2 (pass@1, 50 samples)

**Date**: 2026-03-24T16:24:29.515791
**Model**: MiniMax-M2.5
**Project**: GraphPrompt
**Total Samples**: 49 (15 reused + 34 new)
**Seed**: 42

---

## Results Summary

| Strategy | pass@1 | 95% CI | Passed | Total | Errors | Avg Context Tokens |
|----------|--------|--------|--------|-------|--------|--------------------|
| Full Context | 0.102 | [0.044, 0.218] | 5 | 49 | 3 | 11952 |
| Adaptive Trigger | 0.265 | [0.162, 0.403] | 13 | 49 | 4 | 1406 |

**Improvement**: +160.0% (Adaptive Trigger vs Full Context)

---

## Statistical Significance (McNemar Test)

| Metric | Value |
|--------|-------|
| Chi-squared | 3.5000 |
| p-value | 0.0614 |
| Significant (p<0.05)? | No |
| Both Pass | 2 |
| FC Only Pass | 3 |
| AT Only Pass | 11 |
| Both Fail | 33 |

---

## Per-Sample Results

| # | Function | File | Full Context | Adaptive Trigger |
|---|----------|------|-------------|-----------------|
| 1 | `load_full_text` | p0-legal-rag/legal_rag/loader.py | PASS | FAIL |
| 2 | `test_geval_score_strips_think` | p0-prompt-eval/tests/test_geval.py | FAIL | FAIL |
| 3 | `test_run_blocked_import` | p0-prompt-eval/tests/test_code_runner.py | FAIL | PASS |
| 4 | `detect_task_type` | graphprompt-mcp/server.py | FAIL | FAIL |
| 5 | `rerank_with_scores` | korag-serve/rag/reranker.py | FAIL | PASS |
| 6 | `render_chat` | p0-rag-demo/app.py | PASS | FAIL |
| 7 | `run_llamacpp_bench` | korag-serve/bench/llamacpp_bench.py | FAIL | PASS |
| 8 | `test_run_multiline_output` | p0-prompt-eval/tests/test_code_runner.py | FAIL | FAIL |
| 9 | `test_run_syntax_error` | p0-prompt-eval/tests/test_code_runner.py | PASS | PASS |
| 10 | `load_checkpoint_df` | p0-prompt-eval/eval/mixed_effects.py | FAIL | PASS |
| 11 | `ask` | korag-serve/rag/pipeline.py | FAIL | FAIL |
| 12 | `save_results` | p0-rag-demo/eval/run_eval.py | FAIL | FAIL |
| 13 | `get_embeddings` | p0-rag-demo/rag/embedder.py | PASS | FAIL |
| 14 | `test_g2_hypothesis_before_question` | p0-prompt-eval/tests/test_builders.py | FAIL | FAIL |
| 15 | `run_benchmark` | p0-vllm-serving/benchmark.py | FAIL | FAIL |
| 16 | `load_and_split` | korag-serve/rag/chunker.py | FAIL | PASS |
| 17 | `init_session_state` | p0-agent-demo/app.py | FAIL | FAIL |
| 18 | `build_prompt` | p0-prompt-eval/prompts/builders.py | FAIL | FAIL |
| 19 | `test_geval_code_quality_metric` | p0-prompt-eval/tests/test_geval.py | FAIL | PASS |
| 20 | `build_rag_pipeline` | p0-rag-demo/eval/run_eval.py | FAIL | FAIL |
| 21 | `augment_prompt` | graphprompt-mcp/augmentor.py | FAIL | FAIL |
| 22 | `match_risk_to_annotation` | p0-legal-rag/eval/benchmark.py | FAIL | FAIL |
| 23 | `create_llm` | p0-agent-demo/config.py | ERROR | PASS |
| 24 | `cohen_kappa` | p0-prompt-eval/eval/annotator_glm.py | FAIL | FAIL |
| 25 | `lifespan` | p0-vllm-serving/client.py | FAIL | PASS |
| 26 | `extract_code_block` | p0-prompt-eval/eval/code_runner.py | FAIL | ERROR |
| 27 | `create_rag_chain` | p0-legal-rag/legal_rag/chain.py | FAIL | FAIL |
| 28 | `analyze_contract` | p0-legal-rag/api.py | FAIL | FAIL |
| 29 | `run_code` | p0-prompt-eval/eval/code_runner.py | FAIL | FAIL |
| 30 | `glm_judge_multihop` | p0-prompt-eval/eval/annotator_glm.py | FAIL | PASS |
| 31 | `run_ragas_evaluation` | p0-rag-demo/eval/evaluator.py | FAIL | FAIL |
| 32 | `test_run_timeout` | p0-prompt-eval/tests/test_code_runner.py | FAIL | FAIL |
| 33 | `run_ollama_bench` | korag-serve/bench/ollama_bench.py | FAIL | ERROR |
| 34 | `test_geval_coherence_metric` | p0-prompt-eval/tests/test_geval.py | FAIL | PASS |
| 35 | `measure_single_request` | korag-serve/bench/ollama_bench.py | FAIL | FAIL |
| 36 | `benchmark_endpoint` | p0-vllm-serving/client.py | FAIL | FAIL |
| 37 | `get_fewshot_text` | graphprompt-mcp/fewshots.py | FAIL | FAIL |
| 38 | `start_vllm_server` | p0-vllm-serving/server.py | FAIL | FAIL |
| 39 | `split_texts` | korag-serve/rag/chunker.py | FAIL | FAIL |
| 40 | `is_llamacpp_available` | korag-serve/bench/llamacpp_bench.py | FAIL | FAIL |
| 41 | `chat` | p0-vllm-serving/client.py | FAIL | FAIL |
| 42 | `test_cache_different_contexts` | p0-prompt-eval/tests/test_graph_extractor.py | ERROR | PASS |
| 43 | `get_qa_pairs_by_domain` | korag-serve/eval/ko_dataset.py | FAIL | FAIL |
| 44 | `save_mixed_effects_report` | p0-prompt-eval/eval/mixed_effects.py | ERROR | ERROR |
| 45 | `glm_judge_coding` | p0-prompt-eval/eval/annotator_glm.py | FAIL | FAIL |
| 46 | `is_ollama_running` | korag-serve/bench/ollama_bench.py | FAIL | FAIL |
| 47 | `get_all_sample_docs` | korag-serve/eval/ko_dataset.py | FAIL | FAIL |
| 48 | `test_run_wrong_output` | p0-prompt-eval/tests/test_code_runner.py | FAIL | ERROR |
| 49 | `build_ragas_llm` | p0-rag-demo/eval/evaluator.py | PASS | PASS |

---

## Context Token Comparison

Full Context uses a fixed context window of ~11952 tokens for all queries.
Adaptive Trigger uses variable context, averaging ~1406 tokens per query.
Token reduction: 88.2% fewer tokens.

---

*Generated by CTX LLM Quality Evaluation v2 (2026-03-24T16:24:29.515791)*