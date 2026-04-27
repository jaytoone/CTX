# [expert-research-v2] CTX Plugin Distribution Strategy
**Date**: 2026-04-27  **Skill**: expert-research-v2

## Original Question
What are the current best practices for publishing a Python-based Claude Code hook system (CTX) as a distributable plugin/service in 2026? Specifically: Claude Code plugin system, PyPI packaging for hooks, community distribution standards, settings.json registration.

---

## Key Findings

### 1. CTX's Plugin Scaffold is 90% Complete

CTX already has the required native plugin structure at `/home/jayone/Project/CTX/.claude-plugin/`:
- `plugin.json` (v0.2.0, correct schema)
- `marketplace.json`
- `plugin/hooks/hooks.json` (4 production hooks using `${CLAUDE_PLUGIN_ROOT}`)
- `plugin/scripts/setup.sh` (venv creation, dep install)
- `plugin/scripts/vec-daemon-start.sh` (SessionStart probe)

The gap to publishable is **one remaining item**: hook files need to ship inside the wheel as `package_data`.

### 2. The Native Plugin System is the Primary Path

Install UX for end users:
```bash
/plugin marketplace add jaytoone/CTX   # add self-hosted marketplace
/plugin install ctx                    # single command install
```

Or after official registry submission:
```bash
/plugin install ctx@jaytoone
```

### 3. PyPI is a Real Secondary Path

Existing prior art: `claude-mem`, `claude-code-memory`, `claude-pyhooks`, `claude-code-plugins-sdk` all ship on PyPI with the same pattern.

CTX already has `ctx-install = "ctx_retriever.cli.install:main"` in `pyproject.toml`. The one missing piece: `install.py` exits with "MISSING HOOKS" if `~/.claude/hooks/bm25-memory.py` doesn't exist — fix it to copy hooks from the installed package via `importlib.resources`.

Secondary path:
```bash
pipx install ctx-retriever && ctx-install
```

### 4. Known Bug: CLAUDE_PLUGIN_ROOT Update Bug

Two open issues directly affect CTX:
- **#18517**: `/plugin update` does NOT update hook paths in `settings.json` → hooks silently point to deleted directory
- **#52218**: auto-update is even worse — doesn't update `installed_plugins.json` either

**Mitigation**: Document that users should run `/plugin install ctx` (not `/plugin update`) to re-expand paths. Add check in `ctx-install status`.

### 5. Community Standard: GitHub + Awesome-Lists

- `anthropics/claude-plugins-official` — official curated registry (Anthropic-reviewed, "Verified" badge)
- `ComposioHQ/awesome-claude-plugins` — 13,500+ repos indexed
- Topic tag for discoverability: **`claude-code-plugin`** (CTX's plugin.json has it; GitHub repo Settings topics still need it)

---

## Distribution Strategy Comparison

| Option | Upside | Downside | Priority |
|--------|--------|----------|----------|
| Native plugin (`/plugin install`) | Zero-step once discovered; official marketplace | CLAUDE_PLUGIN_ROOT update bug | **P0 — Primary** |
| PyPI (`pipx install + ctx-install`) | Works everywhere Python runs | PEP 668 blocks pip; low discoverability | **P1 — Secondary** |
| GitHub install script (`curl \| bash`) | Lowest friction | Security optics; no version management | P2 |
| Homebrew | Mac-native UX | Maintainer burden; no Linux | P3 |

---

## Concrete Action Plan (ordered by ROI)

1. **GitHub topics** (5 min): Add `claude-code-plugin`, `claude-code`, `hooks`, `memory`, `bm25` to repo Settings → Topics.

2. **package_data fix** (30 min):
   - Move `plugin/hooks/*.py` into `src/ctx_retriever/hooks/`
   - Add to `pyproject.toml`: `package_data = {"ctx_retriever": ["hooks/*.py"]}`
   - Update `install.py` to copy from `importlib.resources` instead of exiting with MISSING HOOKS

3. **Plugin submission** (30 min): Submit to `platform.claude.com/plugins/submit` with existing `plugin.json` and `hooks.json`.

4. **README install section** (20 min): Add two-path install instructions:
   ```bash
   # Option A — Native plugin (recommended)
   /plugin marketplace add jaytoone/CTX
   /plugin install ctx

   # Option B — PyPI
   pipx install ctx-retriever && ctx-install
   ```

5. **Update bug mitigation note** (20 min): Add `ctx-install status` check for stale versioned paths in `settings.json`.

---

## Remaining Uncertainties

- **Review timeline** for `anthropics/claude-plugins-official` submission — unknown queue times
- **CLAUDE_PLUGIN_ROOT update bug status** — check if #18517 was patched in current Claude Code version before recommending plugin path as primary
- **`package_data` path** — `plugin/hooks/` is outside `src/`; verify whether files need to be moved under `src/ctx_retriever/hooks/`
- **`claude-mem` in official registry?** — if yes, CTX needs differentiation note (BM25 vs AI compression, utility measurement, visible failure)

---

## Sources
- [Claude Code Plugins docs](https://code.claude.com/docs/en/plugins)
- [Plugins reference - Claude Code Docs](https://code.claude.com/docs/en/plugins-reference)
- [anthropics/claude-plugins-official - GitHub](https://github.com/anthropics/claude-plugins-official)
- [ComposioHQ/awesome-claude-plugins - GitHub](https://github.com/ComposioHQ/awesome-claude-plugins)
- [Issue #18517 - Plugin hooks not updated after version change](https://github.com/anthropics/claude-code/issues/18517)
- [Issue #52218 - Plugin autoUpdate stale paths](https://github.com/anthropics/claude-code/issues/52218)
- [claude-mem - PyPI](https://pypi.org/project/claude-mem/)
- [claude-code-memory - PyPI](https://pypi.org/project/claude-code-memory/)

## Related
- [[projects/CTX/research/20260409-bm25-memory-generalization-research|20260409-bm25-memory-generalization-research]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
