# Decision: "related to X" concept extraction for SEMANTIC_CONCEPT

**Date**: 2026-03-26
**Type**: TechnicalDecision
**Status**: Active

## 결정 내용

`TriggerClassifier`에서 SEMANTIC_CONCEPT 분류 시 쿼리에서 **실제 개념어(X)**를 추출한다.
"related to X", "about X", "everything about X" 패턴에서 X만 concept.value로 반환.

## 근거 (Why)

1. **이전 문제**: "Find all code related to euler" → value = "related to euler" (전체 구문)
   → `_concept_retrieve`에서 "related", "euler" 모두 개념어로 처리 → stem 4자 매칭에서 "rela" 히트 → 노이즈
2. **해결**: regex로 "related to (\w+)" 패턴 매칭 → X만 추출 → value = "euler"
3. **결과**: 개념 검색 정밀도 향상 (SEMA_CONC recall 개선의 일부)

## 구현

```python
_concept_extract = re.search(
    r'(?:related to|about|code for|everything about|module for|responsible for)'
    r'\s+([a-zA-Z_][a-zA-Z0-9_\s]{1,30})',
    prompt_lower
)
if _concept_extract:
    concept_value = _concept_extract.group(1).strip()
```

## 적용 범위

`src/trigger/trigger_classifier.py` — `_classify_semantic_concept()` 분기

## 재검토 조건

복합 개념어 ("X and Y", "X or Y") 처리 시 첫 번째 X만 추출하는 한계. n=5 이상 실패 케이스 발생 시 확장 검토.
