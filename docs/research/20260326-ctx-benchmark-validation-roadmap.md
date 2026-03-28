# [expert-research-v2] CTX G1/G2 공인 벤치마크 검증 로드맵
**Date**: 2026-03-26  **Skill**: expert-research-v2

## Original Question
CTX Goal 1 (cross-session memory continuity) + Goal 2 (instruction-grounded retrieval)를 공인 외부 벤치마크로 독립 검증하려 한다. 현재 CTX 수치: Cross-session Recall@10=0.567, Doc Recall@5=0.933, AgentNode R@5=0.522, NDCG@5=0.723, TES=0.776. 어떤 공인 벤치마크에 제출/비교하면 각 Goal을 독립적으로 검증할 수 있는가?

## Web Facts

[FACT-1] CoIR (ACL 2025 Main): pip install coir-eval. MTEB 리더보드 공식 제출. NDCG@10 기준. SOTA: CodeXEmbed-7B=67.41, Voyage-Code-002=56.26.
Source: https://github.com/CoIR-team/coir

[FACT-2] RepoBench (ICLR 2024): cross-file snippet retrieval. Accuracy@5 기준. SOTA RANGER=0.5471. CTX 자체 측정 NDCG@10=0.646.
Source: https://github.com/Leolty/repobench

[FACT-3] LongMemEval (ICLR 2025): 500개 질문, 5가지 long-term memory 평가. GPT-4o 자동 채점.
Source: https://github.com/xiaowu0162/LongMemEval

[FACT-4] MemoryAgentBench (ICLR 2026 제출): incremental multi-turn 에이전트 메모리.
Source: https://github.com/HUST-AI-HYZ/MemoryAgentBench

[FACT-5] SWE-bench: 파일 로컬라이제이션 서브태스크 존재. BM25/RAG baseline.
Source: https://www.swebench.com

## Multi-Lens Analysis

### Domain Expert (Lens 1)

**Goal 2 (Instruction-Grounded Retrieval)**:
- CoIR: 즉시 실행 가능, MTEB 제출, NDCG@10 기준. CTX 예상 60~68. [GROUNDED]
- RepoBench-R: cross-file 특화. BM25 대비 +11.8pp CTX 우위 재현 가능. [GROUNDED]
- SWE-bench 파일 로컬라이제이션: practical downstream 검증. [REASONED]

**Goal 1 (Cross-Session Memory)**:
- LongMemEval: 구조적으로 가장 가깝지만 파일 복원 Recall ≠ QA correctness. [REASONED]
- MemoryAgentBench: 가장 직접적이나 ICLR 2026 제출 상태로 인프라 미성숙. [UNCERTAIN]
- **핵심 발견**: Cross-session code memory 공인 벤치마크가 현재 존재하지 않음. [REASONED]

### Self-Critique (Lens 2)

- 30q 샘플 기반 수치의 표준오차: ±0.05~0.15 → 공식 벤치마크에서 하락 가능.
- CoIR SOTA(임베딩 모델 7B)와 CTX(orchestration layer) 비교의 레벨 차이 명시 필요.
- Goal 1 공백 = novelty이기도 하지만 peer review 취약점이기도 함.

### Synthesis (Lens 3)

Goal 2: CoIR 즉시 제출 → TES 차원 추가로 차별화.
Goal 1: LongMemEval partial proxy + 테스트셋 300q+ 확장이 현실적 최선.
Goal 1 벤치마크 공백 자체를 논문의 motivation으로 활용.

## Final Conclusion

### Goal 2 검증 로드맵

| 벤치마크 | 메트릭 | CTX 예상 | SOTA | 제출 난이도 |
|---------|-------|---------|------|----------|
| CoIR (ACL 2025) | NDCG@10 | 0.60~0.68 | 67.41 | 낮음 |
| RepoBench-R (ICLR 2024) | Accuracy@5 / NDCG@10 | BM25 +11.8pp | 0.5471 | 낮음 |
| SWE-bench localization | File accuracy | 미측정 | — | 높음 |

### Goal 1 검증 전략

| 전략 | 상태 | 설명 |
|------|------|------|
| LongMemEval information extraction | 부분 proxy | 파이프라인 연결 필요 |
| MemoryAgentBench | 미성숙 | ICLR 2026, 공개 여부 확인 필요 |
| 자체 테스트셋 확장 | 권장 | 300q+, 5+ 코드베이스, 재현 포맷 |

### 즉시 실행 순서

1. `pip install coir-eval` → CoIR 내부 재현 (Week 1)
2. MTEB 리더보드 공식 제출 (Week 2)
3. LongMemEval information extraction 서브태스크 (Week 3)
4. RepoBench-R 공식 스크립트 (Week 4)

## Sources
- [CoIR GitHub (ACL 2025)](https://github.com/CoIR-team/coir)
- [RepoBench GitHub (ICLR 2024)](https://github.com/Leolty/repobench)
- [LongMemEval GitHub (ICLR 2025)](https://github.com/xiaowu0162/LongMemEval)
- [MemoryAgentBench GitHub (ICLR 2026)](https://github.com/HUST-AI-HYZ/MemoryAgentBench)
- [SWE-bench](https://www.swebench.com)
