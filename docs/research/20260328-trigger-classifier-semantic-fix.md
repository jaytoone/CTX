# CTX TriggerClassifier SEMANTIC Fix — 2026-03-28

## Problem

All "Find all code related to X" queries were being classified as EXPLICIT_SYMBOL instead of SEMANTIC_CONCEPT, causing SEMANTIC R@5 ≈ 0 on external codebases.

## Root Cause

In `_detect_explicit_symbols`, `SYMBOL_PATTERNS[1]` is:
```python
re.compile(r'\b([A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]+)*)\b')
```

This matches ANY word starting with uppercase — including "Find", "Show", "Get", "What", "Where". So:
- "**Find** all code related to routing" → EXPLICIT_SYMBOL("Find") conf=0.70
- SEMANTIC_CONCEPT got conf=0.70 ("related to" + "all code" = 2 keywords)
- Tie → EXPLICIT wins (added first)

Exception: when concept word was in SEMANTIC_KEYWORDS (e.g., "authentication"), SEMANTIC got conf=0.80 > 0.70, winning correctly. This explains why "authentication" queries worked but "routing"/"middleware"/"template" didn't.

## Fix

### 1. Common Words Filter

```python
_COMMON_WORDS = frozenset({
    "find", "show", "get", "list", "what", "where", "how", "why",
    "the", "all", "for", "and", ...
})
```

Applied in `_detect_explicit_symbols`: skip symbol if `symbol.lower() in self._COMMON_WORDS`.

### 2. Concept Word Extraction

```python
_CONCEPT_EXTRACT_PATTERNS = [
    re.compile(r'related\s+to\s+([a-z_][a-z0-9_]*)', re.IGNORECASE),
    re.compile(r'about\s+([a-z_][a-z0-9_]{2,})', re.IGNORECASE),
    ...
]
```

`_detect_semantic_concepts` now extracts the actual concept (e.g., "routing") from the query instead of returning "related to" as the concept value.

### 3. Confidence Boost

When explicit semantic marker ("related to", "all code") is present:
- SEMANTIC confidence = 0.70–0.85 (was 0.50–0.85)
- Ensures SEMANTIC wins over any remaining EXPLICIT false positives

## Impact

| Dataset | SEMANTIC Before | SEMANTIC After | Overall R@5 Δ |
|---------|----------------|----------------|---------------|
| Small | 0.682 | 0.958 | +0.120 |
| Medium | 0.159 | 0.798 | +0.133 |
| Flask | 0.000–0.098 | 0.670 | +0.273 |
| FastAPI | 0.000 | 0.531 | +0.189 |
| Requests | 0.013 | 0.788 | +0.312 |
| External mean | ~0.04 | **0.663** | **+0.242** |

## Combined Effect (both fixes: import graph + trigger classifier)

- External R@5: 0.217 → **0.495** (+128%)
- Target 0.25: **ACHIEVED** (CI: [0.441, 0.550])

## Related
- [[projects/CTX/decisions/20260326-concept-extraction-sema-conc|20260326-concept-extraction-sema-conc]]
