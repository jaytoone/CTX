# [expert-research-v2] CTX 실험 방식 상위 티어 논문 기준 평론
**Date**: 2026-03-24  **Skill**: expert-research-v2

## Original Question
CTX 실험 방식이 ACL/EMNLP/NeurIPS/ICLR 상위 티어 논문 기준으로 어떤 수준인가?

## Web Facts
[FACT-1] ACL/ARR: novelty + technical quality + reproducibility 필수, checklist 위반 시 desk rejection (http://aclrollingreview.org/reviewerguidelines)
[FACT-2] Synthetic→Real gap (EMNLP 2025): 합성 84-89% → 실제 25-34% (https://arxiv.org/abs/2510.26130)
[FACT-3] DeepCodeBench: PR 기반 1,144 QA pairs, 멀티파일 (https://www.qodo.ai/blog/deepcodebench)
[FACT-4] Code Retrieval 연구: 50,000+ lines, 338 files (https://www.preprints.org/manuscript/202510.0924)
[FACT-5] SWINGARANA: BM25 + syntax chunking + dense reranking 조합 (arxiv 2505.23932)
[FACT-6] NeurIPS 2025: 코드 제출 의무화 (https://neurips.cc/public/guides/CodeSubmissionPolicy)
[FACT-7] COIR (ACL 2025): 코드 정보 검색 표준 벤치마크 (https://aclanthology.org/2025.acl-long.1072.pdf)

## Final Conclusion — 상위 티어 제출 로드맵

### 현재 상태 판정
- ACL/EMNLP main: reject 확률 80%+
- Findings: reject 확률 60%+ (보강 시 가능)
- NeurIPS/ICLR: 현재 방향으로 구조적 진입 어려움

### Findings 달성 필수 4가지 (1단계)
1. Real 데이터셋 3-5개 프로젝트 확장 (300+ files, 200+ queries)
2. 통계 검증 (신뢰구간, bootstrap test)
3. Error Analysis 섹션 (실패 케이스 패턴 분류)
4. Ablation Study (Trigger 구성요소별 기여)

### Main Track 추가 4가지 (2단계)
5. COIR 벤치마크 평가
6. pass@1 100+ 샘플, 복수 LLM
7. SoTA 시스템 직접 비교 (COIR 기준 reported numbers)
8. TES 지표 이론적 정당화

## Sources
- http://aclrollingreview.org/reviewerguidelines
- https://arxiv.org/abs/2510.26130
- https://www.qodo.ai/blog/deepcodebench
- https://neurips.cc/public/guides/CodeSubmissionPolicy
- https://aclanthology.org/2025.acl-long.1072.pdf
