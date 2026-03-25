# [expert-research-v2] CTX 논문 학술 티어 평가
**Date**: 2026-03-25  **Skill**: expert-research-v2

## Original Question
CTX 논문 (Trigger-Driven Dynamic Context Loading for Code-Aware LLM Agents) 의 현재 학술적 티어 평가.
1) ACL/EMNLP/ICLR/NeurIPS/ICSE/FSE/ASE 2024-2025 수준과 비교
2) 실험 설계 강점/약점
3) 현실적인 accept 가능 베뉴 예측
4) 티어 상승을 위해 필요한 보완사항

## Web Facts
[FACT-1] RANGER (arXiv:2509.25257, Sep 2025): graph-based repo retrieval, 4 standard benchmarks (CodeSearchNet/RepoQA/RepoBench/CrossCodeEval), KG with variable-level granularity (source: arxiv.org/abs/2509.25257)
[FACT-2] KG-based Repo Code Gen (arXiv:2505.14394, May 2025): KG capturing class/function/module hierarchies + dependencies (source: arxiv.org/abs/2505.14394)
[FACT-3] RACG Survey (arXiv:2510.04905, Oct 2025): strong papers must "capture long-range dependencies, ensure global semantic consistency, multi-file coherence" (source: arxiv.org/abs/2510.04905)
[FACT-4] ASE 2024: DroidCoder (RAG code completion) accepted; ICSE 2025: SpecRover (LLM code intent extraction) accepted
[FACT-5] NeurIPS 2025: HyperGraphRAG accepted (graph-structured RAG)
[FACT-6] EMNLP 2025: Hierarchical Document Refinement for Long-context RAG accepted
[FACT-7] Standard CodeSearchNet corpus = 500K+ documents (CTX used 1K subset)
[FACT-8] ICLR 2025 acceptance rate ~32%, requires foundational contribution with large-scale eval

## Multi-Lens Analysis

### Domain Expert (Lens 1)
- Trigger taxonomy: incremental conceptualization, IMPLICIT_CONTEXT category most original [REASONED]
- BFS import graph: simplified vs RANGER's full KG; sound but dense prior art [GROUNDED]
- TES metric: most genuinely novel contribution; axiomatic grounding needed [REASONED]
- Hybrid Dense+CTX: standard two-stage pattern, routing layer is differentiator [GROUNDED]
- Evaluation: 50-file synthetic + own 3 projects + 1K COIR = structural mismatch with 2025 standards [GROUNDED]

### Self-Critique (Lens 2)
1. [OVERCONFIDENT] Self-generated benchmark → circular validation, Recall@5=1.0 claim unverifiable externally
2. [MISSING] 1K COIR subset vs 500K standard → toy evaluation, desk-rejection trigger
3. [MISSING] Trigger classification accuracy/confusion matrix never reported
4. [OVERCONFIDENT] pass@1 n=49 on MiniMax M2.5 → non-reproducible, under-powered
5. [MISSING] No comparison to RANGER, KG-based code gen (2025 SOTA)

### Synthesis (Lens 3)
Current tier: Workshop / arXiv preprint
Achievable tier: EMNLP/ACL Findings, ASE main (6-12 months)

## Final Conclusion

| 베뉴 | 전망 |
|------|------|
| ACL/EMNLP main | Reject |
| ICLR/NeurIPS | Reject |
| ICSE/FSE | Reject |
| ASE main | Borderline |
| EMNLP/ACL Findings | 보완 후 가능 |
| Workshop (CodeNLP/BigCode) | Accept 유력 |

### Top 5 개선 우선순위
1. [Critical] 표준 벤치마크: RepoBench, CrossCodeEval, full CodeSearchNet(500K)
2. [High] 외부 독립 코드베이스: CPython, Django, PyTorch 등
3. [High] Trigger 분류 정확도 + confusion matrix ablation
4. [Medium] pass@1 → DeepSeek-Coder/StarCoder2 + n≥200
5. [Medium] TES 메트릭 형식화 (공리적 속성 + 기존 메트릭 비교)

**Confidence: HIGH** — 평가 방법론 격차는 판단이 아닌 수치의 문제.

## Sources
- [RANGER](https://arxiv.org/abs/2509.25257)
- [RACG Survey](https://arxiv.org/abs/2510.04905)
- [KG-based Repo Code Gen](https://arxiv.org/abs/2505.14394)
- [EMNLP 2025 CFP](https://www.aclweb.org/portal/content/emnlp-2025-first-call-papers)
- [NeurIPS 2025 HyperGraphRAG](https://github.com/LHRLAB/HyperGraphRAG)

## Related
- [[projects/CTX/research/20260324-ctx-methodology-critique-top-tier|20260324-ctx-methodology-critique-top-tier]]
