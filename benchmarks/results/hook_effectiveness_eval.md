# CTX Hook Effectiveness Evaluation

Date: 2026-03-25 16:02
Target: /home/jayone/Project/CTX
Total queries: 30

## Overall Metrics

| Metric | Value |
|--------|-------|
| Context Hit Rate (CHR) | 86.7% (26/30) |
| Mean Precision | 0.272 |
| Mean Response Time | 120.4 ms |

## Per-Trigger-Type Results

| Trigger Type | N | CHR | Mean Precision | Mean RT (ms) | Goal |
|-------------|---|-----|----------------|--------------|------|
| EXPLICIT_SYMBOL | 13 | 100.0% (PASS) | 0.171 | 119.8 | ≥ 80% |
| SEMANTIC_CONCEPT | 12 | 66.7% (PASS) | 0.078 | 126.8 | ≥ 60% |
| TEMPORAL_HISTORY | 5 | 100.0% (PASS) | 1.000 | 106.9 | ≥ 80% |

## Per-Query Results

| # | Trigger | Prompt | Hit | Precision | Files | RT(ms) |
|---|---------|--------|-----|-----------|-------|--------|
| 1 | EXPLICIT_S | TriggerClassifier class 구현 보여줘 | Y | 0.14 | 7 | 129.4 |
| 2 | EXPLICIT_S | AdaptiveTriggerRetriever retrieve 메서드 | Y | 0.14 | 7 | 126.2 |
| 3 | EXPLICIT_S | BenchmarkRunner class 어디있어? | Y | 0.14 | 7 | 121.6 |
| 4 | EXPLICIT_S | FullContextRetriever 구현 | Y | 0.17 | 6 | 120.9 |
| 5 | EXPLICIT_S | HybridDenseCTXRetriever 어떻게 동작해? | Y | 0.17 | 6 | 119.1 |
| 6 | EXPLICIT_S | TES metric 계산 함수 | Y | 0.12 | 8 | 119.6 |
| 7 | EXPLICIT_S | RANGERApproxRetriever 구현 보여줘 | Y | 0.17 | 6 | 117.3 |
| 8 | EXPLICIT_S | RepoBenchSample class 찾아줘 | Y | 0.14 | 7 | 116.4 |
| 9 | EXPLICIT_S | GraphRAGRetriever class | Y | 0.14 | 7 | 115.9 |
| 10 | EXPLICIT_S | LLMQualityEvaluator class | Y | 0.14 | 7 | 115.4 |
| 11 | SEMANTIC_C | token efficiency 계산 로직 | Y | 0.08 | 12 | 116.2 |
| 12 | SEMANTIC_C | import graph traversal 구현 | Y | 0.17 | 12 | 123.4 |
| 13 | SEMANTIC_C | recall at k 평가 로직 | N | 0.00 | 12 | 120.6 |
| 14 | SEMANTIC_C | LLM pass@1 실험 코드 | Y | 0.17 | 12 | 136.4 |
| 15 | SEMANTIC_C | BFS 구현 코드 | Y | 0.08 | 12 | 126.2 |
| 16 | SEMANTIC_C | trigger accuracy 실험 결과 | N | 0.00 | 12 | 132.0 |
| 17 | SEMANTIC_C | claude code integration 방법 | N | 0.00 | 12 | 131.3 |
| 18 | SEMANTIC_C | repobench evaluation 결과 | Y | 0.08 | 12 | 122.3 |
| 19 | SEMANTIC_C | external codebase flask fastapi 결과 | Y | 0.08 | 12 | 133.3 |
| 20 | SEMANTIC_C | openrouter gemini pass@1 결과 | Y | 0.08 | 12 | 137.6 |
| 21 | EXPLICIT_S | AdaptiveTriggerRetriever dependencies 이해 | Y | 0.29 | 7 | 115.1 |
| 22 | EXPLICIT_S | BenchmarkRunner imports 추적 | Y | 0.29 | 7 | 119.9 |
| 23 | EXPLICIT_S | HybridDenseCTXRetriever 의존 모듈 | Y | 0.17 | 6 | 120.0 |
| 24 | SEMANTIC_C | metrics.py 사용하는 코드 파악 | N | 0.00 | 12 | 123.0 |
| 25 | SEMANTIC_C | trigger_classifier 호출하는 모듈 | Y | 0.18 | 11 | 118.7 |
| 26 | TEMPORAL_H | 이전에 작업하던 파일 보여줘 | Y | 1.00 | 3 | 109.4 |
| 27 | TEMPORAL_H | 지난번에 편집한 코드 계속해줘 | Y | 1.00 | 3 | 107.4 |
| 28 | TEMPORAL_H | 방금 전에 봤던 함수 다시 보여줘 | Y | 1.00 | 3 | 105.5 |
| 29 | TEMPORAL_H | 이전 작업 이어서 진행 | Y | 1.00 | 4 | 105.6 |
| 30 | TEMPORAL_H | 최근 수정한 파일 목록 | Y | 1.00 | 4 | 106.7 |

## Failure Analysis

Total failures: 4/30

### Query 13: recall at k 평가 로직
- Trigger: SEMANTIC_CONCEPT (conf=0.5)
- Ground truth: ['src/evaluator/metrics.py', 'src/evaluator/benchmark_runner.py']
- Injected: ['src/evaluator/coir_evaluator.py', 'src/evaluator/repobench_evaluator.py', 'hf_space/app.py', 'src/analysis/differentiation.py', 'src/visualizer/report.py', 'src/evaluator/ranger_comparison.py', 'benchmarks/results/repobench_eval.md', 'benchmarks/results/ablation_results.md', 'benchmarks/results/report_ablation_small.txt', 'src/trigger/trigger_classifier.py', 'src/retrieval/adaptive_trigger.py', 'src/retrieval/hybrid_dense_ctx.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: recall at k 평가 로직 | Confidence: 0.50
Code files (6/92 total):
• src/evaluator/coir_evaluator.py [load_`

### Query 16: trigger accuracy 실험 결과
- Trigger: SEMANTIC_CONCEPT (conf=0.5)
- Ground truth: ['benchmarks/results/trigger_accuracy.md']
- Injected: ['src/trigger/trigger_classifier.py', 'src/analysis/trigger_accuracy.py', 'hf_space/app.py', 'src/retrieval/adaptive_trigger.py', 'src/evaluator/hook_effectiveness_eval.py', 'src/analysis/differentiation.py', 'hf_space/README.md', 'benchmarks/results/hook_effectiveness_eval.md', 'benchmarks/results/differentiation_analysis.md', 'src/retrieval/hybrid_dense_ctx.py', 'src/evaluator/metrics.py', 'src/evaluator/benchmark_runner.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: trigger accuracy 실험 결과 | Confidence: 0.50
Code files (6/92 total):
• src/trigger/trigger_classifier.py`

### Query 17: claude code integration 방법
- Trigger: SEMANTIC_CONCEPT (conf=0.5)
- Ground truth: ['docs/claude_code_integration.md']
- Injected: ['src/evaluator/coir_evaluator.py', 'hf_space/app.py', 'src/evaluator/repobench_evaluator.py', 'run_llm_eval_opensource.py', 'src/evaluator/benchmark_runner.py', 'src/evaluator/llm_quality.py', 'benchmarks/results/coir_evaluation.md', 'benchmarks/results/doc_retrieval_eval.md', 'docs/research/20260325-ctx-paper-tier-evaluation.md', 'src/trigger/trigger_classifier.py', 'src/retrieval/adaptive_trigger.py', 'src/retrieval/hybrid_dense_ctx.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: claude code integration 방법 | Confidence: 0.50
Code files (6/92 total):
• src/evaluator/coir_evaluator.`

### Query 24: metrics.py 사용하는 코드 파악
- Trigger: SEMANTIC_CONCEPT (conf=0.5)
- Ground truth: ['src/evaluator/metrics.py']
- Injected: ['src/evaluator/benchmark_runner.py', 'src/evaluator/ranger_comparison.py', 'src/visualizer/report.py', 'hf_space/app.py', 'src/analysis/trigger_accuracy.py', 'src/evaluator/repobench_evaluator.py', 'benchmarks/results/hook_effectiveness_eval.md', 'benchmarks/results/statistical_tests_real_GraphPrompt.json', 'benchmarks/results/statistical_tests_real_eval_requests.json', 'src/trigger/trigger_classifier.py', 'src/retrieval/adaptive_trigger.py', 'src/retrieval/hybrid_dense_ctx.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: metrics.py 사용하는 코드 파악 | Confidence: 0.50
Code files (6/92 total):
• src/evaluator/benchmark_runner.py `


## Session Continuity Detail

- [HIT] 이전에 작업하던 파일 보여줘
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 작업하던 | Confidence: 0.90
Recent session (3 files):
• `
- [HIT] 지난번에 편집한 코드 계속해줘
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 지난번 | Confidence: 0.80
Recent session (3 files):
• s`
- [HIT] 방금 전에 봤던 함수 다시 보여줘
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 방금 | Confidence: 0.80
Recent session (3 files):
• sr`
- [HIT] 이전 작업 이어서 진행
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 이전 작업 | Confidence: 0.80
Doc files (1/76 total):
• b`
- [HIT] 최근 수정한 파일 목록
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 최근 수정 | Confidence: 0.65
Doc files (1/76 total):
• b`