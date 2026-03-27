# CTX Downstream LLM Evaluation — Complete Results (MiniMax M2.5)
**Date**: 2026-03-28  **Type**: Comprehensive Report  **Backend**: MiniMax M2.5

## 전체 실험 요약

CTX context 주입이 LLM 품질에 미치는 영향을 3단계 실험으로 측정.
모든 실험: MiniMax M2.5 실제 API 호출.

## 실험 매트릭스

| 실험 | 데이터 | 시나리오 수 | WITH CTX | WITHOUT CTX | Δ Delta |
|------|--------|------------|----------|------------|---------|
| G1 (기억 회상, synthetic) | 50 synthetic files | 8 | **1.000** | 0.219 | **+0.781** |
| G2 (코드 작업, synthetic) | 50 synthetic files | 6 | 0.375 | 0.000 | **+0.375** |
| G2 (코드 작업, real CTX code) | CTX src/ files | 5 | 0.350 | 0.150 | **+0.200** |

**전체 평균 Δ (across all conditions)**: +0.452

## G1 Deep Dive: Cross-Session Memory Recall

### 왜 WITH CTX = 1.000인가?

CTX가 주입하는 `persistent_memory.json` 구조:
```json
{
  "session_memory": {
    "last_modified_files": ["auth/jwt.py", "api/users.py", ...],
    "recent_tasks": ["JWT 구현", "유저 API 테스트"],
    "timestamp": "2026-03-27T..."
  }
}
```

→ LLM이 명시적인 파일명 목록을 받으면 **100% 회상** 가능.
→ WITHOUT CTX: LLM이 추측으로 0.219 달성 (일반 패턴 지식 활용)

**시사점**: CTX G1은 이미 최적화된 상태. 개선 여지 < G2.

## G2 Deep Dive: Instruction-Grounded Coding

### Synthetic vs Real Codebase 격차 원인

| 요인 | Synthetic (Δ+0.375) | Real (Δ+0.200) |
|------|---------------------|----------------|
| WITHOUT CTX baseline | 0.000 (LLM 추측 불가) | 0.150 (일반 지식으로 추측 가능) |
| WITH CTX absolute | 0.375 | 0.350 |
| Context 복잡도 | 단순 합성 파일 | 실제 CTX 코드 (복잡한 API) |
| 평가 엄격도 | 합성 함수명 매칭 | 실제 함수명 정확 매칭 |

→ Real codebase에서 gap이 줄어드는 이유: WITHOUT baseline 상승 + WITH 절대값 유지

### Over-Anchoring 현상 (실험에서 발견)

**real_g2_05**: "Fix BM25Okapi IDF penalty → switch to TF-only"
- WITH CTX (bm25_retriever.py 제공): 0.000
- WITHOUT CTX: 0.250

가설:
1. LLM이 현재 BM25Okapi 구현을 보고 "이 코드를 수정"에 집중
2. "TF-only로 전환"이라는 더 나은 해결책을 제시하지 못함
3. Context 없을 때 오히려 더 유연한 답변

**Over-Anchoring 조건**: context가 현재 (잘못된) 구현을 보여줄 때

## CTX 성능 3분류

### 타입 A: Context-완전-의존 (CTX 필수)
- G1 recall: WITHOUT=0.033→0.219 (LLM이 파일 이름 추측 불가)
- G2 synthetic: WITHOUT=0.000 (완전 환각)
- **CTX 제거 시 0 또는 근접 → CTX가 최대 가치**

### 타입 B: Context-개선 (CTX 도움)
- G2 real (대부분): Δ+0.250~+0.500
- LLM이 일반 지식으로 부분 답변 가능하지만 CTX로 더 정확해짐

### 타입 C: Context-역효과 (CTX 해로움)
- real_g2_05: Δ-0.250
- 현재 구현 노출이 LLM을 잘못 앵커링
- **빈도**: 5시나리오 중 1건(20%) — 무시할 수 없는 비율

## 실용적 CTX 개선 방향

### 단기 (현재 코드 수정 가능)

1. **Context 선택 다양성**: 단일 파일 대신 관련 파일 2-3개 제공
   - 현재: `ctx_context_file = target_file` (동일 파일)
   - 개선: target 파일 + 관련 파일 1개 추가 → over-anchoring 완화

2. **Context 요약 전처리**: 파일 전체 대신 함수 시그니처 + docstring만 추출
   - 구현 세부사항 없이 API 구조만 노출 → LLM이 유연하게 추론 가능

3. **Query-type별 context 전략**:
   ```
   instruction.startswith("Fix") → 유사 코드 사례 (다른 파일) 제공
   instruction.startswith("Implement") → 관련 인터페이스 제공
   instruction.startswith("Add") → 현재 파일 제공 (안전)
   ```

### 중기 (새 실험 필요)

4. **Instruction parsing → CTX query 변환**:
   "Replace X with Y in Z" → CTX query: `semantic_concept("X"), semantic_concept("Y")`
   (현재 CTX R@5=0.000 on instruction queries → 이 레이어 추가 시 R@5 개선 예상)

5. **Negative example context**: "이 파일은 수정하지 마세요" 형태로 wrong 파일 제외

## 핵심 메시지 (CTX 논문 contribution 후보)

```
1. CTX G1(세션 기억) = SOLVED: WITH CTX 1.000 (완벽), Δ+0.781
2. CTX G2(코드 작업) = PARTIAL: Δ+0.200~+0.375 (일관적 개선, over-anchoring 예외)
3. Over-Anchoring Risk: context가 현재 구현 노출 시 LLM 창의성 억제 (20% 빈도)
4. Synthetic-Real Gap: proxy 수치(R@3=0.862) > synthetic G2(0.375) > real G2(0.350)
   → downstream eval이 proxy보다 더 보수적인 실제 성능 측정
```

## 실험 재현

```bash
# 전체 실험 재현
MINIMAX_API_KEY=<key> MINIMAX_BASE_URL=https://api.minimax.io/anthropic MINIMAX_MODEL=MiniMax-M2.5

# G1+G2 synthetic
python3 benchmarks/eval/downstream_llm_eval.py --n-scenarios 8

# G2 real codebase
python3 benchmarks/eval/real_codebase_downstream_eval.py
```

## Related
- [[projects/CTX/research/20260328-ctx-downstream-minimax-eval|G1+G2 synthetic results]]
- [[projects/CTX/research/20260328-ctx-real-codebase-g2-eval|G2 real codebase results]]
- [[projects/CTX/research/20260327-ctx-downstream-eval|Dry-run comparison]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|Real-project self-eval]]
