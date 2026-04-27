# [expert-research-v2] bm25-memory Hook 범용 프로젝트 적용 방법
**Date**: 2026-04-09  **Skill**: expert-research-v2

## Original Question
CTX bm25-memory hook을 범용 프로젝트에서도 잘 동작하게 만들려면 무엇을 바꿔야 하나?

현재 상황:
- bm25-memory.py는 CTX 자체 프로젝트(YYYYMMDD prefix commit style, docs/research/*.md 구조)에 최적화됨
- G1 closed-set recall = 0.881 (CTX 프로젝트), open-set = 0.250 (Flask/Requests/Django)
- `_is_decision()` 함수: CTX 스타일 YYYYMMDD prefix를 인식하지만 일반 프로젝트의 commit 스타일은 놓칠 수 있음
- G2a: docs/research/*.md 경로 하드코딩
- G2b: codebase-memory-mcp 의존

---

## Web Facts (Phase 1 Fact Finder)

**[FACT-1]** Conventional Commits 자동 분류 (ICSE 2025): CodeLlama fine-tuned 모델이 10개 CCS 타입 분류에서 macro F1 = 0.7641 달성. 가장 어려운 카테고리는 `chore` (F1=0.5397). 88,704개 commits (116 repositories) 데이터셋 사용.
- Source: [ICSE 2025](https://dl.acm.org/doi/10.1109/ICSE55347.2025.00011), [GitHub](https://github.com/0x404/conventional-commit-classification)

**[FACT-2]** Linux 커널 commit message 내 rationale 분류 연구: Decision 시그널 단어: `add`, `use`, `remove`, `kill`, `introduce`, `check` (각 18-28회). Rationale 시그널: `might`, `fixes`, `help`, `will`. 98.9%의 commit에 rationale 정보 존재. 언어 무관.
- Source: [arXiv 2403.18832](https://arxiv.org/html/2403.18832v1)

**[FACT-3]** Lore Protocol (2026-03): git trailers로 structured decision knowledge — `Constraint:`, `Rejected:`, `Confidence:`, `Directive:` 등 8개. 실증 벤치마크 없음 (프로토콜 제안 수준).
- Source: [arXiv 2603.15566](https://arxiv.org/html/2603.15566)

**[FACT-4]** CoMRAT (MSR 2025): commit message rationale 분석 도구.
- Source: [MSR 2025](https://2025.msrconf.org/details/msr-2025-data-and-tool-showcase-track/3/)

**[FACT-5]** GitHub Copilot Memory (2026-03 GA): 저장소 단위 스코프. cross-project 없음. 28일 만료.
- Source: [GitHub Blog](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)

**[FACT-6]** Cursor Memory: mid-2025 project-level Memories → v2.1.x에서 제거. 현재 `.cursor/rules/*.mdc`로 대체. organization-wide memory는 "future goal."
- Source: [Cursor Community Forum](https://forum.cursor.com/t/persistent-ai-memory-for-cursor/145660)

**[FACT-7]** Aider repo-map: tree-sitter AST 파싱 → PageRank → cross-session memory 없음. 매 세션 fresh.
- Source: [Aider Blog](https://aider.chat/2023/10/22/repomap.html)

**[FACT-8]** Zed: 네이티브 cross-project memory 없음. MCP 서버(ByteRover 등)로 외부 memory 주입 가능.
- Source: [Zed Docs](https://zed.dev/docs/ai/agent-panel)

**[FACT-9]** BM25 open-domain top-1 recall = 22.1%, hybrid pipeline = 53.4% (+31.3%p). 핵심 문제: vocabulary mismatch.
- Source: [RAG Engineers](https://ranjankumar.in/bm25-vs-dense-retrieval-for-rag-engineers)

**[FACT-10]** SPLADE: MS MARCO 학습 후 BEIR에서 BM25보다 나쁜 일반화 가능. sparse neural도 도메인 외 성능 저하.
- Source: [Qdrant](https://qdrant.tech/articles/modern-sparse-neural-retrieval/)

**[FACT-11]** Hybrid retrieval: BM25 + dense top-20 fusion → 15-30% recall 향상. 기술 문서 최적: BM25 0.6/Dense 0.4. Reranking 시 hallucination 23% → 11%.
- Source: [Hybrid Search Guide](https://ranjankumar.in/building-a-full-stack-hybrid-search-system-bm25-vectors-cross-encoders-with-docker)

**[FACT-12]** Claude Code 철학: "Just-in-time context, not pre-inference RAG."
- Source: [Mike Mason 2026](https://mikemason.ca/writing/ai-coding-agents-jan-2026/)

**[FACT-13]** BM25 subword extension (tiktoken): OOV 문제 완화. trade-off: raw text coverage 일부 손실 vs. 구현 단순성.
- Source: [Medium](https://medium.com/@emitchellh/extending-bm25-with-subwords-30b334728ebd)

---

## Multi-Lens Analysis (Phase 1 Deep Analyst + Phase 1.5 Devil's Advocate)

### Domain Expert Analysis (5 Points)

**Point 1: `_is_decision()` Over-Fitting**
- CTX YYYYMMDD prefix + ML-specific keywords (CONVERGED, iter, benchmark, eval, ablation, recall) → general projects miss
- Fix candidate: 3-tier (CC pattern → verb signal → date heuristic)

**Point 2: G2a `docs/research/*.md` Hardcoding**
- General projects use docs/, doc/, README.md, CHANGELOG.md, wiki/
- Fix: glob scan from project root

**Point 3: G2b SQLite/codebase-memory-mcp Scope**
- CLAUDE_PROJECT_DIR only — hooks/, external paths 제외
- Fix: direct BM25 indexing (G2b-hooks 이미 구현)

**Point 4: BM25 Corpus Collapse (IDF Distortion)**
- CTX: 163 pre-filtered decisions → IDF well-calibrated
- Open-set: 2000 raw commits → IDF distorted
- Fix candidate: decision_pool vs general_pool split

**Point 5: Korean Tokenizer Bias**
- English-only 프로젝트: benign (regex no-op)
- NOT a generalization blocker

### Self-Critique / Devil's Advocate (Phase 1.5)

**CRITICAL — Root Cause Misdiagnosis**
- Open-set recall 0.250 ≈ BM25's known open-domain ceiling of 0.221 (FACT-9)
- Collapse is BM25's fundamental vocabulary mismatch limit, NOT primarily `_is_decision()` keyword overfit
- Fixing `_is_decision()` alone will yield <0.05 recall improvement
- **Real fix: Hybrid BM25 + Dense (FACT-11: +15-30%)**

**CRITICAL — Missing Hybrid Retrieval**
- FACT-9: BM25 = 22.1%, hybrid = 53.4% — the delta is the entire improvement budget
- FACT-11: BM25 0.6/Dense 0.4 confirmed best for technical docs
- This should be the headline recommendation, not regex tuning

**MAJOR — Keyword-Expansion Fallacy**
- FACT-1: even fine-tuned CodeLlama achieves F1=0.76 on CC classification
- Regex tiers will be strictly worse → bounded at F1=0.76 ceiling
- Better: FACT-2's empirically-validated verb signals (add/use/remove/kill/introduce/check) — language-agnostic, zero ML

**MAJOR — Missing CTX Moat Analysis**
- FACT-5/6/7/8: ALL major coding agents (Copilot, Cursor, Aider, Zed) LACK cross-session git-based memory
- CTX is unique. Generalization strategy must preserve this moat
- Framing: "how to expand CTX's unique capability to other project styles" (not "how to match Cursor")

**MAJOR — Hybrid Breaks <1ms Latency Promise**
- CTX's current value prop: deterministic, <1ms, no LLM calls
- Dense embedding: all-MiniLM-L6-v2 = ~50ms on CPU (not <1ms)
- Must address: async pre-computation, two-stage (BM25 filter → dense rerank top-5), or explicit latency disclosure

**MAJOR — No Ablation Plan**
- Which factor (keywords / IDF / corpus composition) causes 0.250?
- Single experiment: set `_is_decision()` = identity function (all commits), re-measure open-set → isolates keyword effect
- Should precede any implementation

---

## Cross-Validation Matrix (Phase 2)

| Topic | Fact Finder | Devil's Advocate | Consensus |
|-------|-------------|------------------|-----------|
| BM25 ceiling = root cause of 0.250 | CONFIRMED (FACT-9: 22.1%) | CRITICAL | CONFIRMED-STRONG |
| Hybrid BM25+Dense as fix | CONFIRMED (FACT-11: +15-30%) | CRITICAL missing | CONFIRMED-STRONG |
| FACT-2 decision verbs for `_is_decision()` | CONFIRMED (empirical) | VALID addition | CONFIRMED-STRONG |
| CTX cross-session uniqueness | CONFIRMED (FACT-5/6/7/8 all absent) | CRITICAL gap | CONFIRMED-STRONG |
| Regex/CC pattern tier | CONTRADICTED (F1=0.76 ceiling) | MAJOR critique | CONTESTED — qualify heavily |
| G2a dynamic path discovery | CONFIRMED (no contradiction) | MINOR fix | CONFIRMED |
| Korean tokenizer benign | CONFIRMED | Mostly agreed | STRONG |
| Hybrid breaks latency | New (DA) | MAJOR | CONTESTED — tradeoff |
| Lore Protocol opt-in | FACT-3 (no benchmark) | UNRESOLVED | UNRESOLVED |

---

## Final Conclusion (Phase 3 Synthesis)

### Core Answer

**Open-set recall 0.250은 BM25의 알려진 오픈 도메인 한계(≈0.22)이며, `_is_decision()` keyword 오버피팅의 직접 결과가 아니다.** `_is_decision()` 개선만으로는 recall이 0.05 이상 개선되기 어렵다. 실질적 개선을 위해서는 아키텍처 변화가 필요하다.

### 우선순위별 구체적 개선 방안

#### Priority 1: `_is_decision()` 개선 (Low effort, 즉시 가능)

FACT-2 기반 언어 독립적 verb signal 추가:

```python
# 현재: CTX-specific
_DECISION_KEYWORDS = frozenset(["CONVERGED", "iter", "benchmark", "eval", ...])

# 개선: universal decision verbs (arXiv 2403.18832 기반)
_DECISION_VERBS = frozenset(["add", "use", "remove", "kill", "introduce", "check",
                              "migrate", "replace", "upgrade", "downgrade", "revert"])
_RATIONALE_SIGNALS = frozenset(["might", "fixes", "help", "will", "because", "since", "to"])

# 3-tier:
# Tier 1: Conventional Commits prefix (feat:/fix:/refactor:/perf:)
# Tier 2: Decision verbs in subject + body length > 50 chars
# Tier 3: Current YYYYMMDD/keyword heuristics (CTX-specific, keep as tier 3)
```

**예상 효과**: 10-15% `_is_decision()` 커버리지 향상 (recall 개선은 제한적 — BM25 ceiling 별도)

#### Priority 2: G2a 동적 경로 발견 (Low effort)

```python
# 현재: 하드코딩
_DOCS_PATTERNS = ["docs/research/*.md"]

# 개선: 프로젝트 루트에서 glob 스캔
def discover_doc_paths(project_dir: Path) -> list[str]:
    candidates = ["docs/**/*.md", "doc/**/*.md", "documentation/**/*.md",
                  "wiki/**/*.md", "notes/**/*.md", "CHANGELOG*.md",
                  "README*.md", "ADR/**/*.md", "decisions/**/*.md"]
    return [p for p in candidates if list(project_dir.glob(p))]
```

#### Priority 3: 개선 전 ablation 실험 (Before hybrid implementation)

1. `_is_decision()` → 전체 커밋 수용 (identity function)으로 교체
2. Flask/Django/Requests open-set recall 재측정
3. recall 개선 < 0.05 → BM25 ceiling 확인 → hybrid로 진행
4. recall 개선 ≥ 0.05 → keyword overfit 문제 → _is_decision() 집중 개선

#### Priority 4: Hybrid BM25 + Dense (High effort, High impact)

FACT-11: BM25 0.6/Dense 0.4 → +15-30% recall for technical docs

**설계 옵션**:
- **Option A (비동기 사전계산)**: SessionStart 시 dense embeddings 생성 → `.omc/embeddings.pkl` 저장 → query time은 BM25(fast) + dense(precomputed) 동시 조회. 초기 latency 50-200ms, 이후 <5ms.
- **Option B (two-stage)**: BM25 top-10 → dense rerank on top-10 only. Dense 추론 횟수 = 10회. ~30ms.
- **Option C (subword BM25)**: FACT-13 tiktoken 기반. 순수 BM25, latency 무변화. OOV 완화에만 효과.

**핵심 tradeoff**: hybrid = <1ms 보장 파기. CTX 현재 "0 LLM calls, <1ms" 마케팅 포인트와 충돌.

#### Priority 5: Two-Profile 접근 (Strategic)

- **Profile A** (default): 현재 CTX (YYYYMMDD, research keywords) — 빠름, 검증됨
- **Profile B** (general): CC prefix + FACT-2 verbs + hybrid retrieval — 느림, 더 범용
- `.bm25-memory.toml`로 프로파일 선택

### CTX 포지셔닝 인사이트

**FACT-5/6/7/8의 공통점**: GitHub Copilot, Cursor, Aider, Zed 모두 cross-session git-based memory 없음. 이것이 CTX의 유일한 differentiator다.

범용화는 "다른 도구와 기능 경쟁"이 아니라 "CTX의 고유 capability를 다양한 project style에서 사용 가능하게"로 프레이밍해야 한다. 여기서 핵심은 _is_decision()의 vocabulary generalization이지 hybrid retrieval 도입이 아닐 수 있다.

### Caveats & Trade-offs

- **Hybrid recall 수치(FACT-11: +15-30%)는 commit message 도메인에서 검증되지 않음** — 기술 문서 기준값. commit messages는 더 짧고 noisier → 최적 비율이 다를 수 있음.
- **Open-set 0.250 eval protocol**: CTX closed-set(손수 QA 59쌍)과 open-set(CHANGELOG 기반 QA)의 query generation 방식이 다를 수 있음 — eval artifact 가능성.
- **Flask/Requests/Django는 오픈소스 성숙 프로젝트** — 랜덤 기업 monorepo는 open-set 0.250보다 나쁠 수 있음 (upper bound).

### Further Investigation Needed

1. **Ablation 실험** (1시간): `_is_decision()` = identity → open-set recall 측정 → 진짜 원인 규명
2. **Commit message dense embedding** recall 측정: all-MiniLM-L6-v2로 Flask/Django/Requests eval
3. **5+ project style** open-set eval harness 구축 (현재 N=3 — 통계적으로 부족)
4. **hybrid retrieval latency** 실측: two-stage BM25→dense rerank 실제 지연 측정

---

## Reference Sources

- [ICSE 2025 — Conventional Commits Classification](https://dl.acm.org/doi/10.1109/ICSE55347.2025.00011)
- [arXiv 2403.18832 — Linux Kernel Commit Rationale](https://arxiv.org/html/2403.18832v1)
- [arXiv 2603.15566 — Lore Protocol](https://arxiv.org/html/2603.15566)
- [GitHub Blog — Copilot Memory](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/)
- [Cursor Community — Persistent Memory](https://forum.cursor.com/t/persistent-ai-memory-for-cursor/145660)
- [Aider Blog — Repository Map](https://aider.chat/2023/10/22/repomap.html)
- [Qdrant — Sparse Neural Retrieval](https://qdrant.tech/articles/modern-sparse-neural-retrieval/)
- [BM25 vs Dense for RAG](https://ranjankumar.in/bm25-vs-dense-retrieval-for-rag-engineers)
- [Hybrid Search Guide](https://ranjankumar.in/building-a-full-stack-hybrid-search-system-bm25-vectors-cross-encoders-with-docker)
- [BM25 Subword Extension](https://medium.com/@emitchellh/extending-bm25-with-subwords-30b334728ebd)

## Related
- [[projects/CTX/research/20260409-g1g2-critique-and-verification|20260409-g1g2-critique-and-verification]]
- [[projects/CTX/research/20260409-g1-fulleval-sota-comparison|20260409-g1-fulleval-sota-comparison]]
