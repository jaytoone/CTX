# CTX Hook 개선 세션 Before/After 성과 리포트

**날짜**: 2026-03-29
**측정 도구**: `tests/benchmark_before_after.py`
**테스트 케이스**: 40개 (한국어 modify×10, create×8, read×5 / 영어 12 / 혼합 3 / FP 방지 7)

---

## Executive Summary

이번 세션에서 CTX 훅의 4가지 핵심 개선을 완료했다.
정량 측정 결과 classify_intent **전체 정확도 85% → 100%**, FP율 **85.7% → 0%** 달성.
TP율 100% 유지. 지연시간 오버헤드 +1.06 μs (무시 가능).

---

## 변경사항 목록

| # | 변경 항목 | 파일 | 효과 |
|---|-----------|------|------|
| 1 | `ctx_loader.py` 유물 제거 | `~/.claude/hooks/` | 불필요한 인라인 CTX 재구현 삭제 |
| 2 | Korean intent regex 앵커링 | `src/trigger/trigger_classifier.py` | FP 6/7 → 0/7 수정 |
| 3 | 훅 intent 판단 LLM 위임 | `~/.claude/hooks/ctx_real_loader.py` | 키워드 기반 CAUTION/REFERENCE 헤더 제거 |
| 4 | Session cwd 필터링 | `~/.claude/hooks/ctx_real_loader.py` | 타 프로젝트 파일 bleeding 방지 |

---

## 정량 측정 결과

### 1. classify_intent 정확도

| 지표 | Before | After | Delta |
|------|--------|-------|-------|
| 전체 정확도 | 85.0% (34/40) | **100.0% (40/40)** | **+15.0pp** |
| FP율 (명사 컨텍스트 7케이스) | 85.7% (6/7) | **0.0% (0/7)** | **−85.7pp** |
| TP율 (실제 intent 33케이스) | 100.0% (33/33) | **100.0% (33/33)** | **±0pp (유지)** |

### 2. 카테고리별 정확도

| 카테고리 | Before | After | 케이스 수 |
|----------|--------|-------|-----------|
| `ko_modify` | 100% | 100% | 10 |
| `ko_create` | 100% | 100% | 8 |
| `ko_read` | 100% | 100% | 5 |
| `en_modify` | 100% | 100% | 3 |
| `en_create` | 100% | 100% | 2 |
| `en_read` | 100% | 100% | 2 |
| `mixed` | 100% | 100% | 3 |
| **`fp_prevent`** | **14.3%** | **100%** | **7** |

### 3. FP Before 케이스 (수정된 6개 오탐)

| 입력 | Before 예측 | 정답 | 원인 |
|------|------------|------|------|
| `추가 설명해줘` | create | read | `추가` 명사 (additional) |
| `추가로 어떻게 동작해?` | create | read | `추가로` 부사 |
| `수정 없이 그냥 실행해` | modify | read | `수정` 명사 (without modification) |
| `만들어진 과정 설명해줘` | create | read | `만들어진` 수동태 (was made) |
| `생성 시점이 언제야?` | create | read | `생성` 명사 (creation time) |
| `삭제된 이유가 뭐야?` | modify | read | `삭제된` 과거수동 (was deleted) |

*(7번째 `새로운 기능이 뭔지 알려줘` → Before에서도 read 정상 분류)*

### 4. 지연시간

| 구현 | μs/call | 비고 |
|------|---------|------|
| Before (frozenset) | 1.51 μs | 단순 in 연산 |
| After (regex) | 2.58 μs | 컴파일된 re.search |
| 오버헤드 | +1.06 μs | **+70% 증가, 절대값 무시 가능** |

> 실제 훅 P99 지연시간 = CTX 인덱싱 ~2.8ms. classify_intent 오버헤드 1μs = 전체의 0.04%.

---

## 개선 상세

### Change 2: Korean Intent Regex 앵커링

**Before**: 한국어 키워드를 frozenset에 직접 포함. `수정`, `추가` 등이 명사로 쓰인 경우에도 매칭됨.

```python
# Before — 문제: 명사/동사 동형어 구분 불가
_MODIFY_KEYWORDS = frozenset({"수정", "변경", "개선", "삭제", ...})
if any(kw in prompt_lower for kw in self._MODIFY_KEYWORDS):
    return "modify"
```

**After**: 한국어는 동사어미(해줘/하다/할/했 등)와 함께 쓰인 경우에만 매칭. 문말 생략형 명령문도 처리.

```python
# After — 동사어미 앵커링
_KO_MODIFY_RE = re.compile(
    r'(?:수정|변경|개선|삭제|제거|이동|교체|수리|패치|리팩토링|리팩터)'
    + r'(?:\s*)(?:해줘|해주|해야|해봐|합니다|할게|해라|하자|하면|해서|해도|하고|하다|할|했|해)'
    + r'|(?:수정|변경|개선|삭제|제거|이동|교체|수리|패치|리팩토링)\s*$'  # EOS 생략형
    + r'|고쳐|고치(?:다|고|면|어|세요)'
    + r'|바꿔|바꾸(?:다|고|면|어|세요)'
)
```

핵심 설계 결정:
- **동사어미 앵커링**: `수정해줘` ✓ vs `수정 없이` ✗
- **문말 생략형**: `retrieve 함수 수정` → `$` 앵커로 명령형 포착
- **부정 lookahead**: `만들어(?!진|졌)` — `만들어줘` ✓ vs `만들어진` ✗

### Change 3: Intent 판단 LLM 위임

**Before**: 훅이 `classify_intent()` 호출 후 CAUTION/REFERENCE 헤더를 주입.

```
[CTX intent=modify CAUTION: Claude Code will OVER-ANCHOR context as targets]
Code files (3/12 total):
...
```

**After**: Intent 판단을 Claude 자체에 위임. 훅은 trigger 정보만 출력.

```
[CTX] Trigger: EXPLICIT_SYMBOL | Query: retrieve | Confidence: 0.70 | Intent: judge from prompt
Code files (3/12 total):
...
(Use the prompt intent to decide how to treat this context.)
```

**근거**: Claude는 컨텍스트 파일 + 전체 사용자 프롬프트를 동시에 보므로 regex보다 정확하게 intent를 판단 가능. 키워드 기반 FP 6/7이 이 방식으로 자동 회피됨.

### Change 4: Session Bleeding 수정

**Before**: `_load_session_files()` 가 모든 세션 파일을 반환 → 타 프로젝트 파일이 컨텍스트에 주입됨.

**After**: `cwd` 파라미터 추가, `session.get("cwd", "") != cwd` 필터링.

```python
# cwd 필터: 현재 프로젝트 세션만 포함
if cwd and session.get("cwd", "") != cwd:
    continue
```

---

## 결론

| 목표 | 달성 여부 |
|------|-----------|
| FP율 감소 (명사 컨텍스트 오탐) | ✅ 85.7% → 0.0% |
| TP율 유지 | ✅ 100% 유지 |
| 전체 정확도 향상 | ✅ +15.0pp (85% → 100%) |
| 지연시간 허용 범위 | ✅ +1.06μs (전체의 0.04%) |
| Session bleeding 수정 | ✅ cwd 필터 적용 |
| LLM 위임 적용 | ✅ 키워드 헤더 제거 완료 |

이번 세션 모든 개선 목표 달성. 40개 테스트 전량 통과.
