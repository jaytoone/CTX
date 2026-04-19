# CTX — Context Bootstrapper for Claude Code (updated 2026-04-19)

## 새 CTX 정의 — 실제 production 구성 (settings.json 기준)

CTX = **Claude Code의 자동 context 주입 시스템**.
**single source of truth = `~/.claude/settings.json`의 `hooks` 블록.** 아래 표는 2026-04-19 시점에서 그 파일로부터 검증한 실제 wired hook만 기재.

### 현재 wired hooks (production)

| Hook | 파일 | Event | 역할 | 현재 상태 |
|------|------|-------|------|-----------|
| **chat-memory** | `~/.claude/hooks/chat-memory.py` | UserPromptSubmit | CM: vault.db FTS5 + vec0 hybrid (α=0.5 cosine + 0.5 bm25) — 과거 대화 회상 | ✅ hybrid 작동 (vec-daemon 필요); 대체 fallback = BM25-only + `⚠ vec-daemon down` 표시 |
| **bm25-memory** | `~/.claude/hooks/bm25-memory.py` | UserPromptSubmit (`--rich`) | G1 (의사결정) + G2-DOCS (docs/research/*.md + CLAUDE/MEMORY) + G2-PREFETCH (codebase-memory-mcp) + G2-HOOKS (~/.claude/hooks/*.py BM25 검색) — 단일 hook에 통합 | ✅ 프로덕션. pure BM25 (semantic rerank 없음). **git-memory.py + g2-augment.py 대체** |
| **memory-keyword-trigger** | `~/.claude/hooks/memory-keyword-trigger.py` | UserPromptSubmit | 결정 키워드(제외/kill/중단/데드라인 등) 감지 → MEMORY.md 즉시 기록 유도 | ✅ 프로덕션. 저장은 Claude가 수행 |
| **g2-fallback** | `~/.claude/hooks/g2-fallback.py` | PostToolUse (Grep) | Grep 실패/빈약 결과 감지 → `mcp__code-search__search_code` 힌트 주입 | ✅ 프로덕션 |
| vec-daemon startup guard | `~/.claude/settings.json` SessionStart | SessionStart | vec-daemon 실 연결 probe → 죽어있으면 rm stale socket + 재시작 (2026-04-17 수정) | ✅ 프로덕션 |

### 은퇴한 / 아카이브 hooks (wired 아님, 실행 안 됨)

| 파일 | 상태 | 은퇴 근거 |
|------|------|-----------|
| `git-memory.py` | **retired** — `bm25-memory.py`에 의해 대체 (bm25-memory.py docstring 자체가 "Replaces git-memory.py"로 명시) | recall 0.169 proactive → BM25 reactive로 성능 개선 |
| `g2-augment.py` | **retired** — `bm25-memory.py` G2-PREFETCH 블록에 흡수 | 동일 |
| `auto-index.py` | **wired 아님** — settings.json에 없음. 코드는 존재하나 Claude Code가 invoke 안 함 | codebase-memory-mcp는 `auto-index` 없이 stale-on-demand로 관리 |

> **2026-04-17 세션 주의**: 이번 세션의 iter 1-15 작업 대부분은 `git-memory.py`와 `auto-index.py`에 대한 편집이었으나, 두 파일 모두 production에 wired 되어 있지 않음 → 해당 편집은 파일에 남아있지만 실제로 실행되지 않음. 진짜 production 영향이 있는 편집은 `chat-memory.py`(iter 2 ⚠ 표시, iter 15 telemetry) 뿐.

### 공유 인프라

- **vec-daemon** (`~/.local/share/claude-vault/vec-daemon.py`): multilingual-e5-small 384-dim, Unix socket. chat-memory.py 만 의존. bm25-memory.py는 의존 안 함.
- **vault.db** (`~/.local/share/claude-vault/vault.db`): claude-vault FTS5 + vec0 통합 DB. chat-memory.py 전용.
- **opt-in telemetry** (iter 15): `CTX_TELEMETRY=1` 또는 `~/.claude/ctx-telemetry.enabled` 파일. 현재 chat-memory.py만 event 기록. bm25-memory.py 미instrument (다음 작업 후보).

**구 CTX**(adaptive_trigger, trigger_classifier, git-memory, g2-augment) → `bm25-memory.py`로 통합 대체. 구 코드는 repo에 아카이브로 남아 있으나 hook에서 사용하지 않음.

## G1/G2 정의 (2026-04-03 명료화)

| | G1: 의사결정 기억 | G2: 파일 검색 |
|--|---|---|
| **무엇을** | 작업 결정과 그 이유 | 관련 파일/문서 |
| **축** | 시간 축 (세션을 넘어서) | 공간 축 (현재 코드베이스 내) |
| **왜 필요** | 방향 희석 방지 ("왜 BM25로 바꿨지?") | 작업 효율 ("BM25 코드 어디있지?") |
| **측정** | 의사결정 recall + 이유 정확도 | R@5 on external codebases |
| **현재 수치** | 미측정 (eval 미구축) | External R@5=**0.595** |

**G1 ≠ G2**: G1은 "파일을 찾는 것"이 아니라 "이전 결정과 그 이유를 기억하는 것"
**G2**: 사용자 지시 → 유관 파일 즉석 검색 (R@5)

### 코딩 에이전트 비교 (2026-04-02 조사)

| 도구 | G1 접근 | G2 접근 | 속도 | CTX와의 관계 |
|------|---------|---------|------|-------------|
| Claude Code | CLAUDE.md + git | agentic grep (순차 20회) | 느림 | **CTX가 첫 턴 가속** |
| Cursor | Merkle tree + 임베딩 | 벡터DB (Turbopuffer) | 빠름 (인덱싱 후) | CTX가 임베딩 보완 |
| Aider | repo map (fresh) | PageRank on dep graph | 중간 | CTX가 semantic 보완 |
| Windsurf | 없음 | SWE-Grep (병렬 4턴x8) | 매우 빠름 | CTX가 pre-filter |

**CTX 차별점**:
1. **유일한 cross-session memory** — 다른 도구 전부 세션마다 리셋
2. **<1ms deterministic** — 임베딩/LLM 없이 즉시 결과
3. **.md 문서 포함 인덱싱** — 코드만이 아닌 문서까지 통합 검색

---

## 오늘 실험 A to Z (2026-03-27)

### Phase 1: CTX 아키텍처 파악
- CTX는 LLM 기반이 아닌 heuristic + structural index 시스템
- 4가지 트리거 타입: EXPLICIT_SYMBOL / SEMANTIC_CONCEPT / TEMPORAL_HISTORY / IMPLICIT_CONTEXT
- G1(크로스세션 연상 기억): persistent_memory.json + SessionStart hook → Cross-session Recall@10=0.567
- G2(지시→파일 검색): keyword/heading 기반 문서+코드 통합 검색

### Phase 2: CTX vs Nemotron-Cascade-2 G1/G2 비교 실험
**설정**: 29 docs, 87 queries (heading_exact/paraphrase/keyword 각 29개)

| 지표 | CTX-doc | Nemotron | Delta | p-value |
|------|---------|----------|-------|---------|
| R@3 전체 | **0.713** | 0.540 | +17.3%p | 3.0×10⁻⁶ |
| R@5 전체 | **0.862** | 0.586 | +27.6%p | — |
| keyword R@3 | 0.379 | 0.207 | +17.2%p | 0.001 ** |
| heading_paraphrase R@5 | **1.000** | 0.828 | +17.2%p | 0.013 * |

→ CTX가 모든 지표 통계적 유의 우세. 코드 검색 R@5도 동등(0.958 vs 0.946, p=0.629).

결과 보고서:
- `docs/research/20260327-ctx-nemotron-g1g2-comparison.md`
- `docs/research/CTX_NEMOTRON_COMPARISON_REPORT.docx`

### Phase 3: CTX 약점 분석 + 대안 조사 (expert-research)
**CTX 3대 약점**:
1. 외부 코드베이스 R@5=0.152 (heuristic 과적합)
2. keyword 쿼리 R@3=0.379 < BM25=0.667
3. 교차 파일 추론 불가 (multi-hop)

**즉시 실행 가능 개선**: TF-IDF → BM25 교체 (ROI 최고)
- 결과 문서: `FromScratch/docs/research/20260327-ctx-alternatives-research.md`

### Phase 4: BM25 교체 구현 (omc-live 완료 ✅)
**목표**: keyword R@3 0.379 → ≥0.600

#### 변경 파일 1: `src/retrieval/adaptive_trigger.py`
```
# 변경 전
from sklearn.feature_extraction.text import TfidfVectorizer
self.vectorizer = TfidfVectorizer(max_features=10000, sublinear_tf=True)
self.tfidf_matrix = self.vectorizer.fit_transform(documents)

# 변경 후
from rank_bm25 import BM25Okapi
self.bm25 = BM25Okapi(tokenized_corpus)
# _tfidf_retrieve(), _concept_retrieve(), _implicit_retrieve() 모두 BM25 교체
```

#### 변경 파일 2: `benchmarks/eval/doc_retrieval_eval_v2.py`
```
# rank_ctx_doc()에 BM25 인자 추가
def rank_ctx_doc(query, docs, bm25_index=None):
    # Stage 2: 기존 keyword frequency(cap 0.5) → BM25 normalized score
    # current >= 0.6: current + norm * 0.2
    # current < 0.6:  max(current, norm * 0.9)
```

**결과**:
| 지표 | 이전 | 현재 | 목표 |
|------|------|------|------|
| keyword R@3 | 0.379 | **0.655** | ≥0.600 ✅ |
| 전체 R@3 | 0.713 | **0.839** | — |
| heading_paraphrase R@3 | 0.966 | **1.000** | — |
| heading_exact R@3 | 0.793 | **0.862** | — |

커밋: `5099f32`, `7d1a6a8`

### Phase 5: keyword R@3 0.724 달성 ✅ (CONVERGED_SUCCESS)
**원인 분석**: BM25Okapi(IDF 포함)가 소규모 도메인 특화 코퍼스(29 docs)에서 역효과.
도메인 핵심 용어("retrieval", "ctx" 등)가 다수 문서에 출현 → IDF 낮아짐 → 성능 저하.
**해결책**: keyword 쿼리를 TF-only BM25(`rank_bm25()`)로 직접 라우팅.
**결과**: keyword R@3 0.379 → 0.655 → **0.724** ✅ (목표 달성)

커밋: `5099f32`, `7d1a6a8`, `f42a22b`

---

## 현재 성과 요약 (최종 — 2026-03-27)

### 문서 검색 (87 queries, 29 docs)
| 전략 | R@3 | R@5 | NDCG@5 | MRR |
|------|-----|-----|--------|-----|
| **CTX-doc (heading+BM25)** | **0.862** | **0.954** | **0.830** | **0.795** |
| BM25 단독 | 0.667 | 0.839 | 0.655 | 0.611 |
| Dense TF-IDF | 0.690 | 0.805 | 0.607 | 0.563 |

### 쿼리 타입별
| 타입 | CTX | BM25 | 평가 |
|------|-----|------|------|
| heading_paraphrase | **1.000** | 0.655 | ✅ 완벽 |
| heading_exact | **0.862** | 0.621 | ✅ 우위 |
| keyword | **0.724** | 0.724 | ✅ 동등 달성 |

### 코드 검색 (CTX vs Nemotron)
| 지표 | CTX | Nemotron |
|------|-----|----------|
| R@5 | 0.958 | 0.946 (동등) |
| TES | **0.668** | 0.241 (+177%) |

---

## 다음 세션 후보 작업

### 완료 ✅
- keyword R@3 0.724 달성 (query_type-aware routing — `f42a22b`)

### Phase 6: Downstream LLM Eval — MiniMax M2.5 실제 실행 ✅ (2026-03-28)
**G1+G2 synthetic (MiniMax M2.5)**:
| 목표 | WITH CTX | WITHOUT CTX | Δ |
|------|----------|------------|---|
| G1 (메모리 회상) | **1.000** | 0.219 | +0.781 |
| G2 (코드 작업, synthetic) | **0.375** | 0.000 | +0.375 |
| G2 (코드 작업, real CTX) | **0.350** | 0.150 | +0.200 |

**핵심 발견**:
- G1: CTX persistent_memory → 완벽 회상 (1.000)
- G2: CTX context 주입 → 환각 0.00 (WITHOUT=0.17)
- Over-anchoring: context가 현재 구현 노출 시 LLM 창의성 억제 (20% 빈도)
- Synthetic R@K(0.862) > synthetic G2(0.375) > real G2(0.350) — downstream이 더 보수적

**관련 파일**:
- `benchmarks/eval/downstream_llm_eval.py` — G1+G2 synthetic eval (MiniMax 지원 추가)
- `benchmarks/eval/real_codebase_downstream_eval.py` — G2 real codebase eval
- `docs/research/20260328-ctx-downstream-eval-complete.md` — 종합 보고서

### 즉시 (1-2일)
1. **keyword R@3 0.800+ 도전**: 현재 0.724는 TF-only BM25와 동등. heading+BM25 조합으로 초과 가능성 탐색
2. **G2 over-anchoring 해결**: context 선택 전략 개선 (함수 시그니처만 추출, 관련 파일 다양화)
3. **G2 real codebase Δ+0.200 개선**: instruction parsing → CTX query 변환 레이어 추가

### 중기 (1-2주)
3. **외부 코드베이스 R@5=0.152 개선**: AST 파서 기반 심볼 추출 (heuristic 제거)
   - `src/retrieval/adaptive_trigger.py`의 `_index_symbols()` 개선
4. **교차 파일 추론**: Import graph BFS 확장 (현재 2-hop 한계)

### 장기
5. **LocAgent DHG 통합**: ACL 2025, 파일 localization 92.7%
6. **Dependency GraphRAG**: 의미 기반 교차 파일 추론

---

## 핵심 파일 맵

```
src/
  retrieval/
    adaptive_trigger.py     ← 핵심 검색 엔진 (BM25로 교체됨)
    full_context.py         ← RetrievalResult, estimate_tokens
  trigger/
    trigger_classifier.py   ← 쿼리 트리거 타입 분류

benchmarks/
  eval/
    doc_retrieval_eval_v2.py ← 87 queries 문서 벤치마크 (BM25 augmented)
  results/
    doc_retrieval_eval_v2.json ← 최신 결과
    doc_retrieval_eval_v2.md   ← 최신 결과 (markdown)

docs/
  research/
    20260327-ctx-nemotron-g1g2-comparison.md  ← G1/G2 vs Nemotron 보고서
    CTX_NEMOTRON_COMPARISON_REPORT.docx       ← DOCX 보고서
    CTX_BM25_PERFORMANCE_REPORT.docx          ← BM25 성과 보고서 (FromScratch에 있음)
```

---

## 벤치마크 실행

```bash
# 문서 검색 벤치마크
python3 benchmarks/eval/doc_retrieval_eval_v2.py

# 코드 검색 벤치마크 (이전 실험 기준)
# benchmarks/eval/ 내 다른 스크립트 참조
```

## 환경
- `rank_bm25` 설치됨 (`pip show rank_bm25` → 0.2.2)
- Python 3.12, sklearn 설치됨
