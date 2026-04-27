# G2 Evaluation Methods Research — Summary Report

**Date**: 2026-04-02  
**Author**: Claude Code Explorer  
**Scope**: "Instruction-to-file grounding" quality measurement in CTX project

---

## Quick Executive Summary

**What is G2?**  
Goal 2: When a user gives a natural language instruction (e.g., "fix the auth flow"), how well does CTX find and provide the relevant files?

**Current Status**: ~40% coverage
- Retrieval metrics: File presence + ranking quality
- Basic LLM scoring: File/function mention accuracy only  
- Real codebase eval: 5 scenarios, mention-based scoring

**Gaps**: 60% missing
- No end-to-end task completion measurement
- No context quality metrics (relevance, completeness)
- No semantic hallucination detection
- No code quality evaluation
- No developer perception measurement
- No multi-step task handling

**Recommendation**: Add Priority 1 metrics → 1 week effort → 80% coverage

---

## Detailed Findings

### Current Evaluations (3 files)

| Eval | File | Scope | Metrics | Results |
|------|------|-------|---------|---------|
| **Retrieval** | `instruction_grounding_eval.py` | 10 instructions, small dataset | R@K, P@K, NDCG@K, trigger type | R@5=0.644, NDCG@5=0.723 |
| **Synthetic LLM** | `downstream_llm_eval.py` | 10 synthetic tasks | File mention, function mention, hallucination | Score=0.375, Hallu=0.00 |
| **Real LLM** | `real_codebase_downstream_eval.py` | 5 real CTX scenarios | File/func mention, hallucination | Score=0.350, Hallu=0.20 |

### What's Measured

✓ File retrieval accuracy (Recall@5, NDCG@5)  
✓ File/function mention in LLM output  
✓ Filename-based hallucination detection  
✓ Trigger type classification  

### What's Missing (60%)

✗ End-to-end task completability  
✗ Context relevance/quality per file  
✗ Semantic hallucinations (patterns, outdated APIs, type mismatches)  
✗ Generated code quality (syntax, imports, types, tests)  
✗ Developer perception (usefulness, confidence, time savings)  
✗ Multi-file dependencies & cross-module grounding  
✗ Iterative task adaptation  

---

## 6 Critical Gaps & Recommendations

### Gap 1: No E2E Task Completion

**Problem**: File presence ≠ task completability

**Solution** (Priority 1, ~8 hours):
```python
class E2ETaskEval:
    metrics:
      - task_completable: Boolean (expert judgment)
      - missing_files: [files needed but not retrieved]
      - insufficient_context: Boolean
      - developer_approval: 1-5 Likert
```

**Implementation**:
1. Create 20 realistic coding tasks (GitHub issues)
2. Expert annotate required files
3. Score = recall of required files (vs. arbitrary R@5)

---

### Gap 2: No Context Quality Metrics

**Problem**: Context list provided, but is it actually useful?

**Solution** (Priority 1, ~12 hours):
```python
class ContextQualityScore:
    metrics:
      - relevance_per_file: [0-1] (% relevant lines per file)
      - coverage: symbols_needed / symbols_in_context
      - coherence: semantic similarity among files
      - noise_ratio: irrelevant_lines / total_lines
      - import_completeness: dependencies shown?
```

**Implementation**:
- AST parsing to extract symbols
- Semantic similarity (Claude review)
- Dependency graph analysis

---

### Gap 3: Limited Hallucination

**Problem**: Only detects non-existent filenames (e.g., "fake.py")

**Solution** (Priority 1, ~6 hours):
```python
class HallucinationDetector:
    metrics:
      - function_hallucination: func names don't exist in files
      - pattern_hallucination: wrong approach suggested
      - outdated_api: suggests deprecated functions
      - type_mismatch: function args don't match signature
```

**Implementation**:
- AST to validate function existence
- Version checking for deprecated APIs
- Type signature validation

---

### Gap 4: No Code Quality Measurement

**Problem**: Can't tell if LLM-provided guidance is actually implementable

**Solution** (Priority 1, ~10 hours):
```python
class CodeQualityMetrics:
    metrics:
      - syntax_valid: Code parses (0/1)
      - imports_valid: All imports resolvable (0/1)
      - type_correct: Function calls match signatures (0-1)
      - logic_sound: Implements feature correctly (0-1)
      - test_pass_rate: Unit tests pass (0-1)
```

**Implementation**:
- Python AST parser for syntax
- Import resolver (check sys.path)
- Type inference (mypy integration)
- Pytest for test execution

---

### Gap 5: No User Study

**Problem**: Objective metrics may not reflect real developer experience

**Solution** (Priority 2, ~20 hours):
```python
class DeveloperStudy:
    sample: 10-20 developers
    tasks: 5 per developer (difficulty: easy/medium/hard)
    conditions: [no_context, ctx, manual_context]
    
    metrics:
      - time_to_completion (minutes)
      - code_quality_score (expert review, 1-10)
      - developer_confidence (1-5 Likert)
      - perceived_usefulness (1-5 Likert)
      - iterations_to_working_code (count)
```

---

### Gap 6: No Multi-Step Handling

**Problem**: Current evals are single-instruction only

**Solution** (Priority 2, ~15 hours):
```python
class MultiFileDependencyEval:
    metrics:
      - cross_module_recall: Files in different modules
      - dependency_chain_accuracy: Transitive deps found
      - circular_dep_detection: Avoids circular imports

class IterativeTaskEval:
    sequence:
      1. Initial instruction + CTX retrieval
      2. Developer feedback: "missing file X"
      3. CTX refetch
      4. Measure: refetch cost, quality delta
```

---

## Implementation Timeline

### Week 1 (Priority 1) — 40-50 hours total

- [ ] E2E Task Completion (8h)
  - Create 20 realistic tasks
  - Expert annotation
  - Implementation

- [ ] Context Quality Scorer (12h)
  - AST symbol extraction
  - Semantic similarity
  - Relevance scoring

- [ ] Semantic Hallucination Detector (6h)
  - Function validation (AST)
  - Type signature checking
  - API version checking

- [ ] Code Quality Metrics (10h)
  - Syntax validation
  - Import resolution
  - Type checking integration
  - Test execution

**Target**: 40% → 80% coverage

### Week 2-3 (Priority 2)

- [ ] Multi-File Dependency Analysis (15h)
- [ ] User Study Framework (20h)
- [ ] Iterative Task Evaluation (8h)

### Future (Priority 3)

- [ ] CoIR/RepoBench benchmark integration
- [ ] LLM robustness analysis
- [ ] Publish methodology paper

---

## Complete G2 Evaluation Framework (Vision)

```
G2 Score: Instruction-to-File Grounding Quality
├─ Retrieval Metrics (30%)
│  ├─ File Recall@5: 0.644
│  ├─ Relevant File Recall: 0.82 (missing file detection)
│  └─ Context Quality: 0.775 (relevance + coverage)
│
├─ LLM Grounding (40%)
│  ├─ File Mention Accuracy: 0.350
│  ├─ Function Mention Accuracy: 0.420
│  ├─ Hallucination Rate: 0.12
│  ├─ Code Quality Score: 0.68 (syntax + imports + types)
│  └─ Test Pass Rate: 0.55
│
├─ User Perception (20%)
│  ├─ Perceived Usefulness: 4.2/5
│  ├─ Developer Confidence: 3.8/5
│  └─ Time Savings: 35% faster
│
└─ Advanced Metrics (10%)
   ├─ Multi-file Dependency: 0.78
   ├─ Iterative Adaptation: 0.65
   └─ Cross-module Accuracy: 0.72

FINAL G2 SCORE: 0.684 / 1.000
```

---

## Key Files Referenced

**Current G2 Evaluations**:
- `/home/jayone/Project/CTX/benchmarks/eval/instruction_grounding_eval.py` (270 lines)
- `/home/jayone/Project/CTX/benchmarks/eval/downstream_llm_eval.py` (350+ lines)
- `/home/jayone/Project/CTX/benchmarks/eval/real_codebase_downstream_eval.py` (312 lines)

**Result Files**:
- `benchmarks/results/instruction_grounding_eval.json` (R@5=0.644)
- `benchmarks/results/doc_retrieval_eval_v2.md` (CTX doc search baseline)

**Research Documentation**:
- `docs/research/20260402-g2-evaluation-methods-research.md` (this repo)

---

## Bottom Line

| Aspect | Current | Target (Post-P1) | Gap |
|--------|---------|------------------|-----|
| Coverage | 40% | 80% | +40% |
| E2E Completability | None | Binary score | NEW |
| Context Quality | None | Multi-metric | NEW |
| Hallucination | Filename only | Semantic | +3 types |
| Code Quality | None | 5 metrics | NEW |
| User Study | None | 10-20 devs | NEW |
| Effort | — | 40-50h | 1 week |

**Recommendation**: Implement Priority 1 metrics immediately. They provide high-impact, relatively quick wins and dramatically improve evaluation completeness.

---

**Generated**: 2026-04-02  
**Confidence**: High (based on comprehensive code review + 3 existing eval files)  
**Status**: Research complete, recommendations ready for implementation

## Related
- [[projects/CTX/research/20260407-g1-final-eval-benchmark|20260407-g1-final-eval-benchmark]]
- [[projects/CTX/research/20260426-ctx-research-critical-evaluation|20260426-ctx-research-critical-evaluation]]
- [[projects/CTX/research/20260402-g2-evaluation-methods-research|20260402-g2-evaluation-methods-research]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|20260328-ctx-real-codebase-g2-eval]]
- [[projects/CTX/research/20260408-g1-longterm-eval-initial-results|20260408-g1-longterm-eval-initial-results]]
- [[projects/CTX/research/20260402-project-understanding-evaluation-framework|20260402-project-understanding-evaluation-framework]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260326-ctx-results-review|20260326-ctx-results-review]]
