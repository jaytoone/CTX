# CTX — Document Index

| 파일 | 설명 |
|------|------|
| [CTX_SPEC_v1.0.md](CTX_SPEC_v1.0.md) | 실험 상세 스펙 문서 v1.0 — 트리거 기반 동적 메모리 호출 실험 설계 |
| [research/20260324-ctx-paper-worthiness.md](research/20260324-ctx-paper-worthiness.md) | CTX 논문 가치 평론 — expert-research-v2 결과 |
| [../benchmarks/results/final_report.md](../benchmarks/results/final_report.md) | P0 최종 실험 결과 리포트 — Synthetic + Real(GraphPrompt) + CCS/ASS |
| [../benchmarks/results/final_report_v2.md](../benchmarks/results/final_report_v2.md) | P1 최종 통합 리포트 — 5전략 비교 + GraphRAG-lite + Differentiation |
| [../benchmarks/results/final_report_v3.md](../benchmarks/results/final_report_v3.md) | P1.6 최종 통합 리포트 — 7전략 비교 (LlamaIndex + Chroma Dense 추가) |
| [../benchmarks/results/differentiation_analysis.md](../benchmarks/results/differentiation_analysis.md) | CTX vs Memori 차별화 정량 분석 — 코드 구조 활용도 + 트리거별 강점 |
| [paper_draft_outline.md](paper_draft_outline.md) | arXiv 논문 초안 구조 — 섹션별 핵심 포인트 + 실험 결과 요약 |
| [paper/CTX_paper_draft.md](paper/CTX_paper_draft.md) | arXiv 제출용 논문 초안 — 전체 본문 (Abstract~References) |
| [../benchmarks/results/llm_quality_results.json](../benchmarks/results/llm_quality_results.json) | LLM pass@1 실험 결과 JSON — MiniMax M2.5, Full Context vs Adaptive Trigger |
| [../benchmarks/results/llm_quality_report.md](../benchmarks/results/llm_quality_report.md) | LLM pass@1 실험 리포트 — per-sample 결과 + 컨텍스트 토큰 비교 |
| [research/20260324-ctx-methodology-critique-top-tier.md](research/20260324-ctx-methodology-critique-top-tier.md) | 상위 티어 논문 기준 실험 방식 평론 — expert-research-v2, 제출 로드맵 포함 |
| [../benchmarks/results/final_report_v4.md](../benchmarks/results/final_report_v4.md) | P2.4 최종 통합 리포트 — 3 real codebases + 통계 검증 + Ablation + Error Analysis |
| [../benchmarks/results/ablation_results.md](../benchmarks/results/ablation_results.md) | Ablation Study 결과 — 4 variants x 4 datasets |
| [../benchmarks/results/error_analysis.md](../benchmarks/results/error_analysis.md) | Error Analysis — 실패 패턴 분류 및 전략 간 비교 |
| [../benchmarks/results/final_report_v5.md](../benchmarks/results/final_report_v5.md) | P3 최종 통합 리포트 — COIR 외부 벤치마크 + pass@1 n=49 확장 + 95% CI |
| [../benchmarks/results/coir_evaluation.json](../benchmarks/results/coir_evaluation.json) | COIR-CodeSearchNet 평가 결과 JSON — 100 queries, 1000 corpus |
| [../benchmarks/results/coir_evaluation.md](../benchmarks/results/coir_evaluation.md) | COIR-CodeSearchNet 평가 리포트 — BM25/TF-IDF/Dense/CTX 비교 |
| [../benchmarks/results/llm_quality_results_v2.json](../benchmarks/results/llm_quality_results_v2.json) | LLM pass@1 v2 결과 JSON — n=49, McNemar test, 95% CI |
| [../benchmarks/results/llm_quality_report_v2.md](../benchmarks/results/llm_quality_report_v2.md) | LLM pass@1 v2 리포트 — 49 samples, 통계 검증 포함 |
| [../benchmarks/results/ndcg_tes_correlation.json](../benchmarks/results/ndcg_tes_correlation.json) | NDCG@5-TES 상관관계 분석 결과 JSON — 28 strategy-dataset pairs, Pearson r=0.87 |
| [../benchmarks/results/hybrid_evaluation.md](../benchmarks/results/hybrid_evaluation.md) | Hybrid Dense+CTX 평가 리포트 — COIR R@5=0.950, IMPLICIT_CONTEXT 분석 |
| [../benchmarks/results/final_report_v6.md](../benchmarks/results/final_report_v6.md) | P4 최종 통합 리포트 — 8전략 비교 (Hybrid Dense+CTX 추가) |
| [paper/CTX_paper.tex](paper/CTX_paper.tex) | ACL/EMNLP LaTeX 논문 — CTX_paper_draft.md의 LaTeX 변환본 |
| [paper/references.bib](paper/references.bib) | BibTeX 참고문헌 — 12개 참고문헌 |
| [research/20260325-ctx-paper-tier-evaluation.md](research/20260325-ctx-paper-tier-evaluation.md) | CTX 논문 학술 티어 평가 — expert-research-v2, 베뉴별 전망 + 개선 로드맵 |
| [../benchmarks/results/trigger_accuracy.md](../benchmarks/results/trigger_accuracy.md) | Trigger 분류기 정확도 분석 — 60.2% accuracy, confusion matrix, SEMANTIC F1=0.15 |
| [../benchmarks/results/external_codebase_eval.md](../benchmarks/results/external_codebase_eval.md) | 외부 코드베이스 평가 (Flask/Requests/FastAPI) — 3개 공개 프로젝트 일반화 실험 |

## Related
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
- [[projects/CTX/research/20260324-ctx-paper-worthiness|20260324-ctx-paper-worthiness]]
- [[projects/CTX/research/20260324-ctx-methodology-critique-top-tier|20260324-ctx-methodology-critique-top-tier]]
