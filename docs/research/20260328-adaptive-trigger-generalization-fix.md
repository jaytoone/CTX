# AdaptiveTriggerRetriever 외부 코드베이스 일반화 개선

**Date**: 2026-03-28
**Status**: 완료 (paper-tier improvement omc-live iter 1)

## 요약

외부 코드베이스(Flask/FastAPI/Requests)에서 IMPLICIT_CONTEXT 트리거의 recall을 3-5배 개선.
전체 R@5 평균: 0.205 → 0.227 (+11%).

## 근본 원인 분석

`adaptive_trigger.py`의 3개 함수가 CTX-내부 코드베이스 관례에만 의존:

### 1. `_index_imports` — 실제 Python import 미파싱
```python
# 기존 (주석 스타일만): 
for match in re.finditer(r'#\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)', content):
```
→ 외부 코드베이스는 `# import X` 주석 없음 → `import_graph` 전체 비어있음

### 2. `module_to_file` — `MODULE_NAME = "..."` 상수에만 의존
→ 외부 코드베이스는 이 CTX 관례 없음 → `_traverse_imports` 실패

### 3. `_concept_retrieve` BM25 쿼리 오염
→ "Find all code related to routing" 전체 텍스트 사용 → "find", "code", "related" 노이즈

## 구현된 수정

### Fix 1: 실제 Python import 파싱
```python
# Real Python: import X, import X.Y
for m in re.finditer(r'^\s*import\s+([\w.]+)', content, re.MULTILINE):
    ...
# Real Python: from X import Y  
for m in re.finditer(r'^\s*from\s+([\w.]+)\s+import', content, re.MULTILINE):
    ...
```

### Fix 2: 파일 경로 기반 모듈명 도출
```python
# e.g. src/auth/session.py -> session, auth.session, src.auth.session
parts = [p for p in stem.split("/") if p and p != "__init__"]
for i in range(len(parts)):
    mod_key = ".".join(parts[i:])
    module_to_file.setdefault(mod_key, rel_path)
```

### Fix 3: BM25 쿼리에 concept만 사용 (full query_text 제거)
```python
# concept_expanded 사용 (not query_text)
concept_expanded = re.sub(r'([a-z])([A-Z])', r'\1 \2', concept).replace("_", " ")
query_tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{1,}', concept_expanded.lower())
```

### Fix 4: concept_index 노이즈 방지
BM25를 1차 랭커로, concept_index는 BM25 결과에만 15% boost (신규 파일 주입 금지)

### Fix 5: 벤치마크 결정론 확보
`real_codebase_loader.py`: `set()→sorted()`, `dirs→sorted(dirs)`, `filenames→sorted(filenames)`,
`interesting_concepts.keys()→sorted(...)` — 랜덤 시드 42 완전 결정론화

## 결과 비교

### Overall R@5

| 코드베이스 | Baseline | After Fix | Delta |
|-----------|---------|-----------|-------|
| Flask     | 0.238   | **0.272** | +14.3% |
| FastAPI   | 0.091   | **0.094** | +3.8% |
| Requests  | 0.285   | **0.316** | +10.9% |
| **Mean**  | **0.205** | **0.227** | **+10.8%** |

### IMPLICIT_CONTEXT R@5 (가장 큰 개선)

| 코드베이스 | Baseline | After Fix | Delta |
|-----------|---------|-----------|-------|
| Flask     | 0.052   | **0.238** | +362% |
| FastAPI   | 0.006   | **0.024** | +319% |
| Requests  | 0.038   | **0.203** | +441% |

## 잔존 한계

- SEMANTIC_CONCEPT: 여전히 낮음 (~0.01-0.10) — AST 기반 concept 추출로 해결 필요
- 전체 R@5 평균 0.227 < 0.25 목표 (IMPLICIT 개선만으로는 부족)
- FastAPI (928 files): 대규모 코드베이스에서 개선 폭 제한적

## 다음 단계

1. AST 기반 SEMANTIC 개선: `ast.parse()`로 docstring/decorator/type annotation에서 개념 추출
2. 통계적 엄밀성: CI 95% 추가, DRR N=3 교체
3. 논문 재포지셔닝: IMPLICIT+G1 결과 기반 스토리 강화

## Related
- [[projects/CTX/research/20260325-ctx-paper-tier-evaluation|20260325-ctx-paper-tier-evaluation]]
