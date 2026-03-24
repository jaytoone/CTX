# CTX — Context-Triggered eXperimentation
## 상세 실험 스펙 문서 v1.0

> **실험 핵심 명제**: LLM이 방대한 데이터 풀에서 "트리거 입력"에 따라 관련 컨텍스트만 동적으로 호출함으로써, 전체 컨텍스트를 비효율적으로 보유하는 것보다 높은 정확도와 효율을 달성할 수 있는가?

---

## 1. 실험 배경 및 동기

### 1.1 인간 뇌의 연상 기억 모델

인간의 뇌는 모든 기억을 항상 활성화된 상태로 보유하지 않는다. 평소에는 유휴 상태로 기억을 보관하다가, 특정 **트리거(자극)**가 입력될 때 관련 기억이 강하게 활성화되는 **연상 기억(Associative Memory)** 패턴을 사용한다.

```
트리거 입력 → 관련 기억 활성화 → 필요한 것만 작업 메모리에 로드 → 처리 → 유휴 상태 복귀
```

이는 에너지 효율과 처리 속도 두 가지를 동시에 최적화한다.

### 1.2 현재 LLM의 컨텍스트 문제

**확인된 문제점 (연구 기반)**:

| 문제 | 출처 | 핵심 수치 |
|------|------|-----------|
| Lost in the Middle | Shi et al., ACL 2024 | 중간 위치 정보 정확도 급락 (U자형 성능 곡선) |
| Context Rot | Chroma Study 2025 | 18개 모델 전체에서 32K+ 시 성능 저하 확인 |
| 컨텍스트 길이의 역설 | Oct 2025 연구 | 100% 완벽한 검색에도 컨텍스트 길이만으로 13.9-85% 성능 저하 |
| 코드베이스 극단 | LongCodeBench 2025 | Claude 3.5: 32K에서 29% → 256K에서 3% 정확도 |

**근본 원인**: Attention 메커니즘이 전체 컨텍스트에 걸쳐 희석되어, 긴 컨텍스트에서 관련 정보를 선택적으로 처리하지 못함.

### 1.3 이론적 근거

**Hopfield Network ↔ Transformer 등가성 (수학적 증명)**:
- Self-attention 메커니즘은 수학적으로 현대 Hopfield 네트워크의 업데이트 룰과 동일
- 현대 Hopfield 네트워크는 **지수적으로 많은 패턴**을 저장하고 **O(1) 패턴 완성** 가능
- 즉, Transformer 기반 LLM은 이론적으로 희소/연상 검색을 구현할 수 있는 구조를 이미 내포

**연관 논문**: Hopfield-Fenchel-Young Networks (2024), ARMT (2024)

---

## 2. 실험 목표

### 2.1 Primary Objectives

1. **정확도 측정**: 방대한 프로젝트 파일에서 트리거 기반 검색이 관련 내용을 얼마나 정확하게 찾아내는가
2. **효율 측정**: 전체 컨텍스트 로딩 대비 트리거 선택 시 토큰 사용량 감소율
3. **마이너 데이터 탐색**: 희귀/마이너 데이터에 대한 LLM 접근 능력의 한계 탐색

### 2.2 Secondary Objectives

4. **포지션 독립성**: 트리거 기반 검색이 Lost-in-the-Middle 문제를 완화하는가
5. **히스토리 재현**: 과거 지시/결정 사항을 트리거로 정확하게 재현 가능한가
6. **실패 모드 분류**: 어떤 조건에서 트리거가 실패하는가 (False Negative 유형)

---

## 3. 실험 설계

### 3.1 실험 구조 개요

```
[ 데이터 레이어 ]
  ├── 대형 코드베이스 (>100K lines, 다수 파일)
  ├── 마이너 데이터 (희귀 엔티티, 낮은 빈도 참조)
  └── 히스토리 데이터 (과거 지시, 결정 사항, 대화 로그)

[ 트리거 레이어 ]
  ├── 명시적 트리거 (함수명, 변수명, 파일명)
  ├── 의미적 트리거 (개념, 패턴, 의도)
  └── 암시적 트리거 (컨텍스트 추론 기반)

[ 검색 레이어 ]
  ├── Full Context (베이스라인): 전체 로드
  ├── Sparse Trigger: 트리거 매칭 파일만 로드
  └── Hierarchical: Working → Episodic → Semantic 계층 검색

[ 평가 레이어 ]
  ├── 정확도 (Trigger Recall / Precision)
  ├── 효율 (토큰 비율, 레이턴시)
  └── 품질 (Task Completion Rate)
```

### 3.2 데이터셋 구성

#### A. 대규모 코드베이스 데이터셋

| 구분 | 크기 | 파일 수 | 특성 |
|------|------|---------|------|
| 소규모 | ~10K lines | ~50 files | 실험 검증용 |
| 중규모 | ~100K lines | ~500 files | 핵심 실험 |
| 대규모 | ~1M+ lines | ~5000+ files | 극한 스트레스 테스트 |

각 데이터셋은 다음을 포함:
- **Head 데이터**: 자주 참조되는 핵심 모듈 (상위 20% 파일이 80% 참조)
- **Torso 데이터**: 보통 빈도의 유틸리티, 헬퍼 모듈
- **Tail 데이터**: 희귀하게 사용되는 레거시, 특수 케이스 파일

#### B. 히스토리/지시 데이터셋

```
history/
├── instructions/       # 과거 사용자 지시 사항 (날짜별)
├── decisions/          # 기술 결정 기록
├── conversations/      # 대화 히스토리 요약
└── annotations/        # Ground Truth 레이블 (어떤 파일이 관련인지)
```

#### C. 마이너 데이터 카테고리

- **Level 1 (쉬운 마이너)**: 파일 1-5개에만 존재하는 함수/변수
- **Level 2 (중간 마이너)**: 특정 도메인 지식 요구 (예: 레거시 프로토콜)
- **Level 3 (극단 마이너)**: 주석이나 문서에만 언급된 히든 로직

### 3.3 트리거 유형 정의

```python
class TriggerType(Enum):
    EXPLICIT_SYMBOL   = "explicit_symbol"    # 정확한 함수명/변수명
    SEMANTIC_CONCEPT  = "semantic_concept"   # "인증 관련 코드"
    TEMPORAL_HISTORY  = "temporal_history"   # "지난번에 논의한 방식"
    IMPLICIT_CONTEXT  = "implicit_context"   # 현재 작업 컨텍스트에서 추론
    CROSS_MODULE_DEP  = "cross_module_dep"   # "이 함수를 호출하는 곳 모두"
```

### 3.4 검색 전략 비교

#### Strategy 1: Full Context (베이스라인)
```
전체 코드베이스 → LLM 컨텍스트에 전부 로드 → 답변
토큰 비용: MAX
정확도 기대: 기준값 (그러나 Lost-in-the-Middle으로 인해 실제로는 저하)
```

#### Strategy 2: BM25 Sparse Retrieval
```
쿼리 → BM25 키워드 매칭 → Top-K 파일 로드 → 답변
토큰 비용: ~15-30% of Full
정확도 기대: 명시적 키워드에 강함, 의미 검색에 약함
```

#### Strategy 3: Dense Vector Retrieval (RAG)
```
쿼리 → 임베딩 → 유사도 검색 → Top-K 청크 로드 → 답변
토큰 비용: ~10-20% of Full
정확도 기대: 의미 검색에 강함, 정확한 심볼 매칭에 약함
```

#### Strategy 4: Adaptive Trigger Retrieval (핵심 실험)
```
쿼리 분석 → 트리거 타입 분류 → 계층적 메모리 탐색:
  L1: 작업 메모리 (현재 세션 컨텍스트)
  L2: 에피소딕 메모리 (히스토리, 결정 사항)
  L3: 의미 메모리 (코드베이스 지식 그래프)
→ 동적 k 조정 (CAR 방식) → 답변
토큰 비용: ~5-20% of Full (동적 조정)
정확도 기대: 가설: Full Context 이상 (포지션 독립성 확보)
```

#### Strategy 5: Hybrid (BM25 + Dense + Trigger)
```
복합 전략으로 위 방법들의 앙상블
```

---

## 4. 평가 지표 (Metrics)

### 4.1 Primary Metrics

```python
# 1. Trigger Recall @ K
# Ground Truth 관련 파일 중 Top-K에 포함된 비율
def trigger_recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    return len(set(retrieved[:k]) & set(relevant)) / len(relevant)

# 2. Token Efficiency Ratio
# 사용한 토큰 / 전체 코드베이스 토큰
def token_efficiency(tokens_used: int, total_tokens: int) -> float:
    return tokens_used / total_tokens

# 3. Trade-off Efficiency Score (TES) — CAR 논문 방식
# 정확도 / ln(1 + 로드한 파일 수)
def tes(accuracy: float, files_loaded: int) -> float:
    import math
    return accuracy / math.log(1 + files_loaded)

# 4. Accuracy Preservation Rate
# 트리거 전략 정확도 / Full Context 정확도
def accuracy_preservation(trigger_acc: float, full_acc: float) -> float:
    return trigger_acc / full_acc
```

### 4.2 Secondary Metrics

| 지표 | 설명 | 목표 임계값 |
|------|------|------------|
| Hallucination Rate | 없는 내용 생성 비율 | < 5% |
| Position Independence | 위치별 성능 분산 | ±10% 이내 |
| Latency Reduction | 응답 시간 감소 | > 30% |
| False Negative Rate | 관련 파일 누락 비율 | < 15% |
| Minor Data Recall | Tail 데이터 검색 성공률 | > 50% |

### 4.3 Degradation Curve 측정

```
컨텍스트 크기별 정확도 측정:
  [10K, 32K, 64K, 128K, 256K, 512K, 1M] tokens
  × [Head, Torso, Tail] 데이터 등급
  × [Full, Trigger, Hybrid] 전략
  = 3차원 성능 매트릭스
```

---

## 5. 구현 아키텍처

### 5.1 시스템 컴포넌트

```
CTX/
├── src/
│   ├── indexer/
│   │   ├── code_indexer.py       # 코드베이스 인덱싱 (파일 → 임베딩)
│   │   ├── symbol_extractor.py   # AST 기반 심볼 추출
│   │   └── graph_builder.py      # 의존성 그래프 생성
│   ├── memory/
│   │   ├── working_memory.py     # 현재 세션 작업 메모리
│   │   ├── episodic_memory.py    # 히스토리/결정 사항 저장
│   │   └── semantic_memory.py    # 코드 지식 그래프 (장기)
│   ├── trigger/
│   │   ├── trigger_classifier.py # 트리거 타입 분류
│   │   ├── trigger_executor.py   # 트리거 기반 검색 실행
│   │   └── adaptive_k.py         # 동적 k 조정 (CAR 방식)
│   ├── retrieval/
│   │   ├── bm25_retriever.py     # 키워드 기반
│   │   ├── dense_retriever.py    # 벡터 기반 (FAISS)
│   │   └── hybrid_retriever.py   # 앙상블
│   └── evaluator/
│       ├── benchmark_runner.py   # 자동 평가 실행
│       ├── metrics.py            # 지표 계산
│       └── report_generator.py   # 결과 리포트
├── benchmarks/
│   ├── datasets/                 # 평가 데이터셋
│   ├── ground_truth/             # 정답 레이블
│   └── results/                  # 실험 결과
└── docs/
    └── CTX_SPEC_v1.0.md          # 이 문서
```

### 5.2 계층적 메모리 구조

```python
class HierarchicalMemory:
    """
    인간 뇌의 3계층 메모리 구조를 모방한 LLM 메모리 시스템

    L1 Working Memory  : 현재 세션 컨텍스트 (4K-8K tokens)
    L2 Episodic Memory : 과거 지시/결정/대화 (히스토리 DB)
    L3 Semantic Memory : 코드베이스 지식 그래프 (구조화된 영구 저장)
    """

    def retrieve(self, trigger: str, trigger_type: TriggerType) -> RetrievalResult:
        # Step 1: L1 Working Memory 먼저 확인 (가장 빠름)
        result = self.working_memory.search(trigger)
        if result.confidence > 0.9:
            return result

        # Step 2: L2 Episodic Memory 확인
        episodic = self.episodic_memory.search(trigger, trigger_type)
        if episodic.confidence > 0.7:
            result.merge(episodic)
            return result

        # Step 3: L3 Semantic Memory (전체 코드 그래프) 탐색
        semantic = self.semantic_memory.search(trigger, trigger_type)
        result.merge(semantic)

        # 동적 k 조정: 신뢰도에 따라 로드량 결정
        k = self.adaptive_k.compute(
            query=trigger,
            candidates=result.candidates,
            target_efficiency=0.15  # 전체의 15% 이하 목표
        )

        return result.top_k(k)
```

### 5.3 트리거 분류기

```python
class TriggerClassifier:
    """
    입력 프롬프트에서 트리거를 자동 추출하고 분류
    """

    def classify(self, prompt: str, session_context: dict) -> List[Trigger]:
        triggers = []

        # 1. 명시적 심볼 추출 (AST-level)
        symbols = self._extract_symbols(prompt)  # 함수명, 클래스명, 변수명

        # 2. 의미적 개념 추출 (NLP)
        concepts = self._extract_concepts(prompt)  # "인증", "데이터베이스 연결"

        # 3. 시간적 참조 감지 ("지난번", "이전에", "remember")
        temporal = self._detect_temporal_refs(prompt)

        # 4. 암시적 컨텍스트 추론
        implicit = self._infer_from_context(prompt, session_context)

        return self._deduplicate_and_rank(symbols + concepts + temporal + implicit)
```

---

## 6. 실험 단계별 로드맵

### Phase 1: 기반 구축 (Week 1-2)

- [ ] 코드베이스 인덱싱 파이프라인 구축
- [ ] 평가 데이터셋 생성 (소규모부터)
- [ ] Ground Truth 레이블 작성 프로세스 정의
- [ ] Full Context 베이스라인 측정

### Phase 2: 트리거 시스템 구현 (Week 3-4)

- [ ] 트리거 분류기 구현
- [ ] 계층적 메모리 구조 구현
- [ ] BM25 / Dense Retrieval 통합
- [ ] 초기 Trigger Recall 측정

### Phase 3: 적응형 검색 최적화 (Week 5-6)

- [ ] 동적 k 조정 알고리즘 (CAR 방식)
- [ ] Hybrid Retrieval 앙상블
- [ ] 마이너 데이터(Tail) 특화 전략
- [ ] 히스토리 검색 (Episodic Memory)

### Phase 4: 벤치마크 평가 (Week 7-8)

- [ ] 전체 지표 측정 자동화
- [ ] 3차원 성능 매트릭스 생성
- [ ] Degradation Curve 분석
- [ ] 실패 모드 분류 및 분석

### Phase 5: 분석 및 문서화 (Week 9-10)

- [ ] 결과 분석 및 해석
- [ ] 가설 검증/반증
- [ ] 최종 보고서 작성
- [ ] 후속 연구 방향 제안

---

## 7. 가설 및 예상 결과

### 7.1 핵심 가설

| 가설 | 검증 방법 | 성공 기준 |
|------|-----------|-----------|
| H1: 트리거 전략이 Full Context보다 효율적 | Token Efficiency Ratio | < 20% 토큰으로 > 80% 정확도 유지 |
| H2: 포지션 독립성 확보 | 위치별 성능 분산 | Full Context 대비 편차 50% 감소 |
| H3: 마이너 데이터 할루시네이션 감소 | Hallucination Rate | Tail 데이터에서 < 30% (현재 60-78%) |
| H4: 히스토리 트리거 정확도 | Temporal Recall | > 70% at K=5 |

### 7.2 예상 한계점

1. **암시적 의존성 실패**: 직접 참조되지 않는 간접 의존성 파일 누락
2. **Cross-module 트리거**: 모듈 간 경계에 걸친 컨텍스트 추론 어려움
3. **동의어/리팩토링**: 동일 개념이 다른 이름으로 구현된 경우
4. **극단 Tail 데이터**: 전체에서 1회만 등장하는 심볼 (메모리에 약한 흔적만 남음)

---

## 8. 비교 연구 포지셔닝

### 8.1 기존 연구와의 차별점

| 기존 연구 | 한계 | CTX 실험의 기여 |
|-----------|------|-----------------|
| Head-to-Tail (NAACL 2024) | 일반 지식 QA 중심 | **코드베이스 특화** 트리거 패턴 분석 |
| LongCodeBench (2025) | 단순 Accuracy 측정 | **트리거 vs. 토큰 Pareto Frontier** 분석 |
| CAR 논문 (2024) | 단일 쿼리 최적화 | **히스토리/에피소딕 트리거** 통합 |
| MemGPT (2023) | OS 비유의 일반 시스템 | **코드 심볼 그래프** 기반 트리거 특화 |

### 8.2 CTX만의 고유 기여

1. **코드베이스 트리거 분류 체계** (명시적/의미적/시간적/암시적)
2. **마이너 데이터 계층별 Degradation 프로파일** (Head/Torso/Tail × 전략)
3. **히스토리 재현 정확도 벤치마크** (에이전트의 "기억" 능력 정량화)
4. **Trigger Efficiency Frontier**: 토큰 비용 대비 정확도의 Pareto 곡선

---

## 9. 기술 스택

```yaml
Language: Python 3.11+
LLM:
  - Claude claude-sonnet-4-6 (주 실험)
  - GPT-4o (비교군)
  - Llama 3 70B (오픈소스 기준)

Indexing:
  - FAISS (Dense Vector)
  - BM25s (Sparse Keyword)
  - Tree-sitter (AST 파싱)

Memory:
  - SQLite (Episodic Memory)
  - NetworkX (Semantic Graph)
  - Redis (Working Memory Cache)

Evaluation:
  - Custom Benchmark Runner
  - LangSmith (트레이싱)
  - Weights & Biases (실험 추적)
```

---

## 10. 참고 문헌

### 핵심 논문

1. **[Lost in the Middle]** Shi et al. — *How Language Models Use Long Contexts* (ACL 2024)
2. **[Long-Tail Knowledge]** — *Long-Tail Knowledge in Large Language Models: Taxonomy, Mechanisms, Interventions* (arXiv 2025)
3. **[Head-to-Tail]** — *How Knowledgeable are Large Language Models?* (NAACL 2024)
4. **[Hopfield-Fenchel-Young]** — *Unified Framework for Associative Memory* (2024)
5. **[MemGPT]** Linn et al. — *Towards LLMs as Operating Systems* (2023)
6. **[CAR]** — *Cluster-based Adaptive Retrieval: Dynamic Context Selection* (2024)
7. **[ARMT]** Rodkin et al. — *Associative Recurrent Memory Transformer* (2024)
8. **[LongCodeBench]** — *Evaluating Coding LLMs at 1M Context Windows* (2025)
9. **[StreamingLLM]** — *Efficient Streaming Language Models with Attention Sinks* (ICLR 2024)
10. **[Context Length Alone Hurts]** — *Oct 2025, even with perfect retrieval* (2025)

### 벤치마크

- RULER: Position-dependent Long Context Evaluation (NVIDIA)
- HELMET: Comprehensive Long Context Benchmark
- LongBench v2: Multi-domain Long Context Tasks
- Sequential-NIAH: Multiple Needles in Long Contexts

---

*문서 버전: v1.0 | 작성일: 2026-03-23 | 프로젝트: CTX*
