# Decision: _NON_SYMBOLS frozenset for trigger classifier

**Date**: 2026-03-26
**Type**: TechnicalDecision
**Status**: Active

## 결정 내용

`TriggerClassifier`에서 CamelCase 패턴 매칭 전에 **30+ 동사/접속사 단어를 frozenset으로 필터링**한다.

## 근거 (Why)

1. **문제**: "Find all code related to euler" → EXPLICIT_SYMBOL('Find', 0.70) 오분류
   - CamelCase regex `[A-Z][a-z]{2,}` 가 "Find", "Show", "Fix" 등을 심볼로 잘못 인식
2. **해결**: `_NON_SYMBOLS` frozenset으로 30개 이상 영어 동사/문장 시작 단어 사전 제거
3. **결과**: SEMA_CONC recall 0.000 → 0.587 on AgentNode

## 핵심 패턴

```python
_NON_SYMBOLS = frozenset({
    "the", "all", "for", "and", "show", "find", "get", "list",
    "fix", "modify", "change", "update", "implement", "add", ...
})
```

## 적용 범위

`src/trigger/trigger_classifier.py` — `_is_symbol_like()` 메서드

## 재검토 조건

새로운 쿼리 유형에서 false negative 발생 시 (실제 심볼명이 동사형인 경우 — 예: `run`, `build`).
현재 `run`, `build`는 frozenset에 포함됨 → 심볼명이 `run`인 경우 EXPLICIT_SYMBOL 놓칠 수 있음.

## Related
- [[projects/CTX/research/20260328-trigger-classifier-semantic-fix|20260328-trigger-classifier-semantic-fix]]
