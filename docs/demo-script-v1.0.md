# CTX Demo Video — Narration Script v1.0
**Date**: 2026-04-29  **Target length**: ~3 min  **Platform**: Linux / WSL2

---

## Pre-recording checklist

- [ ] Terminal: clean, dark theme, font size 18+, 1920×1080
- [ ] Claude Code open in the CTX project directory
- [ ] vault.db seeded with at least 3 past sessions
- [ ] `bm25-memory.py` wired and confirmed firing (`ctx-install status` shows ✅)
- [ ] Rehearse the two demo prompts — responses must be real, not scripted

---

## [0:00–0:20] HOOK — The Problem

**Screen**: Terminal. Claude Code open, fresh session. No context loaded yet.

> "Every time you open Claude Code, it starts from zero."

**Action**: Type and send:
```
why did we switch from TF-IDF to BM25 for the retrieval scorer?
```

**Expected WITHOUT CTX**: Claude gives a generic or wrong answer — "I don't have context about previous decisions in this project."

> "You ask it something you already decided three sessions ago —"
> "— and it has no idea."
> "That's the cold-start problem. CTX fixes it."

---

## [0:20–0:40] INSTALL

**Screen**: New terminal pane. WSL2 bash prompt.

> "Installation is one command."

**Action**: Type (don't run — or run a pre-staged version):
```bash
pip install ctx-retriever && ctx-install
```

> "CTX wires four hooks into Claude Code's settings dot json."
> "It backs up your existing config first. Merges cleanly — never overwrites your other hooks."
> "Restart Claude Code. Done."

**Action**: Brief flash — open `~/.claude/settings.json`, scroll to the hooks block. 2 seconds max.

> "Two hooks fire on every prompt you type."
> "bm25-memory — past decisions, relevant docs, relevant code."
> "chat-memory — semantic search across your conversation history."

---

## [0:40–1:25] G1 DEMO — Decision Memory

**Screen**: Back to Claude Code. Same project, same cold session — but CTX is now wired.

> "Same question. Same cold session."

**Action**: Type and send the exact same prompt:
```
why did we switch from TF-IDF to BM25 for the retrieval scorer?
```

**Action**: Scroll up briefly to show the hook injection line in Claude's context — `[CTX G1] 3 decisions injected`.

**Expected WITH CTX**: Claude answers accurately — cites keyword R@3 improvement, the IDF problem on small corpora, the 0.379 → 0.655 → 0.724 journey.

> "CTX pulled that decision out of your git history and past sessions."
> "No embedding model. No cloud API. Pure BM25, under one millisecond."
> "Claude answered correctly because CTX remembered — so it didn't have to."

*[Pause 1 second.]*

> "That's G1. Cross-session decision recall."

---

## [1:25–2:10] G2 DEMO — File Retrieval

**Screen**: New prompt in the same session.

> "Now G2 — finding the right file without you pointing to it."

**Action**: Type and send:
```
update the BM25 scoring weights in the retrieval scorer
```

**Action**: Show the hook injection line — `[CTX G2-CODE] src/retrieval/adaptive_trigger.py:214 injected`.

**Expected WITH CTX**: Claude opens `src/retrieval/adaptive_trigger.py` at the correct function on the first tool call. No directory scan, no grep loop.

> "Without CTX, Claude would grep through your entire codebase."
> "Four, five, sometimes ten tool calls before it finds the right file."
> "CTX found it before Claude's first tool call."

*[Brief cut — show the tool call count in a WITHOUT session: 7 grep calls.]*

> "G2 searches your docs, your codebase, and your hooks — all at once."
> "Under one millisecond."

---

## [2:10–2:35] NUMBERS

**Screen**: Static benchmark table — GitHub README or the HF Space demo page.

> "These aren't toy benchmarks."

*[Read each row slowly — one breath per row.]*

> "G1 decision recall — one-point-zero with CTX, zero-point-two without."
> "G2 docs H@5 — one-point-zero hybrid, versus zero-point-eight BM25 alone."
> "Hallucination rate — zero percent with CTX. Seventeen percent without."
> "Hook latency — zero-point-eight milliseconds. No LLM. No embedding model."
> "Utility rate — fifty percent of tool-use turns get context Claude actually cites."

---

## [2:35–3:00] WRAP

**Screen**: GitHub repo page — `github.com/jaytoone/CTX`.

> "CTX is open source, MIT licensed."
> "Linux and WSL2. One pip install."

*[Pause.]*

> "If you use Claude Code and you're tired of re-explaining your own codebase to it —"
> "give CTX five minutes."

**Screen**: Final frame — URL + install command side by side, held for 4 seconds.

```
github.com/jaytoone/CTX

pip install ctx-retriever && ctx-install
```

> "Link in the description."

---

## B-roll / cutaway shots (optional, for editing)

| Timestamp | Shot |
|-----------|------|
| After install | `ctx-install status` output — green checkmarks for all 4 hooks |
| After G1 | vault.db session count — "47 sessions indexed" |
| After G2 | Side-by-side: 7 tool calls (without) vs 1 tool call (with) |
| Benchmarks | Animate the table row by row |

---

## Recording notes

- Record terminal at 2x actual speed, then slow to 0.75x during typing — removes dead air while keeping legibility.
- Do NOT fake the Claude responses. Record live — real hook injection is the demo.
- If chat-memory vec-daemon is down during recording, the `⚠ vec-daemon down` warning in the injection block is fine — leave it in. Shows honest failure mode.
- Keep the hook injection output visible for at least 2 seconds before Claude starts responding.
