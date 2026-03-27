# CoIR 공식 벤치마크 형식 분석 및 CTX 적용 가능성
**Date**: 2026-03-26  **Package**: coir-eval==0.7.0

## 설치 완료

```
pip3 install coir-eval --break-system-packages
Successfully installed coir-eval-0.7.0 pytrec-eval-terrier-0.5.10 voyageai-0.3.7
```

## 사용 가능한 태스크

| Task | Status | N_queries | N_corpus |
|---|---|---|---|
| codesearchnet (6 languages) | OK | ~14,918 (py) | ~280,310 |
| apps | OK | 500 | 20,604 |
| cosqa | OK | 500 | 20,604 |
| codesearchnet_py (별도) | FAIL (Hub 미존재) | - | - |

## CoIR CodeSearchNet Python 형식

```
corpus[c0] = {
  "text": "Set the text for this element. Arguments: text (str)...",  # 자연어 설명
  "title": ""
}

queries[q265734] = """def sina_xml_to_url_list(xml_data):
    '''str->list Convert XML to URL List. From Biligrab.'''
    ...actual code..."""  # Python 함수 코드

qrels[q265734] = {"c265608": 1}  # query → relevant corpus doc
```

## 핵심 발견: Task Direction Mismatch

| 방향 | CoIR CodeSearchNet | CTX |
|---|---|---|
| Query | **코드 함수** (Python code) | **자연어** (NL description) |
| Corpus | **자연어 설명** (docstrings) | **Python 파일** (code) |
| 검색 방향 | CODE → DESCRIPTION (NL) | NL → CODE |

**CoIR의 CodeSearchNet Python task는 CODE→NL 방향**으로 CTX의 NL→CODE와 반대.

## CTX 평가 가능 여부

### Option A: 직접 역방향 적용 (NDCG@10 측정 가능)
- corpus를 임시 디렉토리에 텍스트 파일로 저장
- 각 query (code 함수)의 keyword를 추출해 CTX 검색
- 문제: CTX가 NL→code 방향에 최적화되어 있어 code→NL은 부적합

### Option B: RepoBench-R 우선 (더 적합)
- RepoBench: cross-file code completion (NL 컨텍스트 → 코드 파일)
- CTX와 방향 일치 (NL→code file)
- SOTA RANGER=0.5471, CTX 자체 측정 NDCG@10=0.646

### Option C: CosQA 태스크 (query=NL, corpus=code)
- `cosqa`: natural language queries → code snippets
- 방향이 CTX와 일치 (NL→code)
- 단, 함수 수준 검색 (파일 수준 아님) → 일부 불일치

## 권고

1. **단기**: CosQA (N=500) 실행 → CTX BM25 어댑터로 NDCG@10 측정
2. **중기**: RepoBench-R 공식 스크립트 실행 → file-level Recall@K
3. **논문**: CoIR의 direction mismatch를 명시 + RepoBench-R을 주 외부 벤치마크로 사용
4. **CoIR 향후**: CTX를 함수 수준으로 확장하면 apps/cosqa task에 제출 가능

## CosQA 빠른 실행 계획

```python
from coir.data_loader import get_tasks
tasks = get_tasks(tasks=['cosqa'])
corpus, queries, qrels = tasks['CoQA']  # 확인 필요

# CTX BM25 어댑터
class CTXModel:
    def encode_corpus(self, corpus, batch_size, show_progress_bar):
        # BM25 인덱스 구축
        ...
    def encode_queries(self, queries, batch_size, show_progress_bar):
        # BM25 query vector
        ...
```
