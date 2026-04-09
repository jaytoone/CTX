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

### Paraphrase Eval 결과 (2026-04-09 신규 측정)

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

### 수정된 공정 수치

| 평가 방식 | G2-DOCS Recall |
|----------|---------------|
| Keyword-identical (원래) | **1.000** (인플레이션) |
| Paraphrase (fairness-adjusted) | **0.700** |
| 권장 리포트 값 | **0.700** |

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
| G1 Structural Recall@7 | 1.000 | 1.000 (자명) | QA pairs=corpus 부분집합이므로 당연 |
| G1 End-to-end Recall@7 | 0.881 | ~0.881 | LLM eval 미재실행; 구조적으로 동일 |
| G1 Type-diversity | full | type1만 | 59쌍 모두 "When did we implement X?" |
| G2-DOCS Recall@5 | 1.000 | **0.700** | Paraphrase eval이 공정한 측정 |
| G2b Code (project-internal) | R@5~0.60 | 정상 동작 | `src/` 내 파일 정확 |
| G2b Code (external) | R@5~0.60 | **실패** | hooks/, 타 프로젝트 파일 미인덱스 |

---

## 즉시 적용된 수정

1. `bm25-memory.py` docstring: G2a 1.000→0.700 (paraphrase), G2b 외부 파일 한계 명시
2. 이 연구 문서: 공정한 수치 기록

## 미적용 개선 (향후 과제)

1. **G1 쿼리 다양화**: type2 (why), type3 (what rationale) 추가 → 진짜 recall 측정
2. **G2-DOCS expand**: 30+쌍 paraphrase eval로 통계적 신뢰성 향상
3. **G2b 범위 확장**: `~/.claude/hooks/` 인덱싱 추가 (auto-index.py 범위 확장)
4. **G1 LLM 재측정**: new hook으로 59 QA pairs 재실행 (413 LLM calls 필요)

---

## 결론

bm25-memory.py는 production에서 올바르게 작동하고 있으나, 성능 주장의 일부가 측정 방법론 편향으로 인해 과장되어 있다. 공정한 수치: **G1 ≈0.881** (end-to-end, LLM-evaluated), **G2-DOCS = 0.700** (paraphrase). G2b는 프로젝트 내부 파일에서만 유효.
