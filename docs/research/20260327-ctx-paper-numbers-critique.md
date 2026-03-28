# [expert-research-v2] CTX Key Paper Numbers 비판적 평론
**Date**: 2026-03-27  **Skill**: expert-research-v2

## Original Question
CTX Key Paper Numbers (Cross-session R@10=0.579, TEMPORAL=0.600, RepoBench NDCG@5=0.723, TES=0.776, CosQA=0.1223, DRR@3=1.000, latency=117ms)의 학술적 가치, 취약점, 실제 의미 평론

## Web Facts
[FACT-1] CoIR CosQA NDCG@10: BGE-Base 32.76, E5-base 32.59, Contriever 14.21, Voyage-Code-002 29.79. BM25 미보고. (source: arxiv 2407.02883, ACL 2025)
[FACT-2] CTX TF-IDF CosQA NDCG@10 = 12.23 (×100 scale) — Contriever(14.21)보다 낮음
[FACT-3] RepoBench-R 공식 메트릭 = Acc@k (Exact Match). NDCG는 공식 메트릭 아님
[FACT-4] CoIR SOTA mean NDCG@10 = 52.86 (Voyage-Code-002). ACL 2025 Main
[FACT-5] RANGER 0.5471은 CTX 자체 보고 수치. 공개 리더보드 독립 검증 불가

## 수치별 위험도 평가

| 수치 | 위험도 | 핵심 공격 벡터 |
|------|--------|--------------|
| RepoBench NDCG@5 vs RANGER | **HIGH** | 메트릭 불일치 + 독립 검증 불가 |
| DRR@3 = 1.000 | **HIGH** | N=3, 통계적 무의미 |
| TEMPORAL R@10 (N=70) | **HIGH** | 통계적 검정 불가 |
| TES = 0.776 | MEDIUM | 자체 정의 메트릭, 비교 기준 없음 |
| CosQA NDCG@10 = 12.23 | MEDIUM | SOTA 대비 37% |
| Cross-session R@10 = 0.579 | MEDIUM | Baseline 없음 |
| Hook latency = 117ms | LOW | 분포 없음 |

## Final Conclusion
(Phase 3 output 참조)

## Sources
- [CoIR ACL 2025](https://arxiv.org/abs/2407.02883)
- [RepoBench ICLR 2024](https://github.com/Leolty/repobench)
- [CoIR GitHub](https://github.com/CoIR-team/coir)
