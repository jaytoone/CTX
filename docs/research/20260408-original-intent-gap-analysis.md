# G1/G2 실험 — 원래 의도 정합성 분석
**Date**: 2026-04-08  **Type**: Gap analysis + SOTA positioning

---

## 원래 의도 재확인

**1차 목적**: LLM에게 컨텍스트를 계속 넣어보면서 *어떤 방식의 기억이 가장 장기기억에 도움이 되는지를 평가하는 방법론* 연구
**2차 목적**: 그 평가 방식에 의거한 실험 실행

---

## 방금 수행한 실험의 정합성 평가

### 수행한 것
- G1 noise filter + topic-dedup 구현 (`~/.claude/hooks/git-memory.py`)
- NoiseRatio@7: 50%→0%, TopicCoverage: 73%→79%, IP@7: 0.0→0.5

### 정합성 판정: **Step 1 (전제 조건 품질 작업) — 필요하지만 불충분**

```
원래 의도
  ├── [Step 1] 주입 품질 확보 (noise 제거, topic coverage 향상) ← 방금 완료 ✓
  ├── [Step 2] 방식 비교 (git-log vs structured summary vs Graph vs vector) ← 미수행 ✗
  └── [Step 3] Downstream LLM 태스크 성능 δ 측정 ← 미수행 ✗ (원래 의도의 핵심)
```

방금 수행한 것은 "git-log 기반 G1 메커니즘 최적화"이지,
원래 의도인 **"어떤 방식이 LLM 장기기억에 가장 도움이 되는가?"** 비교 실험이 아님.

---

## 현재 측정 지표의 한계

| 지표 | 측정하는 것 | 원래 의도 커버 | 문제 |
|------|------------|--------------|------|
| NoiseRatio@7 | 주입 집합 내 noise 비율 | 간접적 | downstream task와 연결 없음 |
| TopicCoverage@7 | 주제 다양성 | 간접적 | "다양하면 도움" 가정이 검증 안 됨 |
| IP@7 | 최신 이터레이션 주입 여부 | 간접적 | 최신이 항상 더 유용하다는 가정 |
| DA@7 | 파일 활성도 proxy | 간접적 | 활성 파일 ≠ LLM에게 유용 |
| **Downstream LLM δ** | **실제 태스크 성능 변화** | **직접적 (핵심)** | **미구축** |

이 proxy 지표들은 "주입 집합의 품질"을 측정하지,
"LLM이 이 주입으로 실제로 더 잘 수행하는가"를 측정하지 않는다.

---

## SOTA 갭 분석 (2026-04-08 조사 기준)

### 존재하는 벤치마크

| 벤치마크 | 무엇을 측정 | CTX 관련성 | 커버 여부 |
|---------|-----------|-----------|---------|
| LongMemEval (ICLR 2025, arXiv:2410.10813) | 챗봇 5가지 장기기억 능력 | G1 temporal reasoning과 관련 | Chat-domain only, coding 없음 |
| MemoryAgentBench (ICLR 2026, arXiv:2507.05257) | 4가지 메모리 역량 (retrieval, learning, understanding, conflict) | G1/G2 역량과 겹침 | 주입 포맷 변수로 통제 ✗ |
| COIR (ACL 2025) | 코드 검색 R@k | G2 직접 관련 | G1 의사결정 기억 ✗ |
| SWE-Bench-Lite | 버그 수정 성공률 | Downstream oracle로 사용 가능 | 포맷 비교 설계 없음 |
| A-MEM (arXiv:2502.12110) | Zettelkasten 구조화 메모리 vs MemGPT 비교 | 포맷 ablation 방법론 | Chat QA domain only |

### 존재하지 않는 것 (Gap)

**"동일 검색 결과, 다른 포맷으로 주입 → LLM 코딩 태스크 성능 비교"** 를 측정하는 표준 벤치마크는 2026년 4월 기준 존재하지 않음.

### 최신 SOTA 방향 (2025-2026)

| 논문 | 핵심 아이디어 | CTX와의 관계 |
|------|------------|------------|
| ByteRover (arXiv:2604.01599, Apr 2026) | LLM 자체가 메모리를 curate → 의도-저장 간 semantic drift 해소 | G1의 git-log 자동 추출 vs. LLM-curated 비교 필요 |
| Meta-Harness (arXiv:2603.28052) | harness 코드(저장·검색·제시 전략) end-to-end 최적화 | CTX가 harness 최적화 그 자체 — 직접 포지셔닝 가능 |
| EXPEREPAIR (2025, SWE-Bench) | episodic + semantic 듀얼 메모리 → SWE-Bench-Lite 성능 측정 | G1+G2의 downstream 측정 설계 선례 |
| JetBrains Context Mgmt (NeurIPS 2025) | 에이전트 컨텍스트가 빠르게 커져도 downstream 성능 개선 미미 | CTX의 selective injection 접근 방식 검증 |

---

## 원래 의도에 부합하는 실험 설계 (미수행)

### 필요한 실험: Format Ablation Study

**설계 원칙** (A-MEM 방법론 차용): 검색 결과는 동일하게 고정, 주입 포맷만 변경

```
동일 쿼리 → 동일 검색 결과 (ground-truth files)
         ↓
  Format A: raw file content (현재 G2)
  Format B: function signatures only
  Format C: git-log decision summary (현재 G1)
  Format D: structured entity graph (GraphRAG/ByteRover style)
  Format E: G1 + G2 hybrid (CTX 현재 전략)
         ↓
  SWE-Bench-Lite 50-100 instances 실행
         ↓
  bug fix success rate per format → δ측정
```

### 달성 가능한 빠른 버전 (현재 CTX 인프라로)

기존 `benchmarks/eval/downstream_llm_eval.py` (실제 MiniMax M2.5 eval 기존 존재) 확장:

```python
# Format variants for same retrieved context:
FORMATS = {
    "raw_git_log": g1_decisions,           # 현재 G1 (방금 최적화)
    "no_context": [],                       # baseline
    "random_files": random_sample(files),  # random baseline
    "g2_files_only": g2_file_content,      # G2 only
    "g1_g2_hybrid": g1_decisions + g2_files  # CTX current
}
# 각 format으로 동일 coding task → LLM 정답률 비교
# 기존 benchmarks/eval/real_codebase_downstream_eval.py 참조
```

이미 `G2 real codebase eval (δ+0.200)` 측정 인프라가 있음 → G1 format 비교만 추가하면 됨.

---

## 결론

### Q: 방금 수행한 실험이 원래 의도에 부합하는가?

**A: 부분 적합 (Step 1 완료, Step 2-3 미완).**

- G1 noise filter + topic-dedup은 **올바른 첫 번째 단계** — 품질 기준선 확립
- 하지만 원래 질문 ("어떤 방식이 LLM 장기기억에 가장 도움?")에 답하려면:
  - 포맷 비교 실험 (Step 2) 이 필요
  - Downstream LLM task δ 측정 (Step 3) 이 필요
  - 현재는 proxy metrics만 존재 (NoiseRatio, TopicCoverage)

### Q: 대체할 SOTA 방식이 있는가?

**A: 없음 — 이 평가 카테고리 자체가 논문 기여 가능 공백.**

"Cross-session coding decision memory + format comparison + downstream delta"를 모두 다루는 표준 벤치마크는 존재하지 않음.
ByteRover(2604.01599)와 Meta-Harness(2603.28052)가 가장 근접하지만 format ablation 없음.

### Q: 다음 단계는?

**우선순위:**
1. **Downstream δ 측정 먼저** — 기존 `downstream_llm_eval.py` 확장, G1 format ablation 5종 비교 (1-2일)
2. **MemoryAgentBench positioning** — CTX의 G1을 MemoryAgentBench 4 competencies에 매핑 (연구 포지셔닝)
3. **ByteRover 비교 실험** — LLM-curated vs git-log-based memory 비교 (중기)

---

## 참고 문헌

- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — format ablation methodology template
- [MemoryAgentBench (ICLR 2026)](https://arxiv.org/abs/2507.05257) — 가장 최신 agent memory benchmark
- [ByteRover: Agent-Native Memory](https://arxiv.org/html/2604.01599) — LLM-curated hierarchical context (April 2026 SOTA)
- [Meta-Harness](https://arxiv.org/html/2603.28052v1) — end-to-end harness optimization (CTX의 직접 포지셔닝 대상)
- [LongMemEval (ICLR 2025)](https://github.com/xiaowu0162/LongMemEval) — 5-ability chat memory benchmark

---

## 관련 파일
- `benchmarks/eval/downstream_llm_eval.py` — G1+G2 downstream eval (MiniMax M2.5)
- `benchmarks/eval/real_codebase_downstream_eval.py` — real codebase G2 eval
- `docs/research/20260407-g1-final-eval-benchmark.md` — G1 proxy metrics baseline
- `docs/research/20260328-ctx-downstream-eval-complete.md` — 기존 downstream eval 결과
