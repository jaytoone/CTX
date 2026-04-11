# G1/G2 Hook Architecture 논문 급 개선 — 실증 벤치마크
**Date**: 2026-04-11 | **Type**: Implementation + empirical benchmark

## 요약

CTX hook 아키텍처(git-memory G1 + chat-memory G2)를 세 가지 실증 기반 개선으로 최적화.
G1 recall **+47.6% 상대적 향상** (0.292 → 0.431, 12-query benchmark).

---

## 개선 1: G1 — BM25 + Deep Grep + Semantic Hybrid (git-memory.py)

### 문제
- 기존: 최근 n=15 커밋 recency-only 선택 → Recall@7 = 0.292
- BM25 offline benchmark ceiling: Recall@7 = 0.881
- 실제 훅 vs benchmark gap = 0.589 (67% unexplained variance)

### 원인 분석
| 원인 | 영향 | 설명 |
|------|------|------|
| 창 크기 부족 | 높음 | n=15: 관련 커밋이 16-100에 있으면 누락 |
| 관련성 무시 | 높음 | 최신≠가장 관련성 높음 |
| 전체 히스토리 미탐색 | 중간 | 특정 키워드가 30+ 전 커밋에만 존재 |
| Paraphrase mismatch | 중간 | BM25 lexical ceiling (semantic으로 해결 시도) |

### 구현: 3-Layer 아키텍처

```
Pass 0 (Deep Grep):    git log --grep=<keyword> 전체 히스토리 (무제한 깊이)
                       ↓ 키워드 매칭 결정 커밋 발굴
Pass 1 (Window):       n=30 최근 창 내 decision-bearing 커밋 수집
                       ↓ 둘 merge, 중복 제거
Pass 1.5 (BM25 Rank): rank_bm25.BM25Okapi로 프롬프트 관련성 정렬
                       ↓ 가장 관련성 높은 커밋 우선
Pass 2 (Topic Dedup):  토픽 클러스터당 1개 최상위 선택 → top-7
                       ↓ 다양성 보장
Post (Semantic):       vec-daemon(multilingual-e5-small) hybrid rerank
                       alpha=0.4 × semantic + 0.6 × positional_prior
```

### 핵심 코드 변경

**_bm25_rank_by_prompt()** — 신규 함수:
```python
def _bm25_rank_by_prompt(candidates, prompt_keywords):
    from rank_bm25 import BM25Okapi
    tokenized_corpus = [re.findall(r'[a-zA-Z가-힣][a-zA-Z0-9가-힣]*',
                                    c["subject"].lower()) for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores([k.lower() for k in prompt_keywords])
    indexed = sorted(enumerate(scores), key=lambda x: -x[1])
    return [candidates[i] for i, _ in indexed]
```

**_semantic_rerank()** — 신규 함수:
```python
def _semantic_rerank(decisions, prompt_emb, alpha=0.4):
    # alpha * cosine_sim + (1-alpha) * positional_prior
    # vec-daemon 연결 실패 시 graceful fallback
```

**Deep grep in get_git_decisions()** — Pass 0 추가:
```python
for kw in long_kws[:3]:
    r = subprocess.run(["git", "log", "--format=%H\x1f%s",
                        f"--grep={kw}", "-i", "--max-count=5"], ...)
    # _is_decision() 필터 후 candidates에 merge
```

### 벤치마크 결과 (12 쿼리, CTX 프로젝트)

| 방법 | Recall@7 | vs baseline |
|------|---------|------------|
| n=15 recency (old) | 0.292 | — |
| n=30 + BM25 rank | **0.431** | **+0.139 (+47.6%)** |
| + Deep grep | 0.431 | +0.000 |
| + Semantic | 0.431 | +0.000 |

**주요 쿼리 개선 예시**:
- "git-memory 작동 방식": 0.333 → **1.000** (+200%)
- "downstream LLM 실험": 0.000 → **0.500** (+∞)
- "Nemotron 비교": 0.000 → **0.500** (+∞)

### 분석: Semantic/Deep Grep 기여 왜 0인가?

CTX 프로젝트 특성상 모든 커밋이 동일 도메인 → BM25가 이미 semantic 신호 포착.
Cross-domain 프로젝트에서는 semantic이 더 유효할 것으로 예상.

Deep grep이 추가 기여를 못한 이유: 0.000 케이스의 관련 커밋들이
`omc-live iter`/`live-inf iter` 패턴으로 `_OMC_ITER_RE` noise filter에 의해 차단됨:
```
"auto-index" at pos 33 = "live-inf iter 1/∞: auto-index.py VS chat-memory.py"
"external" at pos 69-74 = "live-infinite iter 5/∞: external R@5 0.5649→0.6033"
```
→ Noise filter와 정보 포함 커밋 간 트레이드오프. Future work: keyword exception.

---

## 개선 2: G2 — Same-Day Adaptive Threshold (chat-memory.py)

### 문제
- 기존: rank < -17 고정 (Youden J 최적, n=194 기준)
- 동일 세션 hit rate: **40%** (ceiling experiment)
- 원인: 당일 메시지는 FTS5 BM25 rank가 -8~-12에 분포 (어휘 누적 부족)

### 실측 증거 (2026-04-11 실시간)

당일 'BM25' 메시지 FTS5 rank:
```
rank=-8.5: 'bm25-memory.py build_docs_bm25()...'  ✓ rank<-8 통과, rank<-17 차단
rank=-8.1: [tool_use: Bash]...                     (tool_use 필터 제거)
rank=-8.0: [tool_use: Edit]...                     (tool_use 필터 제거)
```

**rank < -17: 0개** vs **rank < -8: 1개 실질 콘텐츠** 접근 가능.

### 구현: Adaptive Dual-Threshold

```python
# 주 검색: rank < -17 (Youden J 최적)
primary_rows = FTS5 query with rank < -17

# 보완 검색: 당일만 rank < -8
today_start = datetime.now(UTC).strftime("%Y-%m-%dT00:00:00")
same_day_rows = FTS5 query with rank < -8 AND timestamp >= today_start
rows = primary_rows + [r for r in same_day_rows if r not in primary_rows]
```

**설계 원칙**: Global FP는 -17 유지 (과도한 노이즈 방지), 당일만 선택적 완화.

### 예상 개선
- 당일 hit rate: 40% → ~70% (FP는 당일 범위로 제한)

---

## 개선 3: n=15 → n=30 Window Expansion

```python
# 변경 전
decisions, work = get_git_decisions(project_dir, n=15)

# 변경 후  
_g1_keywords = extract_keywords(prompt) if prompt else None
decisions, work = get_git_decisions(project_dir, n=30, prompt_keywords=_g1_keywords)
```

**효과**: 커밋 16-30 범위 추가 커버 → CTX 기준 15개 커밋 추가 접근.

---

## Latency Profile

| 컴포넌트 | 기존 | 이후 |
|---------|------|------|
| git log (n) | ~5ms (n=15) | ~8ms (n=30) |
| BM25 rerank | — | ~2ms (30 candidates) |
| Deep grep | — | ~9ms (3 keywords × git grep) |
| Semantic (vec-daemon) | — | ~60ms (7 embeddings, warm) |
| **Total** | **~10ms** | **~79ms** |

UserPromptSubmit 허용 threshold ~200ms 대비 여유 있음.

---

## 구조적 한계 (향후 과제)

1. **Noise-filter/information tradeoff**: omc-live iter 커밋에 핵심 결정 포함
   → keyword exception 리스트 추가 고려
2. **Semantic on cross-domain**: CTX에서 marginal하지만 다른 프로젝트에서 검증 필요
3. **G2 vocabulary sparsity**: 세션 초반 메시지는 여전히 약함
   → session-aware normalization (future work)

---

## 성과 요약

| 지표 | 이전 | 이후 | 개선 |
|------|------|------|------|
| G1 Recall@7 (12 queries) | 0.292 | **0.431** | **+47.6%** |
| G2 same-day accessible (BM25 keyword) | 0개 | 1개 | **접근 가능** |
| G1 훅 검색 창 | 15 commits | 30 commits | **2× 확장** |
| G1 훅 latency | ~10ms | ~79ms | +69ms (허용범위) |

**코드 변경 파일**: `~/.claude/hooks/git-memory.py`, `~/.claude/hooks/chat-memory.py`
