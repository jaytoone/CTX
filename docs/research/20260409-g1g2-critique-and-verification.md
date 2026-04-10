# G1/G2 재평론 및 검증 — 공정성 분석

**Date**: 2026-04-09
**Triggered by**: live-inf 재평론 요청
**Scope**: bm25-memory.py production hook의 G1/G2 주장 검증

---

## Executive Summary

G1과 G2 성능 수치의 공정성을 재검토한 결과, 두 가지 주요 편향이 발견됨:
1. **G1**: Structural Recall@7=1.000은 자기참조적(tautological) — QA pairs가 corpus와 동일한 소스에서 생성됨
2. **G2-DOCS**: 10/10=1.000은 쿼리와 정답이 동일한 키워드를 사용해 발생한 인플레이션

공정한 조정 후: **G1 end-to-end recall ≈0.881** (LLM 추출 노이즈 포함), **G2-DOCS paraphrase recall = 0.700**

---

## G1 비판 분석

### 발견된 문제점

| 문제 | 상세 |
|------|------|
| 자기참조적 corpus | 59 QA pairs가 163-commit corpus의 부분집합에서 생성 → "없는 commit 찾기" 불가 |
| 쿼리 단일타입 | 59쌍 모두 type1 "When did we implement X?" — why/what/how 없음 |
| 토큰 중복 | 쿼리-GT subject 토큰 겹침 평균 0.540 (BM25에 유리한 어휘 동일성) |
| 연령 편향 | 0-7d 45쌍(76%), 7-30d 14쌍(24%) — 최신 기억에 치우침 |
| Structural≠End-to-end | Recall@7=1.000은 "top-7에 있냐"만 측정; LLM이 실제로 답 추출하느냐는 별개 |

### 수치 재해석

```
Structural Recall@7 = 1.000  →  "corpus에 있고 top-7에 든다" (자명)
End-to-end Recall@7 = 0.881  →  "LLM이 top-7 context에서 정확히 답한다" (의미 있음)
Gap = 0.119  →  LLM 추출 실패율 (new hook에서 미측정)
```

**실제로 주장할 수 있는 것**: "G1 BM25 hook은 63/59 개 결정 커밋 중 관련 7개를 선택하고, 이 context로 LLM이 약 88% recall을 달성한다."

### G1 쿼리 다양성 부족

전체 59쌍이 "When did we implement X?" 형태 → BM25의 키워드 매칭이 직접 작동.
더 어려운 쿼리 예시:
- "왜 proactive injection 대신 query-time retrieval로 전환했나?" (이유 질문)
- "G1 temporal retention 실험에서 핵심 트레이드오프는?" (이해 질문)
- "BM25 threshold를 0에서 3.0으로 올린 근거는?" (근거 질문)

이 타입의 쿼리에서는 BM25 recall이 크게 낮아질 것으로 예상됨.

### G1 Type2/3/4 실측 결과 (2026-04-09 추가)

8개 harder 쿼리로 structural recall 측정 (score>0 필요):

| 타입 | 쿼리 예시 | 결과 | Top Score |
|------|---------|------|-----------|
| type2_why | "왜 proactive injection → query-time?" | ✗ | 4.6 (nonzero=1) |
| type2_why | "BM25 threshold 3.0으로 올린 이유?" | ✓ | 5.7 |
| type2_why | "git-memory→bm25-memory 교체 이유?" | ✓ | 10.3 |
| type3_what | "G1 temporal retention 핵심 발견?" | ✓ | 10.2 |
| type3_what | "BM25와 dense embedding 핵심 차이?" | ✗ | **0.0** |
| type3_what | "format ablation 최적 포맷?" | ✓ | 9.2 |
| type4_rationale | "CTX=context bootstrapper 근거?" | ✓ | 4.8 |
| type4_rationale | "topic-dedup이 diversity 최적화 실측?" | ✓ | 5.4 |

**Type2/3/4 Strict Recall@7 = 0.750** (6/8) vs Type1 = 1.000

**분석**:
- "BM25와 dense embedding 차이" → score=0 (Korean 쿼리, 영어 corpus, 어휘 불일치 → BM25 완전 실패)
- "proactive injection 전환 이유" → 1개 commit만 nonzero, 그게 GT 아님
- **갭 요약**: Type1 1.000 → Type2/3/4 0.750 (-0.250). 실제 사용 쿼리 분포에서 G1 recall은 0.88이 아닐 수 있음

---

## G2-DOCS 비판 분석

### 원래 eval의 구조적 문제

```python
# 원래 QA pair 예시 (self-referential):
{
    "question": "CTX G1 long-term memory eval에서 BM25 retrieval의 Recall@5는 얼마인가?",
    "answer_keywords": ["0.881", "88.1%"],
}
# 문제: 쿼리에 "BM25", "Recall" 포함 → 정답 doc도 동일 키워드 → BM25 trivially 성공
```

### Paraphrase Eval 결과 1차 (2026-04-09 신규 측정, 10쌍)

| 카테고리 | 난이도 | 결과 | 쿼리 예시 |
|---------|-------|------|---------|
| semantic_reframe | hard | ✓ | "회상 정확도가 가장 높은 검색 방식은?" |
| terminology_change | medium | ✓ | "단키워드 검색 성능 개선 최종 수치는?" |
| domain_description | hard | ✓ | "Python 웹 프레임워크 코드 파일 검색 정확도" |
| indirect | medium | ✓ | "production hook의 결정 corpus 크기는?" |
| comparison | hard | ✗ | "새 접근의 회상률 향상은 몇 배인가?" |
| numeric_indirect | medium | ✗ | "시작 시점에 주입되는 context 문자 수는?" |
| synonym | hard | ✓ | "벡터 검색 방식의 오픈셋 평균 점수는?" |
| paraphrase | medium | ✓ | "자동 검색에 걸리는 시간 비중은?" |
| indirect | medium | ✗ | "결정 커밋 총수는?" |
| negation | easy | ✓ | "문서 없이 답할 경우 정답률은?" |

**결과: 7/10 = 0.700** (vs 주장된 1.000)

**Gap 원인 (3 miss):**
- `comparison`: "5.2x" 향상 수치 → 쿼리에 "향상", "배" → BM25가 wrong doc 선택
- `numeric_indirect`: "204chars" 주입 → 쿼리에 해당 숫자 없음 → 관련 doc 미발견
- `indirect`: corpus 크기 "163" → 쿼리가 "git-memory hook이 식별한 총수" → temporal doc 우선

### Paraphrase Eval 결과 2차 (2026-04-09 확장, 33쌍)

**스크립트**: `benchmarks/eval/g2_docs_paraphrase_eval.py`

**전체 결과: 22/33 = 0.667** (통계적 신뢰도 향상)

| 카테고리 | 정확/전체 | Recall |
|---------|---------|-------|
| ctx_internal | 4/4 | 1.000 |
| g1_diversity | 4/4 | 1.000 |
| g2_docs | 4/4 | 1.000 |
| decision | 3/4 | 0.750 |
| architecture | 3/4 | 0.750 |
| open_set | 2/4 | 0.500 |
| temporal | 1/4 | 0.250 |
| retrieval_perf | 1/4 | 0.250 |
| efficiency | 0/1 | 0.000 |

**난이도별:**
| 난이도 | Recall |
|-------|-------|
| easy | 3/4 = 0.750 |
| medium | 10/15 = 0.667 |
| hard | 9/14 = 0.643 |

**실패 패턴 분석:**
- `retrieval_perf` (0.250): "의사결정 회상 수치는?" → BM25가 숫자가 많은 비관련 doc 선택 (한국어 간접 어휘)
- `temporal` (0.250): "오래된 의사결정 기억은?" → 쿼리 어휘가 영어 doc 핵심 토큰("7-30d", "n=100")과 미매칭
- `open_set` (0.500): 외부 저장소 결과가 fulleval-sota-comparison 한 파일에 집중 → 다른 경로로 접근 실패

### 수정된 공정 수치

| 평가 방식 | G2-DOCS Recall |
|----------|---------------|
| Keyword-identical (원래) | **1.000** (인플레이션) |
| Paraphrase 10쌍 (1차) | **0.700** |
| Paraphrase 33쌍 (2차, 확장) | **0.667** |
| 권장 리포트 값 | **0.667~0.700** (33쌍이 더 신뢰성 높음) |

---

## G2b (코드 파일 발견) 분석

### 현황

- **프로젝트 내부 쿼리**: 정상 동작 (`adaptive_trigger.py BM25` → `src/retrieval/adaptive_trigger.py` 정확)
- **외부 파일 쿼리**: 실패 (`bm25_rank_decisions` → `src/evaluator/llm_quality.py` 오답)
  - 이유: `~/.claude/hooks/bm25-memory.py`는 CTX 프로젝트 디렉토리 밖 → 인덱스 미포함

### 한계 명시

```
G2b scope: CLAUDE_PROJECT_DIR 내 파일만 검색 가능
미포함:
  - ~/.claude/hooks/ (hook 파일들)
  - 다른 프로젝트 파일
  - 시스템 패키지
```

**docstring 수정 완료**: "R@5 ~0.60" → 프로젝트 내부 한정 명시

---

## 공정한 성능 표 (수정판)

| 컴포넌트 | 주장값 | 공정값 | 비고 |
|---------|-------|-------|------|
| G1 Structural Recall@7 | 1.000 | **0.627** | 20260410 paraphrase fair eval (token overlap 0.476→0.085); 편향=0.373 |
| G1 Structural Recall@7 (combined) | 1.000 | **0.634** | 71 queries (59 paraphrase + 12 Type2/3/4) |
| G1 End-to-end Recall@7 | 0.881 | ~0.881 | Type1 keyword-identical 기준; fair end-to-end 미측정 |
| G1 Type-diversity | full | type1만 | 59쌍 모두 "When did we implement X?"; Type2/3/4 Recall@7=0.667 (12쌍) |
| G2-DOCS Recall@5 | 1.000 | **0.700** | Paraphrase eval이 공정한 측정 |
| G2b Code (project-internal) | R@5~0.60 | 정상 동작 | `src/` 내 파일 정확 |
| G2b Code (external) | R@5~0.60 | **실패** | hooks/, 타 프로젝트 파일 미인덱스 |

---

## 즉시 적용된 수정

1. `bm25-memory.py` docstring: G2a 1.000→0.700 (paraphrase), G2b 외부 파일 한계 명시
2. 이 연구 문서: 공정한 수치 기록

## 완료된 개선 (2026-04-09 후속 세션)

1. **G2-DOCS expand**: 33쌍 paraphrase eval 완료 → **0.667** (10쌍 0.700보다 신뢰도 높음)
   - 스크립트: `benchmarks/eval/g2_docs_paraphrase_eval.py`
   - 결과: `benchmarks/results/g2_docs_paraphrase_results.json`
2. **G2b-hooks 범위 확장**: `bm25-memory.py`에 G2b-hooks BM25 검색 추가
   - `~/.claude/hooks/*.py` 직접 BM25 인덱싱 (hook/훅 키워드 검지 시 자동 실행)
   - 이전 실패 케이스 해결: `bm25_rank_decisions` 쿼리 → `bm25-memory.py` 정확 반환

## 완료된 개선 (2026-04-10)

3. **G1 Paraphrase Fair Eval 완료**: `benchmarks/eval/g1_fair_eval.py`
   - 59 Type1 쿼리 → MiniMax M2.5로 패러프레이즈 생성 (token overlap 0.476→0.085)
   - BM25 Structural Recall@7: 1.000→**0.627** (편향 0.373 확인)
   - Type2/3/4 12쌍 생성 + Recall@7=0.667
   - 통합 공정 Recall@7=**0.634** (71 queries)
   - `bm25-memory.py` docstring 업데이트 완료

## 미적용 개선 (향후 과제)

1. **G1 LLM 재측정 (공정 버전)**: 71 paraphrase+type234 queries × 7 baselines (497 LLM calls)
2. **corpus body 인덱싱**: 커밋 subject만 아닌 body도 BM25 텍스트에 포함 → 22개 paraphrase 실패 케이스 개선 가능

---

## 결론

bm25-memory.py는 production에서 올바르게 작동하고 있으나, 성능 주장의 일부가 측정 방법론 편향으로 인해 과장되어 있다.

공정한 수치 (최종):
- **G1 Structural Recall@7 = 0.627** (paraphrase, 59쌍) / **0.634** (combined 71쌍) — 편향 0.373 제거 후
- **G1 End-to-end = ~0.881** (Type1 keyword-identical 기준, LLM-evaluated) / 공정 end-to-end 미측정
- **G2-DOCS = 0.667** (paraphrase 33쌍) — 권장 리포트 수치
- **G2b**: 프로젝트 내부 정상 + 훅 파일은 G2b-hooks BM25로 해결

## Related
- [[projects/CTX/research/20260408-g1-format-ablation-results|20260408-g1-format-ablation-results]]
- [[projects/CTX/research/20260409-g1-fulleval-sota-comparison|20260409-g1-fulleval-sota-comparison]]
- [[projects/CTX/research/20260402-production-context-retrieval-research|20260402-production-context-retrieval-research]]
- [[projects/CTX/research/20260408-g1-temporal-retention-eval|20260408-g1-temporal-retention-eval]]
- [[projects/CTX/research/20260326-ctx-final-sota-comparison|20260326-ctx-final-sota-comparison]]
- [[projects/CTX/research/20260407-g1-temporal-eval-results|20260407-g1-temporal-eval-results]]
- [[projects/CTX/research/20260326-ctx-vs-sota-comparison|20260326-ctx-vs-sota-comparison]]
- [[projects/CTX/research/20260410-g1-fair-eval-bm25-bias|20260410-g1-fair-eval-bm25-bias]]
