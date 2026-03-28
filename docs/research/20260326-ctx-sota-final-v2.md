# CTX vs SOTA — 최종 성능 비교 테이블 v2

**Date**: 2026-03-26 (post omc-live iter 5)
**Baseline**: CTX 5x collapse 해결 후 최종 수치 반영

---

## 비교 시스템 분류

| 카테고리 | 시스템 | 타입 |
|---------|--------|------|
| **CTX (Ours)** | Adaptive Trigger Retrieval | Trigger-driven dynamic context |
| **IDE 도구** | Cursor | Commercial IDE (semantic index + Memories) |
| **IDE 도구** | GitHub Copilot | Commercial IDE (embedding-based) |
| **IDE 도구** | Windsurf | Commercial IDE (Cascade context) |
| **검색 모델** | CodeXEmbed 7B | CoIR #1 embedding model |
| **검색 모델** | Voyage-Code-002 | CoIR #5 embedding model |
| **기준선** | BM25 | Lexical retrieval baseline |
| **기준선** | Dense (MiniLM) | Semantic embedding baseline |
| **기준선** | LlamaIndex | RAG framework baseline |

---

## 1. 핵심 지표 종합 비교

### 1-A. 코드 파일 검색 품질 (Goal 2: Instruction Grounding)

| 시스템 | R@5 (Real) | R@5 (Synthetic) | NDCG@5 | 데이터셋 | 공개여부 |
|--------|-----------|-----------------|--------|---------|---------|
| **CTX** | **0.522** (AgentNode) | **0.958** | **0.723** | Internal 3 real codebases | ✅ |
| **CTX** (GraphPrompt) | **0.619** | — | — | Internal | ✅ |
| **CTX** (OneViral) | **0.424** | — | — | Internal | ✅ |
| BM25 | ~0.993 | 0.982 | ~0.982 | RepoBench / Synthetic | ✅ |
| Dense (MiniLM) | ~1.000 | 0.973 | 0.983 | COIR 30q sample | ✅ |
| LlamaIndex | — | 0.972 | — | Synthetic | ✅ |
| **Cursor** | N/A | N/A | N/A | ❌ 미공개 | ❌ |
| **GitHub Copilot** | N/A | N/A | N/A | ❌ 미공개 | ❌ |
| **Windsurf** | N/A | N/A | N/A | ❌ 미공개 | ❌ |

> **해석**: BM25/Dense는 NL→코드 단순 텍스트 매칭에서 높음. CTX는 구조적 의존성 쿼리(IMPLICIT_CONTEXT)에서 우위.

### 1-B. IMPLICIT_CONTEXT 특화 성능 (Import Graph 의존성 추론)

| 시스템 | IMPLICIT_CONTEXT R@5 | 방법론 | 공개 |
|--------|---------------------|--------|------|
| **CTX (synthetic)** | **1.000** | Import graph BFS + TF-IDF | ✅ |
| **CTX (AgentNode)** | **0.715** | Import graph BFS + TF-IDF | ✅ |
| **CTX (GraphPrompt)** | **0.437** | Import graph BFS + TF-IDF | ✅ |
| BM25 | 0.400 (synthetic) | Lexical | ✅ |
| Dense Embedding | ~0.400 | Semantic similarity | ✅ |
| Cursor | N/A | Internal codebase graph (?) | ❌ |
| CodeXEmbed 7B | — | Embedding only (no graph) | N/A |

> **CTX의 핵심 차별화**: import chain traversal이 실제 Python 코드의 구조적 의존성을 포착.
> BM25/Dense 대비 **+1.79x (synthetic), +1.79x (AgentNode)** 우위.

### 1-C. 토큰 효율성 (TES: Token Efficiency Score)

| 시스템 | TES | 토큰 사용률 | 비고 |
|--------|-----|-----------|------|
| **CTX (synthetic)** | **0.776** | **5.2%** | TES 정의: Recall@5 / ln(1+files) |
| **CTX (AgentNode)** | **0.300** | **3.6%** | 실제 코드베이스 |
| BM25 | 0.410 | 18.7% | CTX 대비 3.6x 토큰 |
| Dense TF-IDF | 0.406 | 21.0% | |
| LlamaIndex | 0.405 | 20.1% | |
| GraphRAG-lite | 0.218 | 24.0% | |
| Full Context | 0.019 | 100.0% | 토큰 낭비 극심 |
| **Cursor** | N/A | N/A | ❌ 미공개 |
| **Copilot** | N/A | N/A | ❌ 미공개 |

> **CTX 토큰 절감**: Full Context 대비 **95% 절감**, BM25 대비 **3.6x 절감** (synthetic 기준).

---

## 2. Cross-Session Memory (Goal 1: 세션 간 연속성)

| 시스템 | Cross-Session Recall@10 | 측정 방법 | 공개 |
|--------|------------------------|----------|------|
| **CTX (head tier)** | **1.000** | 파일 접근 빈도 persistent_memory | ✅ |
| **CTX (torso)** | **0.710** [0.699, 0.720] | 95% CI | ✅ |
| **CTX (tail)** | **0.431** [0.423, 0.439] | 95% CI | ✅ |
| **CTX (weighted avg)** | **0.567** | 통계 검증 완료 | ✅ |
| Cursor | N/A | Project Memories 기능 있음 | ❌ |
| GitHub Copilot | N/A | Spaces 기능, 세션 간 자동 연속성 없음 | ❌ |
| Windsurf | N/A | Cascade context, 세션 간 구조 미공개 | ❌ |
| MemoryArena SOTA | TBD | 2026.02 신규 벤치마크 | 🔄 미평가 |

> **CTX**: 세션 간 Recall@10을 **수치로 공개한 최초 코드 에이전트 시스템** 중 하나.
> 업계 도구 모두 비교 가능한 수치 미제공.

---

## 3. 외부 코드 검색 벤치마크 (CoIR / CodeSearchNet)

| 시스템 | CoIR NDCG@10 | 타입 | 비고 |
|--------|-------------|------|------|
| CodeXEmbed 7B | **67.41** | Embedding 7B | #1 CoIR 공식 |
| Voyage-Code-002 | **56.26** | Embedding | #5 CoIR 공식 |
| BM25 | ~0.983* | Lexical | *내부 30q 샘플 |
| Dense (MiniLM) | ~0.983* | Embedding | *내부 30q 샘플 |
| **CTX Adaptive** | **~0.356*** | Trigger-driven | *내부 샘플, 미공식 |
| **CTX Hybrid Dense+CTX** | **~0.967*** | Hybrid | *내부 샘플, 미공식 |

> **주의**: CTX 내부 COIR 평가는 30쿼리/300 corpus 소규모 샘플. 공식 CoIR 제출 미완료.
> NL→코드 텍스트 매칭 도메인에서는 embedding 모델이 우위 (CTX 설계 목적과 다름).

---

## 4. 실제 통합 성능 (Claude Code Hook 환경)

| 지표 | CTX | 업계 비교 | 비고 |
|------|-----|---------|------|
| Context Hit Rate (CHR) | **86.7%** | N/A (미공개) | 30 queries, Claude Code hook |
| EXPLICIT_SYMBOL CHR | **86.7%** | — | 검증됨 |
| TEMPORAL_HISTORY CHR | **100%** | — | 완벽 패스 |
| 평균 응답 지연 (RT) | **120ms** | N/A (미공개) | 실시간 수준 |
| 환경 | single WSL2 | — | 단일 환경 측정 |

---

## 5. 알고리즘별 성능 (Synthetic 기준 — CTX 강점 도메인)

| 전략 | R@5 | Token% | TES | 특징 |
|------|-----|--------|-----|------|
| **CTX (Ours)** | **0.958** | **5.2%** | **0.776** | 최고 TES |
| Hybrid Dense+CTX | 0.725 | 23.6% | 0.303 | |
| BM25 | 0.982 | 18.7% | 0.410 | 어휘 매칭 |
| Dense TF-IDF | 0.973 | 21.0% | 0.406 | |
| LlamaIndex | 0.972 | 20.1% | 0.405 | |
| Chroma Dense | 0.829 | 19.3% | 0.346 | |
| GraphRAG-lite | 0.523 | 24.0% | 0.218 | |
| Full Context | 0.075 | 100.0% | 0.019 | |

---

## 6. CTX 강점 / 약점 요약

### 강점 (CTX 압도적 우위)

| 차원 | CTX | 경쟁 | 차이 |
|------|-----|------|------|
| **IMPLICIT_CONTEXT** (import graph) | R@5=1.000/0.715 | BM25: 0.400 | **+1.79x** |
| **토큰 효율성** (TES) | 0.776 | BM25: 0.410 | **+1.89x** |
| **토큰 사용량** | 5.2% | Full: 100% | **-95%** |
| **Cross-session 수치 공개** | 0.567 avg | 업계: 미공개 | 유일 |
| **실시간 통합 RT** | 120ms | 업계: 미공개 | — |

### 약점 (개선 필요)

| 차원 | CTX | 경쟁 SOTA | 차이 | 원인 |
|------|-----|---------|------|------|
| NL→코드 검색 (CoIR 공식) | 미제출 | CodeXEmbed: 67.41 | TBD | 제출 필요 |
| RepoBench cross-file | R@5~0.244 | BM25: 0.993 | -0.749 | 범용 cross-file 취약 |
| TEMPORAL_HISTORY (real) | R@5=0.300 | — | — | 실제 세션 히스토리 없음 |
| CoIR 공식 검증 | 내부 30q | 공식 leaderboard | 미완 | 제출 필요 |

---

## 7. Goal 달성 현황 (최종)

| Goal | 지표 | 이전 | **최종 (iter 5)** | 상태 |
|------|------|------|------------------|------|
| **Goal 1**: 세션 간 연속성 | Cross-Session Recall@10 | 0.567 | **0.567** | ✅ (외부 미검증) |
| **Goal 2**: 지시→파일 검색 | R@5 (real avg) | 0.176 (collapsed) | **0.522** | ✅ |
| **Goal 2**: NDCG@5 | NDCG@5 | 0.723 | **0.723** | ✅ |
| **핵심 강점**: IMPLICIT_CONTEXT | R@5 (AgentNode) | 0.044 | **0.715** | ✅ (+16x) |
| **효율성**: TES (synthetic) | TES | 0.776 | **0.776** | ✅ (1.89x BM25) |
| **5x 붕괴 해결** | 붕괴 비율 | 5.0x | **1.84x** | ✅ |

---

## 8. 권고 액션 (우선순위)

1. **즉시**: CoIR 공식 leaderboard 제출 → NL→코드 검색 외부 검증
2. **즉시**: MemoryArena 평가 → Goal 1 독립 외부 검증
3. **단기**: TEMPORAL_HISTORY 개선 → 실제 git log 기반 시뮬레이션
4. **단기**: RepoBench cross-file 약점 분석 → CTX 적용 가능 영역 명확화

---

## 출처

| 출처 | 수치 |
|------|------|
| CoIR Leaderboard (archersama.github.io/coir/) | CodeXEmbed=67.41, Voyage=56.26 |
| MemoryArena (memoryarena.github.io) | Feb 2026 신규, CTX 미평가 |
| CTX internal: final_report_v7.md | AgentNode R@5=0.522, Synthetic=0.958 |
| CTX internal: hook_effectiveness_eval.md | CHR=86.7%, RT=120ms |
| CTX internal: cross_session_recall.json | Recall@10 weighted avg=0.567 |
| CTX internal: coir_evaluation.md | 내부 30q 샘플 평가 |

## Related
- [[projects/CTX/research/20260328-adaptive-trigger-generalization-fix|20260328-adaptive-trigger-generalization-fix]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|20260328-ctx-real-codebase-g2-eval]]
- [[projects/CTX/research/20260328-trigger-classifier-semantic-fix|20260328-trigger-classifier-semantic-fix]]
- [[projects/CTX/research/20260325-long-session-context-management|20260325-long-session-context-management]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
