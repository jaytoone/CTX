# CTX 논문 수준 갭 분석 보고서 (v2 — 수정본)

**Date**: 2026-03-29 (수정: 집계 리포트 버그 발견 후 재분석)
**Goal**: CTX 실험 환경이 학술 논문(ICSE/FSE/EMNLP급) 주장 수준인지 진단
**Verdict**: ⚠️ **Workshop/Short Paper 가능 수준 — 보완 시 Full Paper 목표 가능**

---

## ⚠️ 데이터 수정 노트

초기 분석(v1)은 `aggregated_stat_report.md`를 기반으로 작성됐으나,
**해당 파일의 CTX/BM25 수치가 실제 stat test JSON과 불일치**하는 것을 발견.

| 소스 | Flask CTX R@5 | Flask BM25 R@5 |
|------|--------------|----------------|
| aggregated_stat_report.md | 0.1447 | 0.3445 (CTX 패배로 오인) |
| statistical_tests_real_eval_flask.json | **0.4890** | **0.2769** (CTX 승리) |

**결론**: aggregated_stat_report.md의 real codebase 수치는 신뢰 불가.
원본 stat test JSON 파일을 정본(ground truth)으로 사용.

---

## 1. 실제 CTX 성능 (수정된 수치)

### Code Retrieval R@5: CTX vs BM25

| 데이터셋 | CTX R@5 | BM25 R@5 | CTX Δ | p-value | 유의성 |
|---------|---------|---------|-------|---------|--------|
| Synthetic (CTSB-small, 166q) | 0.874 | 0.982 | -0.108 | <0.001 | CTX < BM25 |
| Flask (79 files, 87q) | **0.489** | 0.277 | **+0.212** | 0.000230 | CTX > BM25 ✓ |
| FastAPI (928 files, 88q) | **0.285** | 0.153 | **+0.132** | 0.000061 | CTX > BM25 ✓ |
| Requests (35 files, 85q) | **0.598** | 0.428 | **+0.170** | 0.003095 | CTX > BM25 ✓ |

**핵심 발견**: CTX는 3개 실제 코드베이스 모두에서 BM25를 유의미하게 초월 (p<0.01).
Synthetic에서는 BM25에 뒤지나, real codebases에서 큰 마진으로 역전.

### Downstream LLM Quality

| 모델 | G1 Δ (세션 기억) | G2 Δ (CTX-unique, v?) | 벤치마크 버전 |
|------|----------------|----------------------|------------|
| MiniMax M2.5 | +0.781 | +0.375 | **v2** (일반 Python 지식 포함) |
| Nemotron-Cascade-2 | +1.000 | +0.667 | **v3** (부분 교정) |
| Claude Sonnet 4.6 | +1.000 | +1.000 | **v4** (완전 교정) |

### Latency
- P99 = 2.8ms (307-file codebase) — LLM-free, 178× SOYA margin

---

## 2. 치명적 갭 (Fatal — 즉시 해결 필요)

### FAT-1: G2 벤치마크 버전 불일치 — 모델 간 비교 무효 ⚠️

3개 모델이 서로 다른 G2 벤치마크 버전 사용 → **cross-model comparison 테이블 게재 불가**

**해결책**: 모든 모델을 G2 v4로 재실행 (MiniMax API + Nemotron NIPA)

---

## 3. 주요 갭 (Major — 논문 주장 약화)

### MAJ-1: 단일 언어 (Python only)

- 현재: Python 전용 (CTSB-small + Flask/FastAPI/Requests = Python 100%)
- ICSE/FSE 요구: 최소 3개 언어
- CTX trigger 패턴이 TypeScript/Java에서도 동작하는지 미검증

### MAJ-2: 데이터셋 크기

| 항목 | 현재 | Top-tier 권장 |
|------|------|--------------|
| Synthetic 쿼리 | 166 | 500+ |
| Real 코드베이스 | 3 (BM25 비교 가능) | 10+ |
| 독립 테스트셋 | 없음 (train=test) | 필수 |

### MAJ-3: Dense Retrieval Baseline 부재

- 비교 대상: BM25만 (sparse)
- Missing: DPR, ColBERT, UniXcoder (dense)
- Top-tier 요구: neural baseline 최소 1개

### MAJ-4: G2 Downstream Eval 자동화 한계

- 현재: keyword matching 기반 채점 (check_keywords in answer)
- 한계: partial correct, paraphrase miss
- 개선: LLM-as-judge 또는 structured output parsing

---

## 4. 경미한 갭 (Minor — 보완 가능)

| 갭 | 설명 | 난이도 |
|----|------|-------|
| MIN-1 | Bootstrap CI 없음 (G2 downstream) | 쉬움 |
| MIN-2 | Internal codebases BM25 비교 부재 (AgentNode/GraphPrompt/OneViral) | 중간 |
| MIN-3 | 재현성: 다중 실행, 시드 고정 | 쉬움 |
| MIN-4 | G1 "WITHOUT" 조건이 너무 극단적 (파일명 전혀 없음 vs BM25-based recall) | 중간 |

---

## 5. 논문 제출 가능성 평가 (수정)

| 목표 벤치 | 가능성 | 조건 |
|----------|--------|------|
| ICSE / FSE / EMNLP (A*) | ⚠️ 조건부 | MAJ-1(3언어)+MAJ-2(500q)+MAJ-3(dense) 필요 |
| ASE / ISSTA (A) | ✅ 가능 | FAT-1 수정 + MAJ-3(dense) 추가 |
| ICSE NIER (Short) | ✅ 즉시 가능 | FAT-1 수정만으로 충분 |
| arXiv / Workshop | ✅ 즉시 가능 | 현재 상태도 게재 가능 |

**핵심 근거**:
- Real codebase CTX > BM25 (3/3, p<0.01): 강한 핵심 주장
- G1 Δ=+0.78~+1.00 (3개 모델): 일관된 session recall 기여
- Latency P99=2.8ms: 실용적 배포 가능성
- **약점**: G2 비교 무효(FAT-1), 단일 언어, 소규모 데이터셋

---

## 6. 우선순위 수정 계획

### Phase 1 (즉시 — 이번 세션)

**P1-A: FAT-1 해결 — G2 v4 통일 평가 스크립트 작성**
- 모든 모델이 동일 G2 v4 시나리오로 평가되는 unified eval script
- MiniMax API (shared.env) + Nemotron NIPA port 8010 지원
- 예상 결과: MiniMax/Nemotron G2 v4 WITHOUT→0, WITH=?

**P1-B: aggregated_stat_report.md 데이터 신뢰성 수정**
- 각 stat test JSON을 직접 읽어 집계 재계산
- 정확한 CTX vs BM25 테이블 생성

### Phase 2 (1주일 — NIER/Workshop 목표)

**P2-A: Internal codebases BM25 비교 추가**
- AgentNode/GraphPrompt/OneViral에 BM25 baseline 실행
- 현재 3 external만 비교 가능

**P2-B: 논문 Section 5 (Results) 수치 업데이트**
- aggregated 수치를 정확한 stat test 기반으로 교체
- Table 2/3 수정

### Phase 3 (2-4주일 — Full Paper 목표)

- TypeScript/Java 언어 추가 (500+ queries)
- Dense retrieval baseline (UniXcoder or CodeBERT)
- 독립 테스트셋 구성

---

## 7. 결론 (수정)

**핵심 수정**: CTX는 real codebases에서 BM25를 모두 이기는 것으로 확인됨. 초기 "FAT-1" 분석은 aggregated_stat_report.md의 버그에 기반한 오류.

**실제 현황**:
- 검색 성능: 실제 코드베이스에서 CTX > BM25 ✓
- 세션 기억: 모든 모델 G1 Δ=+0.78~+1.00 ✓
- 지연시간: P99=2.8ms ✓
- **주요 미해결**: G2 모델 비교 무효(FAT-1), 단일 언어, 소규모 데이터

**제출 전략**: Phase 1 완료 후 ICSE NIER 또는 ML4Code workshop 목표. 실험 데이터 보완 후 ASE full paper 목표.

---

*Generated: 2026-03-29 v2 | Corrected after discovering aggregated_stat_report.md data bug*
