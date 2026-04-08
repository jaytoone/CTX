# [expert-research-v2] G1 Long-Term Memory Evaluation Framework
**Date**: 2026-04-08  **Skill**: expert-research-v2  **Type**: Methodology Research

---

## Original Question

G1 재정의: "시간에 대한 장기 기억 보장 능력 및 중요 판단 히스토리 복원/유지 능력" 평가 방법론.

기존 CTX의 keyword recall 방식을 넘어, git history, documentation, accumulated decisions를 기반으로 장기 기억 능력을 정확히 측정할 수 있는 SOTA 평가 프레임워크 설계.

---

## Web Facts

**[FACT-1] LongMemEval (ICLR 2025)**
- 5가지 핵심 능력 평가: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention
- 500개 질문, 115K~1.5M 토큰 시뮬레이션
- 상용 시스템 30% 정확도 하락 발견
- 3단계 framework: Indexing → Retrieval → Reading
- 최적화: session decomposition, fact-augmented key expansion, time-aware query expansion
- Source: [LongMemEval arXiv](https://arxiv.org/abs/2410.10813)

**[FACT-2] LoCoMo — Very Long-Term Conversational Memory**
- 300턴, 9K 토큰, 최대 35세션에 걸친 장기 대화 평가
- 3가지 태스크:
  - (1) QA with 5 reasoning types: single-hop, multi-hop, temporal, commonsense, adversarial
  - (2) Event Graph Summarization (causal/temporal understanding)
  - (3) Multimodal Dialog
- RAG 기법 22-66% 향상하지만 여전히 인간 대비 56% 낮음
- **특히 temporal reasoning에서 약함**
- Source: [LoCoMo](https://snap-research.github.io/locomo/)

**[FACT-3] GitGoodBench — Git History Understanding**
- Git 히스토리 이해 평가
- Interactive Rebase에서 commit dependencies와 git history 추론 요구
- LLM-as-Judge로 4가지 차원 평가:
  - Commit message quality
  - Logical cohesion within commits
  - Logical progression across commits
  - Commit granularity
- Source: [GitGoodBench arXiv](https://arxiv.org/html/2505.22583v1)

**[FACT-4] Memory Evaluation 3-Dimensional Framework**
- Effectiveness (accuracy)
- Efficiency (메모리 연산 수)
- Capacity (메모리 크기 증가에 따른 성능 저하)
- 질문을 5가지 reasoning types로 분류하여 다각도 평가
- Source: [Memory for LLM Agents](https://arxiv.org/html/2603.07670v1)

**[FACT-5] Temporal Context Model (TCM)**
- 시간적 맥락 표현 메커니즘
- Contextual drift → recency effects
- Contextual retrieval → contiguity effects
- 인지과학 기반 모델
- Source: [TCM PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC2585999/)

**[FACT-6] Context Recall Metric**
- Formula: (Ground Truth Claims Attributable to Retrieved Context) / (Total Claims in Ground Truth)
- 검색 완전성 측정
- Source: [DeepEval Context Recall](https://deepeval.com/docs/metrics-contextual-recall)

**[FACT-7] Memory System Architecture**
- LTM (long-term memory): 지속적 지식 저장
- STM (short-term memory): 현재 입력 컨텍스트
- High-quality LTM → efficient retrieval of accumulated knowledge
- Source: [Agentic Memory](https://arxiv.org/html/2601.01885v1)

**[FACT-8] Mem0 Benchmark Results**
- LOCOMO에서 OpenAI memory 대비 26% 상대 향상 (66.9% vs 52.9%)
- Factual accuracy와 coherence에서 우수
- Source: [Mem0 Research](https://mem0.ai/research)

**[FACT-9] SWE-bench — Real-World Software Engineering**
- 실제 GitHub 이슈 해결 벤치마크
- Git 히스토리를 이슈 생성 날짜 이후로 제거하여 미래 솔루션 접근 방지
- Real-world software engineering context 제공
- Source: [SWE-bench GitHub](https://github.com/swe-bench/SWE-bench)

---

## Multi-Lens Analysis

### LENS 1: Domain Expert Analysis

#### Insight 1: 단순 Keyword Recall은 G1의 본질을 측정하지 못한다

**[GROUNDED]** — LongMemEval은 "information extraction" 외에 temporal reasoning, knowledge updates, multi-session reasoning을 별도 차원으로 분리. LoCoMo에서도 RAG가 22-66% 향상을 주지만 "temporal reasoning에서 특히 약함"이 별도로 명시.

**Reasoning**: CTX의 현재 G1 eval은 "keyword가 context에 있는가"를 측정. 그러나 G1 재정의 — "중요 판단 히스토리 복원/유지" — 는 세 가지 능력을 포함:
- (a) 과거 결정 사실 회상
- (b) 그 결정의 시간적 순서 이해
- (c) 결정의 인과 관계 재구성

Keyword recall은 (a)의 하위 지표일 뿐.

**Counterargument**: Keyword recall이 단순해 보여도 precision이 높으면 downstream task에서 충분할 수 있다. CTX의 현재 G1 delta(+0.300 vs None, +0.112 vs Random)가 실용적 가치를 이미 입증.

---

#### Insight 2: Git History는 G1 평가의 고품질 Ground Truth Source다

**[GROUNDED]** — GitGoodBench는 git 히스토리 이해를 4개 차원으로 평가. SWE-bench는 git 히스토리를 이슈 생성 시점으로 truncate하여 미래 정보 누출을 방지.

**Reasoning**: CTX의 G1은 `git log`에서 의사결정을 추출. 이는 곧 git history가 G1의 자연스러운 ground truth임을 의미.

**평가 설계**:
1. 실제 프로젝트 git log에서 중요 결정 commit 선별
2. "왜 이 결정을 했는가"를 묻는 질문 생성
3. CTX가 해당 결정 + 이유를 올바르게 반환하는지 측정
4. SWE-bench의 temporal isolation 기법으로 데이터 오염 방지

**Counterargument**: Git commit message 품질은 프로젝트마다 편차가 크다. "fix bug" 같은 저품질 메시지에서는 의사결정 ground truth를 추출하기 어렵다.

---

#### Insight 3: 시간 축 평가는 "Age-based Decay"와 "Recency Bias" 두 방향 모두를 측정해야 한다

**[GROUNDED]** — TCM은 contextual drift가 recency effect를 만들고 contiguity effect가 연속 기억 회상을 강화함을 보임. LoCoMo에서 시스템이 최신 세션 정보를 오래된 정보보다 더 잘 회상하는 temporal bias가 관찰.

**Reasoning**: G1 temporal retention 평가는 두 가지 직교적 실패 모드를 구분해야 함:
- **Decay failure**: 오래된 결정이 잊힌다 (age가 증가할수록 recall 감소)
- **Recency bias failure**: 최신 결정이 오래된 결정을 override (conflicting decisions에서 잘못된 것 선택)

**평가 지표**: recall@K by commit_age_bucket (0-7d, 7-30d, 30-90d, 90d+)

**Counterargument**: Age-based decay가 CTX에서 바람직한 특성인지 자체가 불명확. 3년 전 아키텍처 결정이 어제 버그픽스보다 더 중요할 수 있다.

---

#### Insight 4: 다차원 평가 프레임워크는 Effectiveness × Efficiency × Capacity를 분리해야 한다

**[GROUNDED]** — FACT-4의 3차원 프레임워크. LongMemEval에서 115K-1.5M 토큰 규모 변화에 따른 성능 변화를 측정하여 capacity 차원을 실증.

**CTX G1 적용**:
- **Effectiveness**: P@K, R@K on decision recall queries
- **Efficiency**: git log 파싱 latency, inject_decisions.py 실행 시간
- **Capacity**: git history depth 증가(100 → 1000 → 10000 commits)에 따른 recall 성능 저하 곡선

현재 CTX는 efficiency가 매우 우수하지만 capacity에서 어떻게 되는지 측정된 바가 없다.

**Counterargument**: CTX가 git log를 모두 inject하는 것이 아니라 recent N개만 사용한다면 capacity 문제는 설계 선택으로 회피된다.

---

#### Insight 5: LLM-as-Judge가 아닌 Deterministic + LLM-Hybrid 방식이 더 신뢰할 수 있다

**[GROUNDED]** — GitGoodBench는 LLM-as-Judge 사용하나 bias 문제 인정. CTX 프로젝트 MEMORY.md에 "MiniMax M2.5 judge가 {0, 5, 10}만 출력 → hybrid scoring으로 해결" 실제 경험 기록. FACT-6의 Context Recall은 deterministic formula.

**Reasoning**: G1 평가에서 순수 LLM judge는 두 가지 문제:
- (a) judge의 편향이 평가 결과에 섞인다
- (b) 재현성이 낮다

**권장 설계**: deterministic skeleton (commit hash 포함 여부, timestamp 순서 정확도 등) + LLM judge for semantic equivalence of decision rationale.

**Hybrid score = 0.5 × deterministic + 0.5 × LLM-semantic** (CTX가 이미 G1 eval에 사용한 방식과 일치)

**Counterargument**: Deterministic 지표만으로는 "왜 그 결정을 했는가"의 이유 품질을 측정할 수 없다.

---

### LENS 2: Devil's Advocate (Self-Critique)

#### [OVERCONFIDENT] Insight 2: Git History = High Quality Ground Truth

Git commit message 품질 편차 문제가 단순 counterargument로 처리됐지만 실제로는 더 심각. CTX 프로젝트는 잘 작성된 편이나, 일반 프로젝트에서는 50% 이상 commit이 "fix", "update", "wip" 수준.

**[UNCERTAIN]** — 실제 프로젝트 git log에서 meaningful decision ground truth를 자동 추출하는 방법이 확립되지 않았다.

---

#### [MISSING] Multi-hop Temporal Reasoning

Insight 1-5 모두 single-hop recall(하나의 결정을 찾는 것)에 집중. LoCoMo와 LongMemEval은 모두 multi-hop reasoning을 핵심 난이도 요소로 꼽음.

**G1에서 multi-hop 예시**:
```
"BM25로 전환한 이유"
  → "TF-IDF 약점"
    → "소규모 코퍼스에서 IDF 역효과"
```

이 chain을 CTX가 복원할 수 있는지 측정하는 항목이 없다.

---

#### [MISSING] Knowledge Update / Contradiction 처리

LongMemEval의 "knowledge updates" 능력이 완전히 누락. G1의 실제 어려운 케이스:

같은 주제에 대해 상충하는 결정이 존재할 때 (예: "외부 코드베이스 R@5 개선 방향을 BM25로 했다가 tree-sitter로 바꿨다") — CTX가 최신 결정을 올바르게 선택하는가.

---

#### [CONFLICT] Insight 3의 Age-based Decay 방향성

FACT-5(TCM)은 인간 episodic memory 모델인데, Insight 3에서 이를 LLM memory evaluation에 직접 적용.

**[CONFLICT]** — LLM은 recency bias와 decay를 인간과 다른 메커니즘으로 처리. TCM의 "contiguity effect"는 vector DB 기반 retrieval에는 적용되나 git log 순차 파싱에는 다르게 작동.

---

#### [OVERCONFIDENT] Insight 4: Capacity 미측정이 "가장 큰 리스크"

CTX가 git log에서 최근 N개만 사용하는 설계라면 capacity는 실제로 문제가 아닐 수 있다. 더 큰 리스크는 측정됐지만 잘못 측정되고 있는 것(G1 recall 100% at --rich mode가 synthetic으로만 측정됨).

---

### LENS 3: Practical Synthesizer — CTX G1 Evaluation Framework

#### 1. Query Type Taxonomy (Confirmed from FACT-1, FACT-2)

G1 evaluation query를 4개 타입으로 분류:

| Type | 예시 | 난이도 | 측정 능력 |
|------|------|--------|----------|
| **Single-hop fact** | "BM25로 전환한 시점은?" | LOW | Information extraction |
| **Rationale recall** | "BM25로 전환한 이유는?" | MEDIUM | Decision reasoning |
| **Multi-hop chain** | "외부 코드베이스 R@5가 낮은 이유와 그에 대응한 결정은?" | HIGH | Causal reasoning |
| **Conflict resolution** | "X에 대해 가장 최근의 결정은?" (중간에 방향 변경 있음) | HIGH | Knowledge update |

**현재 CTX G1 eval은 사실상 Type 1만 측정. Type 3, 4가 실제 사용 가치와 더 직결.**

---

#### 2. Ground Truth 구축 방법 (Revised from Insight 2)

자동 git log parsing으로 ground truth를 완전히 뽑는 것은 [UNCERTAIN].

**권장 방식: semi-automated**
- CTX 프로젝트처럼 잘 작성된 commit log → 자동 추출
- 그렇지 않은 경우 → human annotation 레이어 추가
- SWE-bench 방식으로 evaluation time cutoff 설정하여 데이터 오염 방지

**구체적 구축 절차**:
1. git log에서 "결정 커밋" 자동 식별 (feat:/fix:/v-version 패턴 — CTX git-memory.py가 이미 구현)
2. 각 결정에 대해 QA pair 생성: (질문, 정답 commit hash, 정답 rationale text)
3. QA pair를 Type 1-4로 분류 (LLM-assisted classification)
4. Temporal cutoff: 평가 시점 기준 T일 전 이후 커밋 제거 (SWE-bench 방식)

---

#### 3. 측정 지표 (Confirmed: FACT-4 framework + FACT-6 formula)

| 지표 | 계산 | 대응 능력 | 신뢰도 |
|------|------|-----------|--------|
| **Decision Recall@K** | (GT decisions in CTX output) / (total GT decisions) | Fact recall | HIGH |
| **Rationale F1** | 0.5 × keyword overlap + 0.5 × LLM semantic score | Reason retention | MEDIUM |
| **Temporal Order Accuracy** | 순서가 있는 결정 쌍에서 CTX가 올바른 순서를 반환하는 비율 | Temporal reasoning | HIGH |
| **Conflict Resolution Accuracy** | 상충 결정 중 최신 것을 선택하는 정확도 | Knowledge update | HIGH |
| **Recall by Age Bucket** | 0-7d / 7-30d / 30-90d / 90d+ 별 recall | Decay curve | MEDIUM |

**Hybrid scoring**: 재현성(deterministic) + 의미 품질(LLM) 균형

---

#### 4. Capacity 평가 (Revised from Insight 4)

CTX가 "최근 N commits만 inject"하는 설계라면 capacity test 대신 **N sensitivity analysis**가 더 실용적:
- N=50 vs 100 vs 200에서 recall 변화 측정
- 만약 CTX가 전체 log를 inject한다면 commit depth 1K/5K/10K test 필요

---

#### 5. Baseline 비교 (from FACT-8)

| Baseline | 이유 | 기대 성능 |
|----------|------|-----------|
| **No CTX** | Lower bound | ~0% |
| **Full git log dump** | CTX 필터링 가치 측정 | Recall 높으나 noise 심함 |
| **Mem0 / LoCoMo RAG** | SOTA 시스템 대비 포지셔닝 | 66.9% (LOCOMO 기준) |

---

## Final Conclusion: Actionable G1 Evaluation Framework

### Core Design Principles

1. **Multi-dimensional evaluation** — Not just "does CTX have the answer" but "can CTX reason about temporal relationships and resolve conflicts"
2. **Git-native ground truth** — Leverage CTX's existing git log foundation, supplement with semi-automated QA pair generation
3. **Hybrid scoring** — Balance deterministic reproducibility (0.5 weight) with semantic quality assessment (0.5 LLM judge)
4. **4-tier query taxonomy** — Single-hop → Rationale → Multi-hop → Conflict resolution
5. **Temporal isolation** — SWE-bench style cutoff to prevent future information leakage

### Implementation Roadmap

**Phase 1: Ground Truth Construction**
- Extract decision commits from CTX git log (existing git-memory.py pattern)
- Generate QA pairs for each decision (Types 1-4)
- Manual review of 30-50 pairs for quality baseline

**Phase 2: Metric Implementation**
- Decision Recall@K (deterministic)
- Rationale F1 (hybrid: keyword + LLM)
- Temporal Order Accuracy (deterministic on timestamp pairs)
- Conflict Resolution (LLM judge on conflicting decision pairs)
- Age-bucket Recall (0-7d, 7-30d, 30-90d, 90d+)

**Phase 3: Baseline Comparison**
- No CTX
- Full git log dump (no filtering)
- Current CTX variants (g1_raw, g1_filtered, random_noise)
- SOTA if available (Mem0 integration or LoCoMo-style RAG)

### Expected Outcomes

- **Validation** of CTX's current G1 delta (+0.300) on more robust tasks (multi-hop, conflict)
- **Discovery** of CTX's capacity limits (how deep in git history can it effectively recall?)
- **Comparison** against SOTA memory systems (position CTX relative to Mem0's 66.9% on LOCOMO)

### Remaining Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Low-quality git commits in target repos | HIGH | Semi-automated annotation, start with CTX repo only |
| LLM judge bias/variance | MEDIUM | Hybrid scoring (0.5 deterministic anchor) |
| SOTA baselines not directly comparable | MEDIUM | Document comparison limitations clearly |
| Multi-hop chain extraction complexity | HIGH | Start with Type 1-2, expand to Type 3-4 iteratively |

---

## Confidence: MEDIUM (65%)

Framework design is well-grounded in FACT-1 through FACT-9. However, actual implementation feasibility (especially multi-hop extraction and SOTA baseline integration) remains [UNCERTAIN] until tested.

---

## Remaining Uncertainties

1. **[UNCERTAIN]** "결정 커밋" 자동 식별의 recall/precision — CTX의 `feat:/fix:/v-version` 패턴이 의미있는 결정 커밋을 얼마나 커버하는가
2. **[UNCERTAIN]** Multi-hop decision chain retrieval — CTX git-memory.py가 현재 이를 지원하는지, 또는 단순 sequential inject인지 코드 확인 필요
3. **[UNCERTAIN]** Conflict resolution (knowledge update) 성능 — CTX가 같은 주제의 상충 결정이 있을 때 어떻게 동작하는지 실험된 바 없음
4. **[UNCERTAIN]** "90d+ 이상 오래된 결정"의 recall 실측치 — age-based decay curve가 구현됐지만 결과가 충분히 공유되지 않음

---

## Sources

1. [LongMemEval (ICLR 2025)](https://arxiv.org/abs/2410.10813) — 5차원 평가, query taxonomy 설계 근거
2. [LoCoMo](https://snap-research.github.io/locomo/) — multi-hop + temporal reasoning의 난이도 근거, RAG 한계 수치
3. [GitGoodBench](https://arxiv.org/html/2505.22583v1) — git history를 LLM evaluation ground truth로 쓰는 선례
4. [Memory 3-Dimensional Framework](https://arxiv.org/html/2603.07670v1) — Effectiveness/Efficiency/Capacity 분리 근거
5. [Temporal Context Model (TCM)](https://pmc.ncbi.nlm.nih.gov/articles/PMC2585999/) — temporal decay/recency bias 이론적 배경
6. [Context Recall Metric (DeepEval)](https://deepeval.com/docs/metrics-contextual-recall) — Decision Recall@K 계산식 직접 차용
7. [Mem0 Research](https://mem0.ai/research) — LOCOMO 66.9% 벤치마크, SOTA baseline 수치
8. [Agentic Memory (LTM/STM)](https://arxiv.org/html/2601.01885v1) — Memory architecture taxonomy
9. [SWE-bench](https://github.com/swe-bench/SWE-bench) — temporal cutoff로 데이터 오염 방지 설계 방법

---

## Related Research

- [[20260407-g1-final-eval-benchmark]] — 기존 CTX G1 eval (NoiseRatio, TopicCoverage, DA@7)
- [[20260408-g1-temporal-retention-eval]] — Age-based recall decay curve 구현
- [[20260408-g1-format-ablation-results]] — Format ablation downstream δ 실험
- [[20260328-ctx-downstream-eval-complete]] — G1+G2 synthetic eval (MiniMax M2.5)
