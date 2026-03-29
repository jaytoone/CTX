# CTX — Document Index

| 파일 | 설명 |
|------|------|
| [CTX_SPEC_v1.0.md](CTX_SPEC_v1.0.md) | 실험 상세 스펙 문서 v1.0 — 트리거 기반 동적 메모리 호출 실험 설계 |
| [research/20260329-ctx-hook-improvement-report.md](research/20260329-ctx-hook-improvement-report.md) | CTX 훅 개선 세션 Before/After 성과 리포트 — FP 85.7%→0%, 전체 정확도 85%→100% |
| [research/20260324-ctx-paper-worthiness.md](research/20260324-ctx-paper-worthiness.md) | CTX 논문 가치 평론 — expert-research-v2 결과 |
| [../benchmarks/results/final_report.md](../benchmarks/results/final_report.md) | P0 최종 실험 결과 리포트 — Synthetic + Real(GraphPrompt) + CCS/ASS |
| [../benchmarks/results/final_report_v2.md](../benchmarks/results/final_report_v2.md) | P1 최종 통합 리포트 — 5전략 비교 + GraphRAG-lite + Differentiation |
| [../benchmarks/results/final_report_v3.md](../benchmarks/results/final_report_v3.md) | P1.6 최종 통합 리포트 — 7전략 비교 (LlamaIndex + Chroma Dense 추가) |
| [../benchmarks/results/differentiation_analysis.md](../benchmarks/results/differentiation_analysis.md) | CTX vs Memori 차별화 정량 분석 — 코드 구조 활용도 + 트리거별 강점 |
| [paper_draft_outline.md](paper_draft_outline.md) | arXiv 논문 초안 구조 — 섹션별 핵심 포인트 + 실험 결과 요약 |
| [paper/CTX_paper_draft.md](paper/CTX_paper_draft.md) | arXiv 제출용 논문 초안 v4.0 P11 — G2 v4 calibrated (+0.688), SOYA READY, BM25 비교 |
| [SOYA_DEPLOYMENT_GUIDE.md](SOYA_DEPLOYMENT_GUIDE.md) | CTX SOYA 배포 가이드 — 비기능 요건 검증(P99<3ms), 통합 패턴, 배포 체크리스트 |
| [research/generate_soya_validation_report.py](research/generate_soya_validation_report.py) | CTX SOYA 최종 검증 결과 DOCX 보고서 생성기 — G1/G2/지연시간/over-anchoring 테이블 |
| [../benchmarks/results/CTX_SOYA_VALIDATION_REPORT.docx](../benchmarks/results/CTX_SOYA_VALIDATION_REPORT.docx) | CTX v4.0 SOYA 배포 최종 검증 보고서 (DOCX) — 8개 섹션, 모든 기준 PASS |
| [../benchmarks/eval/claude_sonnet_ctx_eval.py](../benchmarks/eval/claude_sonnet_ctx_eval.py) | Claude Sonnet 4.6 G1/G2 v4 eval — claude CLI subprocess 기반 격리 평가 |
| [../benchmarks/eval/unified_g2v4_eval.py](../benchmarks/eval/unified_g2v4_eval.py) | G2 v4 통일 평가 스크립트 — MiniMax/Nemotron/Sonnet 동일 벤치마크로 cross-model 비교 (FAT-2 해결) |
| [../benchmarks/results/g2v4_unified_comparison.json](../benchmarks/results/g2v4_unified_comparison.json) | G2 v4 통일 비교 결과 — MiniMax(Δ=0.833)/Nemotron(Δ=1.000)/Sonnet(Δ=1.000), WITHOUT 전원=0.000 |
| [../benchmarks/results/ctx_vs_bm25_complete.json](../benchmarks/results/ctx_vs_bm25_complete.json) | CTX vs BM25 완전 비교 — 6개 실제 코드베이스 모두 CTX 승리 (내부 3개 BM25 추가 완성) |
| [research/20260329-ctx-corrected-results-summary.md](research/20260329-ctx-corrected-results-summary.md) | CTX 수정된 실험 결과 종합 — Table A(CTX vs BM25 7개), Table B(G2 v4 통일), 논문 수준 평가 |
| [../benchmarks/results/sonnet_ctx_g1g2_results.json](../benchmarks/results/sonnet_ctx_g1g2_results.json) | Claude Sonnet 4.6 G2 v4 self-eval 결과 — WITHOUT=0.000, WITH=1.000, Δ=+1.000 |
| [research/20260329-ctx-paper-gap-analysis.md](research/20260329-ctx-paper-gap-analysis.md) | CTX 논문 수준 갭 분석 — FAT/MAJ/MIN 갭 진단, 재포지셔닝 전략, Phase별 수정 계획 |
| [../benchmarks/eval/latency_profiler.py](../benchmarks/eval/latency_profiler.py) | CTX 지연시간 프로파일러 — P50/P95/P99 측정, SOYA P99<500ms 검증 |
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
| [../benchmarks/results/llm_quality_openrouter.md](../benchmarks/results/llm_quality_openrouter.md) | OpenRouter Gemini Flash 1.5 pass@1 — CTX 0.733 vs Full 0.200 (+267%, p=0.0004) |
| [claude_code_integration.md](claude_code_integration.md) | CTX → Claude Code Hook 통합 가이드 — UserPromptSubmit hook, 트리거별 전략, A/B 테스트 설계 |
| [../benchmarks/results/doc_retrieval_eval.md](../benchmarks/results/doc_retrieval_eval.md) | 문서 검색 평가 — CTX-doc Recall@3=0.600 vs Random 0.000, 10-query 수동 쿼리셋 |
| [../benchmarks/results/hook_effectiveness_eval.md](../benchmarks/results/hook_effectiveness_eval.md) | CTX Hook 실효성 평가 — 30 queries, CHR 70.0%, EXPLICIT_SYMBOL 86.7%/PASS, TEMPORAL 100%/PASS, 평균 RT 116.9ms |
| [research/20260325-long-session-context-management.md](research/20260325-long-session-context-management.md) | 장기 세션 컨텍스트 관리 리서치 — 7개 도구 비교 + 2024-2025 연구 + CTX Gap 분석 (P0: cross-session memory) |
| [research/20260326-ctx-achievement-review.md](research/20260326-ctx-achievement-review.md) | CTX 현재 성과 vs 사용자 요구 평론 — Goal 1: 30%, Goal 2: 60%, 측정 인프라: 90%, "방향 희석"은 mcp__memory__ 결정 맥락 복원이 실제 해법 |
| [../benchmarks/results/cross_session_recall.json](../benchmarks/results/cross_session_recall.json) | 크로스 세션 연속성 평가 — persistent memory 복원 Recall@10=0.917 (Goal 1: 세션 간 작업 히스토리 유지) |
| [../benchmarks/results/instruction_grounding_eval.json](../benchmarks/results/instruction_grounding_eval.json) | 지시→파일 grounding 평가 — IMPLICIT_CONTEXT 88.9%, 베이스라인 Recall@5=0.333 (Goal 2: 자연어 지시→유관 파일 찾기) |
| [research/20260326-ctx-vs-industry-comparison.md](research/20260326-ctx-vs-industry-comparison.md) | CTX vs Cursor/Copilot/Windsurf 비교 — Cross-session memory 3-tier, Instruction grounding CoIR/Voyage-Code, 외부 검증 포함 |
| [research/20260326-ctx-vs-sota-comparison.md](research/20260326-ctx-vs-sota-comparison.md) | CTX Goal 1&2 vs SOTA 성능 비교 — CoIR 미출시, MemoryArena (Feb 2026) 신규 벤치마크, Cursor/Copilot/Windsurf 공개 지표 없음 |
| [research/20260326-ctx-final-sota-comparison.md](research/20260326-ctx-final-sota-comparison.md) | CTX 최종 SOTA 성능 비교 테이블 — Goal 1(Recall@10=0.567), Goal 2(NDCG@5=0.723), TES=0.776(1.9x BM25), IMPLICIT_CONTEXT Recall@5=1.0 |
| [research/20260326-ctx-results-review.md](research/20260326-ctx-results-review.md) | CTX 성과 평론 — 합성/실제 붕괴 분석, ICSE/FSE 15-25%, MSR 45-60%, 3 Must-Fix 제시 |
| [../benchmarks/results/multi_dataset_cross_session_eval.md](../benchmarks/results/multi_dataset_cross_session_eval.md) | SG1: 4개 데이터셋 cross-session 평가 — small=0.567(PASS), AgentNode=0.361, GraphPrompt=0.472, OneViral=0.405, head recall mean=0.803 |
| [../benchmarks/results/coir_repobench_integrated.md](../benchmarks/results/coir_repobench_integrated.md) | SG2: COIR+RepoBench 통합 평가 — NDCG@10 추가, CTX vs BM25 p=0.0000 Cohen's d=0.955(large effect) |
| [../benchmarks/results/aggregated_stat_report.md](../benchmarks/results/aggregated_stat_report.md) | SG3: 22개 결과 파일 통합 통계 리포트 — Goal1 mean=0.544, Goal2 d=0.276, cross-dataset significance test |
| [../benchmarks/results/final_report_v7.md](../benchmarks/results/final_report_v7.md) | P5 최종 리포트 — 5x 성능 붕괴 완전 해결 (5.0x→1.84x), AgentNode R@5=0.522(목표 0.35 달성), 5개 RC 분석 + 코드 변경 기록 |
| [research/20260326-ctx-sota-final-v2.md](research/20260326-ctx-sota-final-v2.md) | CTX vs SOTA 최종 성능 비교 v2 — iter5 수치 반영, IDE 도구/검색모델/기준선 8개 시스템 비교, Goal 1&2 달성 현황 |
| [research/20260326-ctx-methodology-comparison.md](research/20260326-ctx-methodology-comparison.md) | CTX vs 연구 방법론 비교 — RANGER/GraphRAG/BM25/Dense/LlamaIndex/CodeXEmbed 정량 비교, IMPLICIT_CONTEXT +150-1275%, TES 1.89x BM25, 논문 포지셔닝 권고 |
| [../benchmarks/results/doc_retrieval_eval_v2.md](../benchmarks/results/doc_retrieval_eval_v2.md) | 문서 검색 평가 v2 — 20 docs, 60 쿼리, CTX-doc R@5=0.933(1위), BM25=0.833, Dense=0.900, heading_paraphrase R@3=1.000 (3전략 비교) |
| [research/20260326-ctx-goal1-goal2-final.md](research/20260326-ctx-goal1-goal2-final.md) | Goal 1+2 최종 달성 보고서 — 코드+문서 통합 인덱싱 구현, 문서 R@5=0.933, 크로스 세션 Recall@10=0.567, heading_paraphrase R@3=1.000 |
| [decisions/20260326-import-bfs-over-ast.md](decisions/20260326-import-bfs-over-ast.md) | 결정: IMPLICIT_CONTEXT에 AST 대신 import BFS 채택 — IMPLICIT R@5 0.044→0.715, FastAPI 속도 문제 회피 |
| [decisions/20260326-non-symbols-frozenset.md](decisions/20260326-non-symbols-frozenset.md) | 결정: _NON_SYMBOLS frozenset — 동사/접속사 30개 제거로 SEMA_CONC false positive 제거, recall 0.000→0.587 |
| [decisions/20260326-path-derived-module-to-file.md](decisions/20260326-path-derived-module-to-file.md) | 결정: 파일 경로 기반 module_to_file 파생 — 실제 코드베이스 MODULE_NAME 상수 없음 문제 해결, AgentNode 5x 붕괴 핵심 수정 |
| [decisions/20260326-unified-doc-code-indexing.md](decisions/20260326-unified-doc-code-indexing.md) | 결정: .py+.md 통합 인덱싱 — AdaptiveTriggerRetriever에 문서 파일 추가, Goal 1 트리거→코드+문서 동시 서페이싱 |
| [decisions/20260326-concept-extraction-sema-conc.md](decisions/20260326-concept-extraction-sema-conc.md) | 결정: "related to X" 패턴에서 X만 concept.value 추출 — 구문 전체 대신 핵심 개념어만 검색 |
| [../benchmarks/results/decision_recall_eval.md](../benchmarks/results/decision_recall_eval.md) | Decision Recall Rate 측정 — DRR@3=1.000, DRR@5=1.000 (5/5 결정 재복원), TEMPORAL_HISTORY 트리거 검증 |
| [research/20260326-ctx-benchmark-validation-roadmap.md](research/20260326-ctx-benchmark-validation-roadmap.md) | 공인 벤치마크 검증 로드맵 — Goal2: CoIR(NDCG@10 추정 0.60-0.68)/RepoBench 즉시 제출, Goal1: 공인 벤치마크 공백, LongMemEval partial proxy |
| [research/20260326-ctx-vs-claudecode-tools.md](research/20260326-ctx-vs-claudecode-tools.md) | CTX vs Claude Code 내장 도구 성능 비교 — Goal1: 네이티브 파일 검색 不在(CTX 독보적, R@10=0.567), Goal2: 1.89x BM25 실증/mcp__code-search__ 대비 미지, IMPLICIT_CONTEXT 명확 우위, P0=head-to-head 필요 |
| [../benchmarks/results/trigger_token_analysis.md](../benchmarks/results/trigger_token_analysis.md) | SG3+SG2: Trigger-type별 R@10 분해 (SEMANTIC=0.880, EXPLICIT=0.566, TEMPORAL=0.500, IMPLICIT=0.424) + 토큰 비용 측정 (TEMPORAL 40K tok/q 급등, IMPLICIT 6K/q 최저) |
| [../benchmarks/results/mcp_code_search_headtohead.md](../benchmarks/results/mcp_code_search_headtohead.md) | SG1: mcp__code-search__ vs CTX head-to-head — 8쿼리 file-level R@5: CTX=0.50, mcp=0.00. 구조적 차이: chunk-level semantic vs file-level trigger |
| [../benchmarks/results/coir_format_analysis.md](../benchmarks/results/coir_format_analysis.md) | SG4: CoIR 공식 벤치마크 형식 분석 — CodeSearchNet=CODE→NL (CTX와 반대 방향), cosqa=NL→code (적합), RepoBench-R 권고 |
| [../benchmarks/results/cosqa_official_eval.json](../benchmarks/results/cosqa_official_eval.json) | CosQA 공식 평가 결과 — coir-eval==0.7.0, N=500, NDCG@10=0.1223, Recall@10=0.232, MAP=0.099 (TF-IDF BM25-equivalent) |
| [../benchmarks/results/final_report_v8.md](../benchmarks/results/final_report_v8.md) | P8 최종 종합 리포트 — TEMPORAL_HISTORY R@10=0.600(목표 달성), CosQA NDCG@10=0.1223, 7개 데이터셋 통합, 논문 수치 완결 |
| [research/20260327-ctx-paper-numbers-critique.md](research/20260327-ctx-paper-numbers-critique.md) | CTX Key Paper Numbers 비판적 평론 — 수치별 위험도(RepoBench/DRR HIGH, TES/CosQA MEDIUM), 리뷰어 공격 예상, 논문 제출 전 필수 수정사항 |
| [../benchmarks/results/final_report_v9.md](../benchmarks/results/final_report_v9.md) | **P9 수정 최종 리포트** — Classifier 버그 수정 후 정직한 수치: CTX R@10=0.457(수정), BM25 baseline=0.556 추가, TEMPORAL_HISTORY CTX+24pp, DRR N=3 제거, 학술 제출 수준 방어력 확보 |
| [research/20260327-ctx-downstream-eval.md](research/20260327-ctx-downstream-eval.md) | CTX Downstream LLM 평가 — CTX-with vs without ablation, G1(memory recall Δ+0.700) / G2(coding Δ+0.582, hallucination 2.00→0.00) |
| [research/20260327-ctx-real-project-self-eval.md](research/20260327-ctx-real-project-self-eval.md) | CTX 실제 코드베이스 자체 평가 — instruction-style query R@5=0.000 (proxy R@3=0.862와 격차), 실패 원인 분석 + 개선 방향 |
| [research/20260328-ctx-downstream-minimax-eval.md](research/20260328-ctx-downstream-minimax-eval.md) | CTX Downstream LLM 평가 (MiniMax M2.5 실제 호출) — G1 Δ+0.781(WITH=1.000), G2 Δ+0.375, Overall Δ+0.578 STRONGLY IMPROVES |
| [research/20260328-ctx-real-codebase-g2-eval.md](research/20260328-ctx-real-codebase-g2-eval.md) | CTX G2 실제 코드베이스 평가 (MiniMax M2.5) — real code Δ+0.200, over-anchoring 발견, synthetic vs real 비교 |
| [research/20260328-ctx-downstream-eval-complete.md](research/20260328-ctx-downstream-eval-complete.md) | CTX Downstream LLM 평가 완전 보고서 — G1/G2 synthetic+real 3실험 종합, over-anchoring 분석, CTX 개선 방향 |
| [research/20260328-adaptive-trigger-generalization-fix.md](research/20260328-adaptive-trigger-generalization-fix.md) | AdaptiveTrigger 외부 코드베이스 일반화 수정 — import graph + module_to_file 범용화, IMPLICIT R@5 +362~441% |
| [research/20260328-trigger-classifier-semantic-fix.md](research/20260328-trigger-classifier-semantic-fix.md) | TriggerClassifier SEMANTIC 수정 — "Find all code related to X" 오분류 수정, SEMANTIC R@5 near-zero→0.531~0.958 |
| [../benchmarks/results/final_report_v10.md](../benchmarks/results/final_report_v10.md) | **P10 최종 리포트 (현재)** — Trigger+Import 두 버그 수정 후: External R@5=0.495 [CI: 0.441,0.550], 목표 0.25 달성, Bootstrap CI 추가 |

## Related
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
- [[projects/CTX/research/20260328-ctx-downstream-nemotron-eval-v2|20260328-ctx-downstream-nemotron-eval-v2]]
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|20260328-ctx-downstream-minimax-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-nemotron-eval|20260328-ctx-downstream-nemotron-eval]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|20260328-ctx-real-codebase-g2-eval]]
- [[projects/CTX/research/20260328-ctx-downstream-eval-nemotron-final|20260328-ctx-downstream-eval-nemotron-final]]
