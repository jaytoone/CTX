# CTX Hook Effectiveness Evaluation

Date: 2026-03-25 15:53
Target: /home/jayone/Project/CTX
Total queries: 30

## Overall Metrics

| Metric | Value |
|--------|-------|
| Context Hit Rate (CHR) | 70.0% (21/30) |
| Mean Precision | 0.198 |
| Mean Response Time | 116.9 ms |

## Per-Trigger-Type Results

| Trigger Type | N | CHR | Mean Precision | Mean RT (ms) | Goal |
|-------------|---|-----|----------------|--------------|------|
| EXPLICIT_SYMBOL | 15 | 86.7% (PASS) | 0.161 | 116.1 | ≥ 80% |
| SEMANTIC_CONCEPT | 13 | 46.2% (FAIL) | 0.116 | 113.2 | ≥ 60% |
| TEMPORAL_HISTORY | 2 | 100.0% (PASS) | 1.000 | 146.3 | ≥ 80% |

## Per-Query Results

| # | Trigger | Prompt | Hit | Precision | Files | RT(ms) |
|---|---------|--------|-----|-----------|-------|--------|
| 1 | EXPLICIT_S | TriggerClassifier class 구현 보여줘 | Y | 0.14 | 7 | 124.5 |
| 2 | EXPLICIT_S | AdaptiveTriggerRetriever retrieve 메서드 | Y | 0.14 | 7 | 122.3 |
| 3 | EXPLICIT_S | BenchmarkRunner class 어디있어? | Y | 0.14 | 7 | 120.7 |
| 4 | EXPLICIT_S | FullContextRetriever 구현 | Y | 0.25 | 4 | 120.3 |
| 5 | EXPLICIT_S | HybridDenseCTXRetriever 어떻게 동작해? | Y | 0.25 | 4 | 118.9 |
| 6 | EXPLICIT_S | TES metric 계산 함수 | Y | 0.12 | 8 | 121.0 |
| 7 | EXPLICIT_S | RANGERApproxRetriever 구현 보여줘 | Y | 0.25 | 4 | 116.6 |
| 8 | EXPLICIT_S | RepoBenchSample class 찾아줘 | Y | 0.14 | 7 | 127.3 |
| 9 | EXPLICIT_S | GraphRAGRetriever class | Y | 0.14 | 7 | 125.2 |
| 10 | EXPLICIT_S | LLMQualityEvaluator class | Y | 0.14 | 7 | 120.8 |
| 11 | SEMANTIC_C | token efficiency 계산 로직 | N | 0.00 | 12 | 120.4 |
| 12 | SEMANTIC_C | import graph traversal 구현 | Y | 0.08 | 12 | 126.2 |
| 13 | SEMANTIC_C | recall at k 평가 로직 | N | 0.00 | 12 | 121.8 |
| 14 | EXPLICIT_S | LLM pass@1 실험 코드 | N | 0.00 | 7 | 115.8 |
| 15 | EXPLICIT_S | BFS 구현 코드 | N | 0.00 | 0 | 31.1 |
| 16 | SEMANTIC_C | trigger accuracy 실험 결과 | N | 0.00 | 11 | 129.6 |
| 17 | SEMANTIC_C | claude code integration 방법 | N | 0.00 | 12 | 163.1 |
| 18 | SEMANTIC_C | repobench evaluation 결과 | Y | 0.08 | 12 | 120.9 |
| 19 | SEMANTIC_C | external codebase flask fastapi 결과 | Y | 0.08 | 12 | 133.7 |
| 20 | SEMANTIC_C | openrouter gemini pass@1 결과 | Y | 0.08 | 12 | 129.9 |
| 21 | EXPLICIT_S | AdaptiveTriggerRetriever dependencies 이해 | Y | 0.29 | 7 | 130.7 |
| 22 | EXPLICIT_S | BenchmarkRunner imports 추적 | Y | 0.14 | 7 | 125.3 |
| 23 | EXPLICIT_S | HybridDenseCTXRetriever 의존 모듈 | Y | 0.25 | 4 | 121.7 |
| 24 | SEMANTIC_C | metrics.py 사용하는 코드 파악 | N | 0.00 | 12 | 119.2 |
| 25 | SEMANTIC_C | trigger_classifier 호출하는 모듈 | Y | 0.18 | 11 | 117.2 |
| 26 | TEMPORAL_H | 이전에 작업하던 파일 보여줘 | Y | 1.00 | 3 | 112.1 |
| 27 | TEMPORAL_H | 지난번에 편집한 코드 계속해줘 | Y | 1.00 | 3 | 180.5 |
| 28 | SEMANTIC_C | 방금 전에 봤던 함수 다시 보여줘 | Y | 1.00 | 3 | 107.0 |
| 29 | SEMANTIC_C | 이전 작업 이어서 진행 | N | 0.00 | 0 | 46.6 |
| 30 | SEMANTIC_C | 최근 수정한 파일 목록 | N | 0.00 | 0 | 36.4 |

## Failure Analysis

Total failures: 9/30

### Query 11: token efficiency 계산 로직
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: ['src/evaluator/metrics.py']
- Injected: ['run_llm_eval_opensource.py', 'run_llm_eval_openrouter.py', 'run_llm_eval_v2.py', 'hf_space/app.py', 'src/retrieval/adaptive_trigger.py', 'run_llm_eval.py', 'benchmarks/results/external_codebase_eval.md', 'benchmarks/results/ablation_results.md', 'benchmarks/results/repobench_eval.md', 'docs/paper/CTX_paper.tex', 'src/trigger/trigger_classifier.py', 'src/evaluator/hook_effectiveness_eval.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: token efficiency 계산 로직 | Confidence: 0.30
Code files (6/92 total):
• run_llm_eval_opensource.py [compu`

### Query 13: recall at k 평가 로직
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: ['src/evaluator/metrics.py', 'src/evaluator/benchmark_runner.py']
- Injected: ['src/evaluator/coir_evaluator.py', 'src/evaluator/repobench_evaluator.py', 'hf_space/app.py', 'src/analysis/differentiation.py', 'src/visualizer/report.py', 'src/evaluator/ranger_comparison.py', 'benchmarks/results/repobench_eval.md', 'benchmarks/results/ablation_results.md', 'benchmarks/results/report_ablation_small.txt', 'docs/paper/CTX_paper.tex', 'src/trigger/trigger_classifier.py', 'src/evaluator/hook_effectiveness_eval.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: recall at k 평가 로직 | Confidence: 0.30
Code files (6/92 total):
• src/evaluator/coir_evaluator.py [load_`

### Query 14: LLM pass@1 실험 코드
- Trigger: EXPLICIT_SYMBOL (conf=0.7)
- Ground truth: ['run_llm_eval_openrouter.py', 'run_llm_eval_opensource.py']
- Injected: ['src/evaluator/llm_quality.py', 'benchmarks/results/llm_quality_openrouter.md', 'benchmarks/results/llm_quality_report.md', 'benchmarks/results/llm_quality_report_v2.md', 'docs/paper/CTX_paper.tex', 'src/trigger/trigger_classifier.py', 'src/evaluator/hook_effectiveness_eval.py']
- Context preview: `[CTX/Python] Trigger: EXPLICIT_SYMBOL | Query: LLM | Confidence: 0.70
Code files (1/92 total):
• src/evaluator/llm_quality.py [extract_functions_from_`

### Query 15: BFS 구현 코드
- Trigger: EXPLICIT_SYMBOL (conf=0.7)
- Ground truth: ['src/retrieval/adaptive_trigger.py']
- Injected: []
- Context preview: ``

### Query 16: trigger accuracy 실험 결과
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: ['benchmarks/results/trigger_accuracy.md']
- Injected: ['src/trigger/trigger_classifier.py', 'src/analysis/trigger_accuracy.py', 'hf_space/app.py', 'src/retrieval/adaptive_trigger.py', 'src/evaluator/hook_effectiveness_eval.py', 'src/analysis/differentiation.py', 'hf_space/README.md', 'benchmarks/results/differentiation_analysis.md', 'benchmarks/results/final_report_v2.md', 'docs/paper/CTX_paper.tex', 'docs/DOC_INDEX.md']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: trigger accuracy 실험 결과 | Confidence: 0.30
Code files (6/92 total):
• src/trigger/trigger_classifier.py`

### Query 17: claude code integration 방법
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: ['docs/claude_code_integration.md']
- Injected: ['src/evaluator/coir_evaluator.py', 'hf_space/app.py', 'src/evaluator/repobench_evaluator.py', 'run_llm_eval_opensource.py', 'src/evaluator/benchmark_runner.py', 'src/evaluator/llm_quality.py', 'benchmarks/results/coir_evaluation.md', 'benchmarks/results/doc_retrieval_eval.md', 'docs/research/20260325-ctx-paper-tier-evaluation.md', 'docs/paper/CTX_paper.tex', 'src/trigger/trigger_classifier.py', 'src/evaluator/hook_effectiveness_eval.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: claude code integration 방법 | Confidence: 0.30
Code files (6/92 total):
• src/evaluator/coir_evaluator.`

### Query 24: metrics.py 사용하는 코드 파악
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: ['src/evaluator/metrics.py']
- Injected: ['src/evaluator/benchmark_runner.py', 'src/evaluator/ranger_comparison.py', 'src/visualizer/report.py', 'hf_space/app.py', 'src/analysis/trigger_accuracy.py', 'src/evaluator/repobench_evaluator.py', 'benchmarks/results/statistical_tests_real_GraphPrompt.json', 'benchmarks/results/statistical_tests_real_eval_requests.json', 'benchmarks/results/statistical_tests_real_eval_fastapi.json', 'docs/paper/CTX_paper.tex', 'src/trigger/trigger_classifier.py', 'src/evaluator/hook_effectiveness_eval.py']
- Context preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: metrics.py 사용하는 코드 파악 | Confidence: 0.30
Code files (6/92 total):
• src/evaluator/benchmark_runner.py `

### Query 29: 이전 작업 이어서 진행
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: None
- Injected: []
- Context preview: ``

### Query 30: 최근 수정한 파일 목록
- Trigger: SEMANTIC_CONCEPT (conf=0.3)
- Ground truth: None
- Injected: []
- Context preview: ``


## Session Continuity Detail

- [HIT] 이전에 작업하던 파일 보여줘
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 이전에 | Confidence: 0.65
Recent session (3 files):
• s`
- [HIT] 지난번에 편집한 코드 계속해줘
  Preview: `[CTX/Python] Trigger: TEMPORAL_HISTORY | Query: 지난번 | Confidence: 0.65
Recent session (3 files):
• s`
- [HIT] 방금 전에 봤던 함수 다시 보여줘
  Preview: `[CTX/Python] Trigger: SEMANTIC_CONCEPT | Query: 방금 전에 봤던 함수 다시 보여줘 | Confidence: 0.30
Recent session`
- [MISS] 이전 작업 이어서 진행
  Preview: ``
- [MISS] 최근 수정한 파일 목록
  Preview: ``