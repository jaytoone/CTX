# vault.db Vector Migration + Retrieval Benchmark

**Date**: 2026-04-10  **Scope**: claude-vault chat memory 시스템

## 배경 및 동기

20260409 연구(`bm25-memory-generalization-research.md`)에서 도출된 결론:
> "오픈셋 0.250 = BM25 천장(22.1%), **hybrid BM25+Dense 필요**"

이 문서는 해당 결론의 직접 구현 + 정량 검증 결과를 기록한다.

---

## 1. 구현 (vault.db Vector Migration)

### 구성 요소

| 컴포넌트 | 경로 | 역할 |
|----------|------|------|
| `build-vec-index.py` | `~/.local/share/claude-vault/` | 일회성 배치 임베딩 스크립트 |
| `vec-daemon.py` | `~/.local/share/claude-vault/` | Unix socket 데몬, 모델 상주 |
| `chat-memory.py` | `~/.claude/hooks/` | hybrid 검색으로 업데이트 |
| `settings.json` | `~/.claude/` | SessionStart에서 데몬 자동 시작 |

### 임베딩 스펙

- **모델**: `intfloat/multilingual-e5-small` (384-dim, 한국어+영어 크로스링구얼)
- **텍스트 처리**: 메시지 첫 400자, `"passage: "` prefix
- **쿼리 처리**: `"query: "` prefix (asymmetric embedding)
- **정규화**: L2 (코사인 유사도)
- **저장**: sqlite-vec `messages_vec` virtual table (`vec0`)

### 인덱스 통계

- vault.db 전체 메시지: 145,881개
- 임베딩 대상 (user/assistant, 50자+, non-tool): **44,981개**
- 빌드 시간: 133.8s (336 msg/s)
- 인덱스 크기: ~44,981 × 384 × 4 bytes ≈ 69MB

### Hybrid 랭킹 공식

```
hybrid_score = 0.5 × cosine_similarity + 0.5 × bm25_rank_normalized
```

- BM25: rank 0 → 1.0, rank N → 0.0
- Vector: distance 0 → 1.0, distance 2 → 0.0

---

## 2. 정량 벤치마크 결과

**스크립트**: `benchmark_retrieval.py` (FromScratch 프로젝트)  
**쿼리**: 25개 (5가지 타입 × 5개)  
**메트릭**: Precision@5 (heuristic — 쿼리 키워드 포함 여부)

### Precision@5 by Query Type

| 쿼리 타입 | BM25 P@5 | Vector P@5 | **Hybrid P@5** | Overlap/5 | Vec-Unique/5 |
|-----------|----------|------------|---------------|-----------|--------------|
| 한국어 NL (의미) | 0.72 | 0.76 | **0.80** | 0.6 | 4.4 |
| 한국어 기술 | 0.76 | **0.92** | **0.96** | 0.8 | 4.2 |
| 영어 기술 | 0.64 | 0.72 | **0.88** | 0.6 | 4.4 |
| 혼합 (ko+en) | **0.88** | 0.72 | 0.80 | 1.0 | 4.0 |
| 인프라/훅 | 0.80 | **0.96** | **0.96** | 0.4 | 4.6 |
| **전체 평균** | **0.76** | **0.82** | **0.88** | **0.7** | **4.3** |

**핵심 수치**:
- Hybrid vs BM25: **+16% P@5 개선** (0.76 → 0.88)
- 평균 overlap: 0.7/5 (= BM25·Vector top-5의 86%가 서로 다른 결과)
- 평균 vec-unique: 4.3/5 (vector가 BM25 대비 4.3개 신규 결과 추가)

### 주목할 패턴

1. **한국어 기술 쿼리에서 Vector > BM25** (0.92 vs 0.76): multilingual-e5-small이 한국어 기술 용어 임베딩에서 FTS5 tokenizer를 앞서는 결과 — "ZeRO-3 gradient 동기화 오류" → BM25=0.00, Vector=1.00
2. **mixed 타입에서 BM25 우위**: 고유명사(overlap_comm, v14, SeqNum)는 키워드 검색이 유리
3. **인프라 쿼리 vector 우위**: "claude-vault import 방법" → BM25=0.00, Vector=0.80

---

## 3. Vector-Unique 히트 관련성 샘플링

vector-unique 히트(BM25가 놓친 결과)의 실제 관련성 샘플링 결과:

| 쿼리 | Vec-Unique 히트 | 관련 비율 |
|------|-----------------|-----------|
| 학습이 멈췄을 때 어떻게 해야 하나요 | 5개 중 3개 샘플 | 3/3 (100%) |
| 모델 훈련 GPU 메모리 부족 | 3개 샘플 | 3/3 (100%) |
| 에러 발생 학습 실패 원인 | 3개 샘플 | 2/3 (67%) |
| 훈련 속도 최적화 | 3개 샘플 | 1/3 (33%) |

**추정 전체 관련성**: ~75% (단순 다른 결과가 아닌 유효한 추가 recall)

---

## 4. KNN 확장성 분석

sqlite-vec `vec0`는 brute-force linear scan — O(n).

| k (fetch) | Avg 레이턴시 |
|-----------|-------------|
| 10 | 30ms |
| 100 | 40ms |
| 1,000 | 97ms |
| 4,096 (최대) | 98ms |

**현재 운영 레이턴시**: hybrid hook 총 80-120ms

| 임베딩 수 | 예상 레이턴시 | 허용 여부 |
|-----------|--------------|----------|
| 44,981 (현재) | ~98ms | ✅ |
| 100,000 | ~217ms | ✅ |
| 200,000 | ~435ms | ⚠️ 허용 한계 |
| 500,000 | ~1,087ms | ❌ HNSW 필요 |

**결론**: 현재 44,981개 기준 약 **4배 성장(200k)까지** 현 구조 유지 가능.  
200k 초과 시 sqlite-vec HNSW 인덱스 또는 외부 벡터 DB(Faiss/Qdrant) 전환 필요.

---

## 5. CTX 연구와의 연관성

### 20260409 연구 결론 → 구현 완료

| 20260409 진단 | 20260410 구현 | 검증 결과 |
|--------------|---------------|----------|
| "BM25 오픈셋 천장 22.1%" | multilingual-e5-small 추가 | Vector P@5=0.82 (+8%p) |
| "hybrid BM25+Dense 필요" | hybrid_score = 0.5×cos + 0.5×bm25 | Hybrid P@5=0.88 (+16%p) |
| "cross-session 포지셔닝" | vault.db 전체 44,981개 임베딩 | avg overlap 0.7 (보완적) |

### CTX 시스템 관점에서의 의미

CTX 아키텍처의 chat-memory 계층이 BM25 단독에서 hybrid로 업그레이드됨:
- G1 (git commit memory) + G2 (doc search) 에 더해 CM이 semantic recall 추가
- 특히 "최근 해결한 방법을 NL로 물을 때" 커버리지 향상 (한국어 NL P@5 0.72→0.80)

---

## 6. 한계 및 주의사항

1. **Precision@5 heuristic**: 쿼리 키워드 포함 여부로 관련성 판단 — manual ground truth 없음. 실제 값은 오차 있음.
2. **sqlite-vec k 제한**: max k=4096 (linear scan 방식). 더 많은 후보가 필요하면 제약.
3. **400자 truncation**: 긴 메시지의 후반부 context 손실. 코드 블록이 뒤에 있는 경우 임베딩 품질 저하 가능.
4. **데몬 장애 시 BM25 fallback**: vec-daemon.py 크래시 시 hybrid 비활성화, BM25-only로 자동 전환.

---

- [[projects/CTX/research/20260409-bm25-memory-generalization-research|bm25-memory-generalization-research]] — 이 구현의 이론적 근거
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|session-6c4f589e-chat-memory]] — chat-memory.py BM25 초기 구현
- [[projects/FromScratch/research/20260410-vault-vector-migration|vault-vector-migration]] — FromScratch 상세 migration 기록
- [[projects/FromScratch/research/20260410-retrieval-benchmark|retrieval-benchmark]] — 25쿼리 A/B 벤치마크 전체 결과

## Related
- [[projects/CTX/research/20260426-g1-hybrid-rrf-dense-retrieval|20260426-g1-hybrid-rrf-dense-retrieval]]
- [[projects/CTX/research/20260426-g2-docs-hybrid-dense-retrieval|20260426-g2-docs-hybrid-dense-retrieval]]
- [[projects/CTX/research/20260424-memory-retrieval-benchmark-landscape|20260424-memory-retrieval-benchmark-landscape]]
- [[projects/CTX/research/20260426-ctx-retrieval-benchmark-synthesis|20260426-ctx-retrieval-benchmark-synthesis]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260417-ctx-semantic-search-upgrade-sota|20260417-ctx-semantic-search-upgrade-sota]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
