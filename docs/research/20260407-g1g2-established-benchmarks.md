# [expert-research-v2] G1/G2 공인 벤치마크 존재 여부
**Date**: 2026-04-07  **Skill**: expert-research-v2

## Original Question
G1 (cross-session decision memory)과 G2 (codebase file retrieval)의 성능을 평가할 수 있는
공인 벤치마크가 존재하는가? CTX 시스템과 연결 가능한 벤치마크 조사.

## Web Facts

[FACT-1] **LongMemEval** (NeurIPS 2024, arxiv 2410.10813): 채팅 어시스턴트의 장기 기억을
5가지 차원(정보 추출, multi-session 추론, temporal reasoning, 지식 업데이트, abstention)으로 평가.
명시적 multi-session 설계 포함. (source: arxiv.org/abs/2410.10813)

[FACT-2] **COIR** (ACL 2025, arxiv 2407.02883): 코드 정보 검색을 파일/함수/심볼 수준에서
평가하는 종합 벤치마크. 시맨틱 코드 매칭 포함. CTX가 이미 이 벤치마크에서
COIR R@5=1.000 달성 (NL-code task). (source: arxiv.org/abs/2407.02883)

[FACT-3] **Agentless** (arxiv 2407.01489): SWE-bench에서 파일 지역화(file localization)
정밀도/재현율 측정. Nemotron-CORTEXA 기준 +18.08% precision, +11.32% recall 개선.
파일 수준 R@k의 사실상 기준점. (source: arxiv.org/abs/2407.01489)

[FACT-4] **EpBench** (2025): 에피소드 메모리 벤치마크 — 시간/공간/컨텍스트 이벤트의
인코딩·검색·추론 평가. 일반 에피소드 메모리, 코딩 특화 아님.
(source: emergentmind.com/topics/episodic-memory-benchmark-epbench)

[FACT-5] **EXPEREPAIR** (Mu et al., 2025): SWE-Bench Lite에서 듀얼 메모리(에피소드+시맨틱)
수리 에이전트 — 코딩 에이전트에서 에피소드 메모리가 성능에 기여함을 실증.

[FACT-6] **Agent Memory Benchmark (AMB)**: 에이전트 메모리/검색 평가 오픈 리더보드.
(source: agentmemorybenchmark.ai)

[FACT-7] RepoQA: 독립 벤치마크로 확인되지 않음 (검색 결과 없음).

## 핵심 발견

### G1 (Cross-Session Decision Memory) — 완전 일치 벤치마크 없음

| 벤치마크 | G1 커버리지 | 차이점 |
|---------|-----------|--------|
| LongMemEval | 부분 (multi-session, temporal) | 채팅 기억 ≠ 코딩 결정 기억 |
| EpBench | 부분 (에피소드 인코딩/검색) | 범용 에피소드, 코드 결정 특화 아님 |
| EXPEREPAIR | 간접 (SWE-bench + 메모리) | 버그 수정 컨텍스트, G1과 다름 |
| AMB | 가능성 있음 | 아직 성숙도 낮음 (오픈 리더보드) |

**결론**: "git log → 과거 코딩 결정 recall" 을 직접 평가하는 공인 벤치 없음.
G1은 **미개척 평가 카테고리** — 논문 contribution으로 직접 활용 가능.

### G2 (Codebase File Retrieval) — 공인 벤치 존재, 부분 연결 가능

| 벤치마크 | G2 커버리지 | CTX 현황 |
|---------|-----------|---------|
| COIR | 높음 (파일/함수 수준 코드 검색) | **이미 측정됨: R@5=1.000** |
| Agentless (SWE-bench) | 중간 (버그 수정용 파일 지역화) | 미측정 (버그 수정 컨텍스트 차이) |
| CodeSearchNet | 낮음 (함수 수준, 파일 아님) | 해당 없음 |

**결론**: G2는 COIR이 공인 비교 기준. CTX는 이미 COIR에서 R@5=1.000 달성.
SWE-bench 파일 지역화는 추가 검증 포인트가 될 수 있음.

## Final Conclusion

**G1**: 공인 벤치마크 없음 → 기회. LongMemEval을 선행 연구로 인용하고
"cross-session coding decision memory" eval을 CTX 논문의 새 기여로 제안 가능.

**G2**: COIR이 공인 기준 (ACL 2025). CTX R@5=1.000 달성 — 이미 연결됨.
추가로 Agentless 방식의 SWE-bench 파일 지역화 비교 권장.

## Sources
- [LongMemEval (NeurIPS 2024)](https://arxiv.org/abs/2410.10813)
- [COIR (ACL 2025)](https://arxiv.org/abs/2407.02883)
- [Agentless](https://arxiv.org/abs/2407.01489)
- [Agent Memory Benchmark](https://agentmemorybenchmark.ai/)
- [NVIDIA CORTEXA](https://research.nvidia.com/labs/adlr/cortexa/)
