# CTX — Cross-Session Memory for Claude Code

CTX gives Claude Code persistent memory across sessions. It injects relevant past decisions, docs, and context into every prompt automatically via three retrieval layers:

- **G1** (time) — recent git commit decisions, ranked by BM25 relevance to the current prompt
- **G2** (space) — BM25 search over project docs and code files
- **CM** (chat) — semantic search over past conversation summaries (optional vec-daemon)

## Install

```bash
pip install ctx-retriever
ctx-install
```

Or via Claude Code plugin (this package):

```
/plugin install ctx@jaytoone
```

The Setup hook installs dependencies and wires hooks automatically. Restart Claude Code after install.

## How it works

CTX runs as Claude Code hooks. On every prompt, it retrieves the top-k relevant memories and injects them as `additionalContext` so Claude sees your project history without you having to re-explain it.

## Requirements

- Python 3.9+
- pip

## License

MIT — see [LICENSE](LICENSE)

## Links

- [GitHub](https://github.com/jaytoone/CTX)
- [PyPI](https://pypi.org/project/ctx-retriever/)
- [HuggingFace Demo](https://huggingface.co/spaces/Be2Jay/ctx-demo)
