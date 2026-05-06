# CTX v0.3.10 — Channel Posts Draft
**Date**: 2026-05-02 | **Status**: DRAFT — awaiting confirmation before posting
**Version**: ctx-retriever==0.3.10 | **GitHub**: https://github.com/jaytoone/CTX

---

## 1. LinkedIn

**Audience**: Developers, AI engineers, Claude Code users
**Tone**: Founder, honest, no hype
**Length**: ~300 words

---

Claude Code is powerful. But it forgets everything the moment you close the session.

Every new session, you re-explain the architecture. Re-describe what you decided last week. Re-locate the file you were working on.

I got tired of it, so I built CTX.

CTX is a hook-based context bootstrapper for Claude Code. Before each prompt, it automatically injects:

- G1: your recent decisions pulled from git log (what you built and why)
- G2: BM25 search over your docs and codebase (the right files, not random ones)
- CM: a vault of past conversations that actually mattered

No LLM calls. No embedding API. Under 1ms. Runs as a Claude Code hook — completely invisible unless you look at the injected context.

Some numbers from real usage:

- Memory recall: 0.880 [0.762, 0.944] vs 0.00 without CTX (MAB N=50, Wilson CI)
- Utility rate: 39.6% of injected items Claude actually referenced — measured across 10,000+ real turns
- Installation: 2 steps, under 2 minutes

It is open source, MIT licensed, and on PyPI.

Install:
pip install ctx-retriever && ctx-install

Or natively inside Claude Code:
/plugin install ctx@jaytoone

GitHub: https://github.com/jaytoone/CTX

If you use Claude Code daily and feel like you're repeating yourself every session — this is for you.

---

## 2. Blog (Dev.to / Personal)

**Title**: CTX: I gave Claude Code a memory that actually works
**Audience**: Developers, AI tooling enthusiasts
**Tone**: Technical, honest, benchmark-backed
**Length**: ~800 words

---

### The problem

Claude Code resets every session. There is no built-in memory. You open a new terminal, start coding, and the model has no idea what you decided yesterday, what architecture you settled on, or which files matter. You explain it again. Every time.

I spent three months building something to fix this.

### What CTX does

CTX hooks into Claude Code's `UserPromptSubmit` event. Before every prompt, three things happen — in under 1ms:

**G1 — Decision memory**
Parses your git log and surfaces the most relevant past decisions. "Why did we switch to BM25?" "What was the reasoning behind this architecture?" CTX pulls those commit messages and injects them before you even ask.

**G2 — Code and doc search**
BM25 search across your entire codebase and markdown docs. When you ask about a function, the right files are already in context. No more "I can't find that file" hallucinations.

**CM — Chat memory vault**
A local SQLite database of past conversations, hybrid-searched (BM25 + optional vector). The things you explained once, you should only have to explain once.

### The numbers

I ran rigorous benchmarks — not synthetic toy tests.

**Memory recall (MAB, N=50)**

| System | Recall | Wilson CI 95% |
|--------|--------|----------------|
| None (baseline) | 0.00 | [0.00, 0.07] |
| CTX | 0.40 | [0.28, 0.54] |
| CTX v2 | 0.58 | [0.44, 0.71] |
| CTX v3 | 0.88 | [0.762, 0.944] |

CTX v3 vs baseline: McNemar p < 0.001. Statistically significant.

**Real-world telemetry (10,000+ turns)**
- Overall utility rate: 39.6% (items injected that Claude actually cited)
- CM block: 52.6% utility rate (highest — chat memory is the most cited)
- G1 block: 39.6%
- G2 docs: 27.8%

A 42 percentage point gap between KEYWORD (16%) and SEMANTIC (42%) queries confirms retrieval method selection matters — and CTX routes them differently.

### How it installs

```bash
pip install ctx-retriever && ctx-install
```

Or natively in Claude Code:
```
/plugin install ctx@jaytoone
```

Two steps. The installer copies hooks to `~/.claude/hooks/` and patches `settings.json` atomically (backup-first, never overwrites existing hooks).

Validated in a clean Docker container (ubuntu:22.04) — all 4 install steps pass.

### What it does not do

- No cloud sync. Everything stays local.
- No LLM calls. Pure BM25 + SQLite.
- No mandatory telemetry. Opt-in only.
- Does not replace Claude's context window — it fills it intelligently before you ask.

### Links

- GitHub: https://github.com/jaytoone/CTX
- PyPI: https://pypi.org/project/ctx-retriever/
- Dashboard: runs locally at port 8787 after install

---

## 3. GeekNews (geek.news)

**Title**: CTX: Claude Code에 세션 간 메모리 추가하는 훅 플러그인
**Audience**: 한국 개발자 커뮤니티
**Tone**: 간결, 기술적, 수치 기반
**Length**: ~200 words (제목 + 본문)

---

**제목**: CTX: Claude Code 세션 간 메모리 — pip install 또는 /plugin install 로 설치

**본문**:

Claude Code는 세션을 닫으면 모든 컨텍스트를 잃습니다. CTX는 이 문제를 Claude Code 훅으로 해결합니다.

**동작 방식**: UserPromptSubmit 이벤트에서 1ms 이내로 3가지 컨텍스트를 자동 주입합니다.

- G1: git log 기반 의사결정 타임라인 (어제 왜 그 결정을 했는지)
- G2: BM25 코드/문서 검색 (관련 파일 자동 주입)
- CM: 과거 대화 vault (SQLite FTS5 + 선택적 벡터)

**실측 수치**:
- 메모리 회상 정확도: 0.880 [0.762, 0.944] (MAB N=50, Wilson CI)
- 베이스라인(없음): 0.00
- 실제 10,000+ 턴 기준 활용률: 39.6%

**설치**:
```bash
pip install ctx-retriever && ctx-install
# 또는 Claude Code 내에서:
/plugin install ctx@jaytoone
```

LLM 호출 없음. 클라우드 없음. 완전 로컬.

GitHub: https://github.com/jaytoone/CTX

---

## 4. Hacker News (Show HN)

**Title**: Show HN: CTX – Claude Code hook that injects cross-session memory before each prompt
**Audience**: HN developers, AI tooling builders
**Tone**: Technical, direct, numbers-first
**Length**: Show HN body ~150 words

---

**Title**: Show HN: CTX – Claude Code hook that injects cross-session memory before each prompt

**Body**:

Claude Code has no persistent memory between sessions. Every time you start a new session, context is gone.

CTX fixes this with three hooks on `UserPromptSubmit`:

- G1: parses git log → injects relevant past decisions
- G2: BM25 search over codebase + markdown docs → injects relevant files
- CM: SQLite vault of past conversations → hybrid search (BM25 + optional vec)

All three run in <1ms. No LLM calls. No external APIs. Pure BM25 + SQLite.

Benchmarks (MAB N=50, Wilson CI):
- CTX v3: 0.880 [0.762, 0.944] vs baseline 0.00
- McNemar p < 0.001 vs baseline

Real telemetry over 10k+ turns: 39.6% of injected items were actually cited by Claude.

Install: `pip install ctx-retriever && ctx-install`
Or: `/plugin install ctx@jaytoone` inside Claude Code

MIT. Local only. Telemetry opt-in.

GitHub: https://github.com/jaytoone/CTX

Happy to discuss the BM25 routing logic or benchmark methodology in comments.

---

## 5. YouTube

**Format**: Short demo (3-5 min) OR YouTube Short (60s)
**Title options**:
- "Claude Code forgets everything. This plugin fixes it."
- "I gave Claude Code a memory — here's how it works"
- "CTX: Before/after — Claude Code with and without session memory"

**Script outline** (short demo, ~3 min):

---

[HOOK — 0:00-0:15]
Open two Claude Code sessions side by side.
Session 1 (no CTX): "What architecture did we decide on last week?" → Claude says it doesn't know.
Session 2 (CTX): Same question → Claude immediately recalls the decision with source.

[PROBLEM — 0:15-0:40]
"Claude Code resets every session. No memory. No context. You re-explain everything, every time. I built CTX to solve this."

[DEMO — 0:40-2:00]
Show `ctx-install` running (30 sec).
Show the hook firing — `last-injection.json` updating in real time.
Show CTX Dashboard at port 8787 — live events, utility rate, grade.
Demonstrate: ask about a past decision → CTX injects it automatically.

[NUMBERS — 2:00-2:30]
"Here are the benchmarks. MAB N=50. CTX v3 recall: 0.880. Baseline: 0.00. Real usage across 10,000 turns: 39.6% utility rate."

[INSTALL — 2:30-2:50]
```bash
pip install ctx-retriever && ctx-install
# or inside Claude Code:
/plugin install ctx@jaytoone
```

[CTA — 2:50-3:00]
"Link in description. MIT licensed. Runs entirely local. Star it if it's useful."

---

## Status Tracker

| Channel | Status | URL |
|---------|--------|-----|
| LinkedIn | DRAFT | — |
| Blog (Dev.to) | DRAFT | — |
| GeekNews | DRAFT | — |
| Hacker News | DRAFT | — |
| YouTube | SCRIPT DRAFT | — |

**Next step**: Confirm each post above, then execute in order 1→5.
