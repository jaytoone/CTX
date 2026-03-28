# Decision: Import BFS over AST parsing for IMPLICIT_CONTEXT

**Date**: 2026-03-26
**Type**: TechnicalDecision
**Status**: Active

## 결정 내용

`IMPLICIT_CONTEXT` 쿼리 처리에서 AST 기반 call graph 대신 **regex import BFS**를 사용한다.

## 근거 (Why)

1. **속도**: AST 파싱은 FastAPI(928 files) 규모에서 인덱싱 시간이 10x 이상 증가
2. **정확도**: `from X import Y` / `import X.Y.Z` regex 파싱으로 실제 Python import chain 완전 추출 가능
3. **결과**: IMPLICIT_CONTEXT R@5 = 0.044 → 0.715 (+1,521% on AgentNode)

## 대안 검토

- **AST full graph** (RANGER-approx 방식): call graph 포함으로 더 정밀하나 느림. 외부 공개 프로젝트에서 유리할 수 있음.
- **하이브리드**: import BFS + 선택적 call graph → 미래 개선 여지

## 적용 범위

`src/retrieval/adaptive_trigger.py` — `_index_imports()`, `_traverse_imports()`

## 재검토 조건

FastAPI/Flask R@5 < 0.2 유지 시 AST 방식 재검토. 현재 0.145→0.440 (iter5 기준).
