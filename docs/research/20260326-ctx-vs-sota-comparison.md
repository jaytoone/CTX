# [expert-research-v2] CTX Goal 1&2 vs SOTA 성능 비교
**Date**: 2026-03-26  **Skill**: expert-research-v2

## Original Question
CTX Goal 1 (cross-session recall) and Goal 2 (instruction grounding) compared to current SOTA with numerical comparisons.

## Agent Response Summary

### Deep Analyst
- Cross-session memory: no published benchmark for Cursor/Copilot/Windsurf (HIGH)
- CTX Recall@10=0.567 competitive, CoIR top 0.65-0.80 (MEDIUM)
- CTX NDCG@5=0.723 upper quartile (MEDIUM)
- CoIR most relevant benchmark (HIGH)
- CodeXEmbed/Voyage-Code are embeddings not full systems (HIGH)

### Fact Finder
- CoIR Leaderboard: CodeXEmbed 7B #1 (67.41), Voyage-Code-002 #5 (56.26)
- Cross-session: No published metrics for Cursor/Copilot/Windsurf
- **MemoryArena (Feb 2026)**: new benchmark for multi-session memory
- CTX not evaluated on CoIR yet

### Devil's Advocate
**CRITICAL**: CTX not evaluated on CoIR — comparing internal metrics to CoIR benchmarks methodologically invalid
**CRITICAL**: MemoryArena exists but ignored — direct benchmark for multi-session, exactly what CTX Goal 1 solves
**MAJOR**: CoIR range 0.65-0.80 not sourced — scores provided (67.41, 56.26) are overall CoIR, not Recall@10

## Cross-Validation Matrix

| Topic | Analyst | Devil's Advocate | Fact Finder | Consensus |
|-------|---------|------------------|-------------|-----------|
| CoIR comparison | CTX competitive | CRITICAL: not evaluated on CoIR | No CoIR eval | **REJECT** |
| Cross-session benchmark | None exist | CRITICAL: MemoryArena exists | MemoryArena Feb 2026 | **CONTESTED** |
| CoIR top range | 0.65-0.80 | MAJOR: metric mismatch | 67.41/56.26 overall | **UNVERIFIED** |

## Final Conclusion

### 핵심 발견

| Dimension | CTX | Industry SOTA | 상태 |
|-----------|-----|--------------|------|
| **Cross-Session Recall** | Recall@10=0.567 (95% CI) | No published benchmark | 비교 불가 |
| **Instruction Grounding** | NDCG@5=0.723 | CoIR not evaluated | 비교 불가 |
| **Code Retrieval** | — | CodeXEmbed 7B: 67.41, Voyage-Code: 56.26 | CTX 미출시 |

### CRITICAL 교훈

1. **CTX는 CoIR에서 평가되지 않음** — 내부 지표(NDCG@5=0.723)를 CoIR 점수와 직접 비교하는 것은 방법론적으로 유효하지 않음

2. **MemoryArena (Feb 2026)** — 다중 세션 메모리 전용 벤치마크 등장. CTX Goal 1의 정체와 정확히 일치. 이 벤치마크에서 CTX를 평가해야 함

3. **Industry는 Cross-Session 공개 지표 없음** — Cursor/Copilot/Windsurf 모두 Cross-Session Recall에 대한 숫자 공개 없음

### 권고

1. **즉시**: CTX를 CoIR에서 평가 (NDCG@10)
2. **즉시**: CTX를 MemoryArena에서 평가
3. **단기**: Cursor/Copilot/Windsurf에 대한_proxy benchmark 설계

## Reference Sources
- https://archersama.github.io/coir/ (CoIR Leaderboard)
- https://arxiv.org/abs/2411.12644 (CodeXEmbed)
- https://memoryarena.github.io/ (MemoryArena, Feb 2026)

## Further Investigation Needed
- CTX CoIR evaluation results
- CTX MemoryArena evaluation results
- Proxy benchmark for Cursor/Copilot/Windsurf cross-session

## Related
- [[projects/CTX/research/20260326-ctx-vs-industry-comparison|20260326-ctx-vs-industry-comparison]]
- [[projects/CTX/research/20260326-ctx-final-sota-comparison|20260326-ctx-final-sota-comparison]]
- [[projects/CTX/research/20260326-ctx-benchmark-validation-roadmap|20260326-ctx-benchmark-validation-roadmap]]
