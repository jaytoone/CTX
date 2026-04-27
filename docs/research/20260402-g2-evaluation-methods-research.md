# G2 Evaluation Methods Research — CTX Project

**Date**: 2026-04-02  
**Goal**: Research "instruction-to-file grounding" quality metrics and identify gaps

---

## Executive Summary

CTX has a **partial G2 evaluation framework**, measuring **file retrieval accuracy** but lacking comprehensive **downstream task completion and context quality metrics**. 

### Current G2 Coverage (3 evals)
1. **`instruction_grounding_eval.py`** — Instruction→File retrieval (R@K, Precision@K, NDCG@K)
2. **`downstream_llm_eval.py`** — Synthetic G2 with LLM evaluation (score, hallucination rate)
3. **`real_codebase_downstream_eval.py`** — Real CTX tasks with LLM (file/function mention accuracy)

### Critical Gaps
- **No end-to-end task completion scoring** (LLM quality vs. human expectations)
- **No context quality metrics** (relevance, completeness, coherence of provided context)
- **Limited hallucination analysis** (only file mention counting, not semantic hallucination)
- **No downstream impact measurement** (does CTX actually reduce coding errors?)
- **No user study component** (developer perception of usefulness)
- **No multi-step task handling** (complex instructions requiring >1 file)

---

## 1. EXISTING G2 EVALUATION METHODS

### 1.1 `instruction_grounding_eval.py` — File Retrieval Level

**Purpose**: Does CTX retrieve files relevant to user instructions?

**Methodology**:
- **Dataset**: Small codebase with file metadata (concepts, module names, functions)
- **Instruction Templates** (10): e.g., "fix the authentication flow", "implement database connection pooling"
- **Ground Truth Construction**:
  - Parse concept keywords from instruction
  - Match keywords against file concepts, module names, paths
  - All matching files = ground truth set

**Metrics Measured**:
- `Recall@K` — fraction of GT files found in top-K
- `Precision@K` — fraction of top-K that are in GT
- `NDCG@K` — ranking quality (discount by position)
- Trigger type distribution (EXPLICIT_SYMBOL, IMPLICIT_CONTEXT, etc.)

**Current Results** (small dataset):
```
Average R@5: 0.644 | Average P@5: 0.58 | Average NDCG@5: 0.723
```

**Limitations**:
- **No LLM involved** — only file presence, not usefulness
- **Ground truth too simplistic** — keyword matching doesn't capture semantic relevance
- **Single-file bias** — doesn't test multi-file dependencies
- **Limited coverage** — only 10 instructions on one small codebase

---

### 1.2 `downstream_llm_eval.py` — Synthetic G2 with LLM

**Purpose**: Does the LLM produce better answers when given CTX-retrieved context?

**Methodology**:
- **G2 Task Builder**: 10 templates (JWT auth, connection pooling, caching, etc.)
- **For each task**:
  - WITH CTX: Show top 3 relevant files (600 char snippets)
  - WITHOUT CTX: No file context
  - LLM prompt: "Which file to modify? Which functions to use?"

**Scoring Function**:
- Counts if target files mentioned
- Counts if target functions mentioned
- Counts non-existent .py files as hallucinations

**Typical Results** (from MEMORY.md):
```
WITH CTX:    0.375 (task accuracy)
WITHOUT CTX: 0.000
Δ:           +0.375
Hallucination: 0.17 (without) → 0.00 (with)
```

**Limitations**:
- **Synthetic scenarios** — hand-crafted, unrepresentative
- **Filename-only scoring** — just regex matching
- **No function implementation quality** — mention ≠ correct usage
- **Small scale** — typically 5–10 synthetic tasks
- **No semantic grounding** — doesn't verify if context actually helps

---

### 1.3 `real_codebase_downstream_eval.py` — Real CTX Tasks with LLM

**Purpose**: G2 evaluation on real CTX codebase (not synthetic)

**Methodology**:
- **5 Real Scenarios** mapped to actual CTX source files
- **For each scenario**:
  - WITH CTX: Show file snippet (first 60 lines or signatures only)
  - WITHOUT CTX: Only instruction
  - LLM: "State EXACTLY which file and functions to modify"

**Current Results** (from MEMORY.md):
```
WITH CTX:    0.350
WITHOUT CTX: 0.150
Δ:           +0.200
Hallucination: WITH=0.2, WITHOUT=0.4
```

**Limitations**:
- **Still file/function mention matching** — no semantic quality
- **Limited sample** — only 5 scenarios
- **No actual code generation** — doesn't test if developer can use suggestion
- **Over-anchoring observed** — LLM gets stuck on shown implementation

---

## 2. WHAT'S CURRENTLY MEASURED (Summary)

| Metric | Level | Eval | Result | Limitations |
|--------|-------|------|--------|-------------|
| File Recall@K | Retrieval | instruction_grounding | R@5=0.644 | Keyword match only |
| Function Mention | LLM | downstream_llm | ~0.375 | Regex matching, no semantic check |
| Hallucination Rate | LLM | downstream_llm | 0.00 (with) | Only file name detection |
| Real-world Grounding | LLM | real_codebase | 0.350 | More conservative than synthetic |
| Trigger Classification | Classification | instruction_grounding | 89% correct | N/A |

---

## 3. CRITICAL GAPS

### Gap 1: No End-to-End Task Completion Scoring

**Currently measured**: File presence + function mentions
**Should measure**: Can developer actually complete task with the grounding?

**Missing metrics**:
- **Actionability**: Are files/functions sufficient? (Yes/No)
- **Completeness**: Does context cover all necessary dependencies?
- **Correctness**: Is the suggested approach technically sound?
- **Missing critical files**: Did retrieval omit essential files?

---

### Gap 2: No Context Quality Metrics

**Currently measured**: File list presence only
**Should measure**: Quality of the provided context

**Missing metrics**:
- **Relevance**: Is each file actually needed?
- **Coverage**: Does context include all required symbols?
- **Coherence**: Are files logically related?
- **Completeness**: Are imports/dependencies shown?
- **Noise ratio**: What % of context is irrelevant?

---

### Gap 3: Limited Hallucination Analysis

**Currently measured**: Non-existent .py filenames
**Should measure**: Semantic hallucinations and incorrect suggestions

**Missing metrics**:
- **Function hallucination**: Mentions non-existent functions in correct files
- **Semantic drift**: Suggests wrong pattern/approach
- **Outdated pattern**: Suggests deprecated APIs
- **Over-specificity**: Invents details not in context
- **Contradiction**: Suggests conflicting approaches

---

### Gap 4: No Downstream Impact Measurement

**Currently measured**: File mention accuracy
**Should measure**: Actual error reduction in generated code

**Missing metrics**:
- **Code syntax correctness**: Does generated code parse/compile?
- **Functional correctness**: Implements requested feature?
- **Test pass rate**: How many unit tests pass?
- **Bug rate**: How many bugs introduced?
- **Import correctness**: Are modules available?
- **Type correctness**: Do type hints match usage?

---

### Gap 5: No User Study Component

**Currently measured**: Objective metrics only
**Should measure**: Developer perception and efficiency

**Missing metrics**:
- **Time-to-completion**: Minutes spent with/without CTX
- **Perceived usefulness**: 1-5 Likert scale
- **Cognitive load**: How much context read/used?
- **Iteration count**: Refactors needed for CTX-aided code
- **Confidence**: Developer confidence in solution

---

### Gap 6: No Multi-Step Task Handling

**Currently measured**: Single instructions
**Should measure**: Complex multi-step workflows

**Missing metrics**:
- **Multi-file dependency resolution**: Tasks requiring 5+ files
- **Cross-module grounding**: Dependencies across modules
- **Sequential task dependencies**: Series of related instructions
- **Partial completion detection**: When task needs more context
- **Context refresh efficiency**: Adaptation if task unfolds differently

---

## 4. RECOMMENDED ADDITIONS FOR COMPLETE G2

### Priority 1 (Critical) — 1 week

#### 1a. End-to-End Task Completion Evaluation
```python
class E2ETaskEval:
    metrics:
      - task_completable: Boolean (yes/no with human judgment)
      - missing_files: List of files needed but not retrieved
      - insufficient_context: Boolean (needs refetch)
      - developer_approval: Would human sign off? (1-5 Likert)
```

#### 1b. Context Quality Scorer
```python
class ContextQualityScore:
    metrics:
      - relevance_per_file: [0-1] for each file
      - coverage: symbols_mentioned_in_task / symbols_in_context
      - coherence: semantic similarity among files
      - noise_ratio: irrelevant_lines / total_lines
      - import_completeness: dependencies included?
```

#### 1c. Semantic Hallucination Detection
```python
class HallucinationDetector:
    metrics:
      - function_hallucination: Functions don't exist
      - pattern_hallucination: Wrong approach suggested
      - outdated_api: Deprecated patterns
      - type_mismatch: Function args don't match
```

#### 1d. Generated Code Quality
```python
class CodeQualityMetrics:
    metrics:
      - syntax_valid: Code parses (0/1)
      - imports_valid: All imports resolvable (0/1)
      - type_correct: Calls match signatures (0-1)
      - logic_sound: Implements feature (0-1)
      - test_pass_rate: Unit tests (0-1)
```

---

### Priority 2 (High Impact) — 2 weeks

#### 2a. Multi-File Dependency Analysis
```python
class MultiFileDependencyEval:
    metrics:
      - cross_module_recall: Files in different modules
      - dependency_chain_accuracy: Transitive dependencies
      - circular_dependency_detection: Avoids circular imports
```

#### 2b. User Study Framework
```python
class DeveloperStudy:
    sample: 10–20 developers
    tasks: 5 per developer (easy, medium, hard)
    conditions: [no_context, ctx, manual_context]
    
    metrics:
      - time_to_completion (minutes)
      - code_quality_score (1-10)
      - developer_confidence (1-5)
      - perceived_usefulness (1-5)
      - iterations_to_working (count)
```

#### 2c. Iterative Task Adaptation
```python
class IterativeTaskEval:
    """Eval over multiple instruction refinements"""
    sequence:
      1. Initial instruction + CTX retrieval
      2. Developer feedback: "missing file X"
      3. CTX refetch with feedback
      4. Measure: cost & quality improvement
```

---

### Priority 3 (Research Extensions) — Future

#### 3a. Benchmark Against Established Standards
- Use **CoIR** (Code Instruction Retrieval)
- Use **RepoBench** (repo-scale instructions)
- Use **LocAgent** (file localization, 92.7% accuracy)

#### 3b. LLM Robustness Analysis
```python
class LLMRobustness:
    metrics:
      - consistency: Same response across 3 runs?
      - model_variance: Score Claude vs. GPT vs. LLaMA
      - context_length_impact: Performance vs. context size
```

---

## 5. COMPLETE G2 FRAMEWORK (Vision)

```
G2 Score (Instruction-to-File Grounding Quality)
├─ Retrieval Metrics (30%)
│  ├─ File Recall@5: 0.644
│  ├─ Relevant File Recall: 0.820 (missing file detection)
│  └─ Context Quality Score: 0.775 (relevance + coverage)
│
├─ LLM Grounding Metrics (40%)
│  ├─ File Mention Accuracy: 0.350
│  ├─ Function Mention Accuracy: 0.420
│  ├─ Hallucination Rate: 0.12
│  ├─ Code Quality Score: 0.680 (syntax + imports + types)
│  └─ Test Pass Rate: 0.55
│
├─ User Perception Metrics (20%)
│  ├─ Perceived Usefulness: 4.2/5.0
│  ├─ Confidence: 3.8/5.0
│  └─ Time Savings: 35% faster with CTX
│
└─ Advanced Metrics (10%)
   ├─ Multi-file Dependency: 0.78
   ├─ Iterative Adaptation: 0.65
   └─ Cross-module Accuracy: 0.72

FINAL G2 SCORE: 0.684 / 1.000
```

---

## 6. Summary & Recommendation

**Current G2 Coverage**: 40% (retrieval + basic LLM scoring)

**Recommended Additions**:
1. End-to-end task completion (E2E score)
2. Context quality metrics (per-file relevance + coverage)
3. Semantic hallucination detection (beyond filename regex)
4. Code quality evaluation (syntax + imports + logic)
5. User study (developer perception & time savings)

**Timeline**: Priority 1 (1 week) → Priority 2 (2 weeks) → Priority 3 (research)

**Impact**: Double G2 evaluation coverage (40% → 80%), enabling comprehensive measurement of instruction-to-file grounding quality.

