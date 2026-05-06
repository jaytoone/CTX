---
title: CTX - Cross-Session Memory for Claude Code
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.29.0
app_file: app.py
pinned: true
license: mit
short_description: G1 decision recall + G2 file retrieval hooks for Claude Code
---

# CTX: Cross-Session Memory for Claude Code

Interactive before/after demo — see what Claude Code answers with and without CTX context injection.

**What CTX does**: Two hooks fire on every Claude Code prompt. G1 recalls past engineering decisions from your session history. G2 finds the relevant file and line number before Claude's first tool call. Pure BM25, under 1ms, no LLM, no embedding model.

**Key results**: G1 Recall@7 = 1.000 (vs 0.219 without), hallucination rate 0% (vs 17%), hook latency < 1ms.

**Platform**: Linux + WSL2 (v1.0). Windows-native in progress.

**GitHub**: https://github.com/jaytoone/CTX  
**Install**: `pip install ctx-retriever && ctx-install`
