# [expert-research-v2] CTX 약점 보완 대안 기술 분석

**Date**: 2026-03-27  **Skill**: expert-research-v2

## Original Question
CTX의 약점(외부 코드베이스 일반화 실패, 자유 키워드 검색 BM25 열세, 의미 기반 교차 파일 추론 불가)을 보완할 수 있는 대안 기술/시스템은?

## Web Facts
- [FACT-2] BEIR 2.0 (Jan 2026): Dense 54.8% > BM25 41.2% NDCG@10. Code-tuned: 58.9% vs general 44.1% (+33.5%). Hybrid는 Dense 대비 +2.8%만 개선. Source: app.ailog.fr/en/blog/news/beir-benchmark-update
- [FACT-4] LocAgent (ACL 2025, Yale/Stanford/USC): DHG(Directed Heterogeneous Graph) 파싱, 파일 localization 92.7%, 인덱싱 수 초, +12% Pass@10. Source: aclanthology.org/2025.acl-long.426.pdf
- [FACT-7] BM25: 서브밀리초, 빌리언 스케일. Dense 인덱스 24시간+. Source: johal.in/pyserini-bm25
- [FACT-8] Dependency graph GraphRAG: GPT-4o 수준, LLM triplet 추출 없이 파싱 기반. Source: arxiv.org/html/2507.03226v2
- [FACT-10] LocAgent 멀티홉: Hop 0-1 >80%, Hop 2 ~60%, Hop 3+ ~40%. Agent > embedding on degradation. Source: aclanthology.org/2025.acl-long.426.pdf

## Final Conclusion

### 약점별 대안 매핑

| 약점 | 즉시 (1-2일) | 중기 (1-2주) | 장기 |
|------|------------|------------|------|
| 외부 코드베이스 R@5=0.152 | AST 파서 기반 심볼 추출 (heuristic 제거) | LocAgent DHG non-LLM 버전 | LocAgent 풀스택 |
| keyword R@3=0.379 < BM25=0.667 | **TF-IDF → BM25 교체** | BM25 + Code-tuned Embedding | Dense 단독 (재인덱싱 파이프라인 포함) |
| 교차 파일 추론 불가 | Import graph BFS 확장 | Dependency GraphRAG (파싱 기반, non-LLM) | LocAgent 멀티홉 에이전트 |

## Sources
- [LocAgent ACL 2025](https://aclanthology.org/2025.acl-long.426.pdf)
- [BEIR 2.0](https://app.ailog.fr/en/blog/news/beir-benchmark-update)
- [Dependency GraphRAG](https://arxiv.org/html/2507.03226v2)
