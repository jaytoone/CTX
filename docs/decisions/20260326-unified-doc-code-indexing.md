# Decision: Unified .py + .md indexing in AdaptiveTriggerRetriever

**Date**: 2026-03-26
**Type**: TechnicalDecision
**Status**: Active

## 결정 내용

`AdaptiveTriggerRetriever._index()`에서 `.py` 파일과 `.md`/`.txt`/`.rst` 파일을 **동일한 인덱스**에 포함한다.

## 근거 (Why)

1. **사용자 Goal 1 비전**: "프롬프트 트리거 → 코드 + 문서 + 결정 기억 동시 서페이싱"
   → 코드와 문서가 별도 시스템이면 단일 쿼리로 통합 검색 불가
2. **문서 검색 결과**: CTX-doc R@5=0.933 (BM25=0.833 대비 +12%)
3. **heading_paraphrase**: CTX R@3=1.000 — 자연어 트리거 → 헤딩 연상 매칭 완벽

## 구현 핵심

```python
# _index_doc_file(): .md 전용 인덱서
# - 마크다운 헤딩 → symbol_index
# - 헤딩 단어 → concept_index
# - 파일명 스템 → module_to_file
# - 전체 내용 → TF-IDF 코퍼스
```

## 트레이드오프

- **단점**: 코드+문서 혼합 TF-IDF 공간 → 코드-코드 유사도 희석 가능
- **측정 필요**: 통합 후 코드 검색 R@5 변화 (현재 미측정)

## 적용 범위

`src/retrieval/adaptive_trigger.py` — `_index()`, `_index_doc_file()` (신규)

## 재검토 조건

코드 검색 R@5 대비 통합 전 -5%p 이상 저하 시 분리 인덱스 구조 검토.

## 검색 키워드 (Decision Recall)

- markdown indexing decision
- extend retriever include markdown docs
- add markdown file support retriever
- _index_doc_file decision
- why added markdown retrieval support
