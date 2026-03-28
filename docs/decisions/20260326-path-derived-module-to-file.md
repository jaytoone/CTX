# Decision: Path-derived module_to_file mapping

**Date**: 2026-03-26
**Type**: TechnicalDecision
**Status**: Active

## 결정 내용

`AdaptiveTriggerRetriever`에서 `MODULE_NAME = "..."` 상수 외에도,
**파일 경로에서 직접 dotted module 이름을 파생**하여 `module_to_file`에 등록한다.

## 근거 (Why)

1. **문제**: 실제 코드베이스(AgentNode/Flask/FastAPI)는 CTX 합성 데이터의 `MODULE_NAME` 상수를 사용하지 않음
   → `module_to_file` 딕셔너리가 거의 비어 있음 → IMPLICIT_CONTEXT BFS 탐색 불가
2. **해결**: `src/retrieval/adaptive_trigger.py` → "adaptive_trigger", "retrieval.adaptive_trigger", "src.retrieval.adaptive_trigger" 등 모든 dotted prefix 등록
3. **결과**: AgentNode R@5: 0.176 → 0.522 (실제 코드베이스 5x 붕괴 해결의 핵심)

## 구현

```python
path_parts = [p for p in parts.split("/") if p and p != "__init__"]
for i in range(len(path_parts)):
    dotted = ".".join(path_parts[i:])
    self.module_to_file[dotted] = rel_path
```

## 적용 범위

`src/retrieval/adaptive_trigger.py` — `_index()` 메서드

## 재검토 조건

패키지 구조가 비표준(namespace packages, src-layout 등)인 경우 dotted prefix 불일치 가능.
