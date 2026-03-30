---
title: CTX - Trigger-Driven Dynamic Context Loading
emoji: 🧠
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.29.0
app_file: app.py
pinned: true
license: mit
short_description: Trigger-based code retrieval — 1.9x TES vs BM25, 5.2% token usage
---

# CTX: Trigger-Driven Context Retrieval for Code-Aware LLM Agents

Interactive demo — enter a developer query and see which files CTX injects as context and why.

**Key results**: 1.9x higher Token-Efficiency Score than BM25, Recall@5 = 1.0 on implicit dependency queries, only 5.2% token usage.

**GitHub**: https://github.com/jaytoone/CTX
**Install**: `pip install ctx-retriever`
**Claude Code hook**: see [setup guide](https://github.com/jaytoone/CTX/blob/main/docs/claude_code_integration.md)
