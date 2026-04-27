# CTX Distribution Research Replay — 2026-04-21

**Session**: continuation of monetization/validation work (see `20260421-ctx-monetization-session-summary.md`)
**Question that started this**: "ctx-install CLI what do u mean? what it differs from now — isn't there a better method to install or use the whole package, like recently I saw an npm/npx thing that wraps Claude Code service?"
**Outcome**: final recommendation = ship CTX as a **Claude Code plugin** (mirror claude-mem's distribution pattern), via a third-party marketplace at `jaytoone/ctx`. ~3h work, replaces the planned pip+ctx-install CLI as PRIMARY install path.

This document captures the full research evolution — 4 rounds, 3 agent dispatches, one `/inhale` — because the final answer contradicts several intermediate recommendations, and the reasoning matters for future audits.

---

## Why this replay exists

The distribution question looked small ("what is ctx-install and is there a better method?") but exposed structural assumptions about:
- **What ecosystem CTX lives in** (Python-packaging world vs Claude Code plugin world vs npm world)
- **What the competitor landscape actually looks like** (claude-mem at 38k stars is 3× bigger than I initially framed)
- **What distribution primitive maps to the UX the user actually saw** (npx ≠ the answer; `/plugin` IS the answer)

Each research round narrowed the answer AND corrected a prior round's error. Keeping the replay makes the correction process auditable.

---

## Round 0 — initial v0.2 proposal (pre-research)

**Context**: earlier in session I had shipped `src/cli/settings_patcher.py` (atomic JSON merger, self-test passing) + `src/cli/install.py` (ctx-install CLI), and registered `[project.scripts] ctx-install = "ctx_retriever.cli.install:main"` in pyproject.toml. README rewritten from 4-step manual install to `pip install ctx-retriever && ctx-install`.

**v0.2 plan was**:
```
User runs:
  pip install ctx-retriever
  ctx-install
```
- Package hook files into `src/ctx_retriever/hooks/`
- ctx-install copies hooks to `~/.claude/hooks/` + patches settings.json atomically

**User pushback**: "2, 3 job should be execute, but is there any better method to install or use the whole package the better way, like recently I saw an MCP-like format that could aggregate the traffics?"

→ Signaled that my pip+ctx-install approach might be suboptimal vs patterns the user saw elsewhere. Triggered Round 1.

---

## Round 1 — MCP aggregator + Claude Code plugin ecosystem

**Agent**: `research-deep-analyst`, task: MCP aggregator patterns + Claude Code plugin ecosystem (2025).

**Key findings**:
1. MCP 1.0 (Nov 2024) → 1.1 (Q1 2025, Streamable HTTP replaces SSE). OAuth for Remote MCP published.
2. **MCP aggregators with traction**: mcp-proxy (~2k⭐), 5ire (~3k⭐, desktop GUI), mcp-hub (~800⭐, Neovim-focused), Smithery.ai (~500+ MCP servers listed), docker-mcp (Anthropic experimental).
3. MCP aggregators multiplex tool namespaces (`server/tool`) — they don't install anything, they route requests.
4. **Claude Code plugin marketplace status**: [UNCERTAIN] — agent knowledge cutoff said "not publicly shipped." **This turned out to be stale** (see Round 4 correction).
5. **Hooks vs MCP for CTX**: hooks = auto-injection, MCP = LLM-gated tool calls. For CTX's core UX (automatic cross-session memory injection), hooks are correct; MCP tool semantics force the LLM to decide when to call, breaking UX. **Hybrid (hooks + optional MCP for cross-client portability) viable but not required for v0.2.**
6. Cursor/Aider/Windsurf use **no MCP** for their memory layers — meaningful signal against MCP-as-primary for retrieval tools.

**Round 1 recommendation**: stick with pip + ctx-install (v0.2). MCP wrapper is 3-4h and delivers zero value to existing Python-comfortable Claude Code audience. Defer Smithery listing to after MCP wrapper exists.

**Verification I did against the agent's UNCERTAIN tags**: empirically confirmed the Claude Code plugin marketplace IS working. Evidence in this user's own `~/.claude/settings.json`:
```json
"enabledPlugins": {
  "typescript-lsp@claude-plugins-official": true,
  "context7@claude-plugins-official": true,
  "superpowers@claude-plugins-official": true,
  ...
},
"extraKnownMarketplaces": {
  "claude-plugins-official": {
    "source": { "source": "github", "repo": "anthropics/claude-plugins-official" }
  }
}
```
→ 7 plugins live from `claude-plugins-official`. **The research agent's knowledge was outdated by ~8 months.**

---

## Round 1.5 — empirical plugin system investigation

**CGR-verified facts** from direct filesystem inspection:

```
~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json
  → schema: https://anthropic.com/claude-code/marketplace.schema.json
  → 33 plugins listed (adlc, adspirer-ads-agent, agent-sdk-dev, ai-firstify, etc.)
  → Mix of Anthropic + third-party sources (URL-based: SalesforceAIResearch/agentforce-adlc.git;
    git-subdir-based: techwolf-ai/ai-first-toolkit.git)

Plugin structure:
  <plugin-name>/.claude-plugin/plugin.json    ← manifest (name, version, description, author)
  <plugin-name>/hooks/                         ← optional — hook scripts
  <plugin-name>/skills/                        ← optional — skill docs
  <plugin-name>/commands/                      ← optional — slash commands
  <plugin-name>/.mcp.json                      ← optional — MCP server registration

Example plugin with all surfaces:
  ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/example-plugin/
    (has commands/, skills/, hooks/, MCP)
```

→ The marketplace is live, third-party plugins DO ship through it (adlc, adspirer, ai-firstify), and the format is a simple JSON schema.

**Revised Round 1 verdict**: pip + ctx-install works for Python-savvy users, BUT the Claude Code plugin path reduces install to ONE settings.json edit OR a single slash command. Worth revisiting.

---

## Round 2 — alternative install paths (uvx, Homebrew, binary distribution, etc.)

**Agent**: `research-deep-analyst`, task: beyond pip+plugin, what creative distribution paths exist?

**Findings**:
1. **uvx (Astral's uv)**: `uvx ctx-retriever` — installs to isolated env on-demand, ~2-3s first run, ~50ms cached. Best zero-install runner for Python tools. uv adoption ~60%+ in 2024-2025 Python devs.
2. **PyInstaller/Nuitka binaries**: 80MB artifact, worse UX than uvx. Skip.
3. **Shell installer (curl|sh)**: universally understood for dev tools (rustup, mise, uv itself). Medium effort, high reach.
4. **Homebrew tap**: 2-3h, macOS dominant in target audience. Medium priority.
5. **Rewrite in Go/Rust**: 3-6 months, retrieval quality regression. Don't.
6. **Remote/hosted CTX**: inverts local-first value prop. Don't.
7. **Smithery listing**: ~500 MCP servers, relevant IF CTX ships an MCP surface.

**Round 2 recommendation**: ship shell installer wrapping `uv tool install ctx-retriever` + `ctx-install` patches. One command install: `curl -fsSL ctx.run/install.sh | sh`. Under the hood uses `uv` not `pip`.

**Intermediate plan after Round 2**:
```
User runs:
  curl -fsSL ctx.run/install.sh | sh
→ installer detects + installs uv, runs `uv tool install ctx-retriever`, patches settings.json
→ settings.json hooks point to `uvx ctx-retriever run-hook <name>` (not file paths)
```

This SEEMED like the right answer. Then Round 3 blew it up.

---

## Round 3 — the user's actual question (npm/npx wrappers for Claude Code)

**User pushback**: "Nono I recently saw something like npx or npm thing that wraps the Claude Code service like current ctx"

→ uvx was wrong direction. User specifically mentioned npm/npx, which my uvx answer didn't address. Fired focused research.

**Agent**: `research-deep-analyst`, task: what npm/npx tools wrap Claude Code in 2025?

**Key findings**:
1. **The thing the user saw was NOT npm/npx** — it was the **Claude Code `/plugin marketplace` command**. Two-liner that LOOKS npm-ish but is actually GitHub + Claude Code's plugin system.
2. **claude-mem** (already installed at `~/.claude/claude-mem/`) is CTX's direct competitor AND its distribution template:
   - Ships via npm package `claude-mem` (for TypeScript worker service)
   - Ships via `/plugin` system for hook registration
   - Install: `/plugin marketplace add thedotmack/claude-mem && /plugin install claude-mem`
   - Zero manual settings.json editing
3. **Smithery is MCP-only** — doesn't help hook-based tools like CTX (this turned out to be wrong in Round 4).
4. **Node rewrite of CTX makes no sense** — sqlite-vec + multilingual-e5-small path would require Node.js ML toolchain (Candle via Node-ONNX), 2-4 weeks of work, retrieval quality regression.

**Round 3 recommendation**: **Ship CTX as a Claude Code plugin** via GitHub-as-registry (mirror claude-mem). Add thin `@jaytoone/ctx-install` npx shim for npmjs.com discoverability.

**Revised plan**:
```
User runs:
  /plugin marketplace add jaytoone/ctx
  /plugin install ctx
→ Plugin system clones repo, runs setup.sh (pip install deps), wires hooks into settings.json
→ Zero manual JSON editing
```

---

## Round 4 — `/inhale` verification + final ground truth

**Invocation**: `/inhale` on the topic — forced WebSearch verification of remaining UNCERTAIN tags.

**Key new facts** (Round 3's conclusions partially corrected):

1. **Third-party plugin marketplace publishing IS officially documented**: https://code.claude.com/docs/en/plugin-marketplaces. Supports GitHub repos, Git URLs, local paths, remote URLs.

2. **Reserved marketplace names** (CTX cannot use):
   - `claude-code-marketplace`, `claude-code-plugins`, `claude-plugins-official`, `anthropic-marketplace`, `anthropic-plugins`, `agent-skills`, `knowledge-work-plugins`, `life-sciences`
   - → CTX must use `jaytoone/ctx` or similar user-scoped namespace

3. **claude-mem real metrics** (corrected Round 3's rough estimate):
   - **38,401 GitHub stars** + 2,775 forks as of March 2026
   - Claimed 3k new stars in one day at some point
   - Current version v12.3.5 (release cadence: v12.3.3 → 12.3.4 → 12.3.5 all within recent weeks)
   - Install UX: `npm install -g claude-mem` does NOT register hooks — must use `npx claude-mem install` OR `/plugin install claude-mem`

4. **Install command forms** (both valid):
   - Inside Claude Code: `/plugin marketplace add <owner/repo> && /plugin install <name>`
   - From shell: `claude plugin install <name>` (subcommand of `claude` CLI)
   - Local dev: `claude --plugin-dir ./your-plugin` (no install required for testing)

5. **Plugins can include**: commands, agents, skills, hooks, **MCP servers**, **LSP servers**, **background monitors** — full surface, not just hooks.

6. **Smithery is NOT MCP-only** (corrected Round 3):
   - Smithery.ai hosts a **"Skills"** category separate from MCP servers
   - Examples found: `pleaseai/claude-code-plugin-builder`, `obra/working-with-claude-code`, `thoeltig/managing-plugins`
   - CTX COULD list on Smithery as a Skill even without exposing MCP

7. **The real 2026 distribution landscape** includes discovery surfaces:
   - claudemarketplaces.com (directory of marketplaces + plugins)
   - aitmpl.com/plugins/ (discovery directory)
   - Smithery Skills listing
   - All are free 15-min listings

---

## Final synthesis

### What the user actually saw
**Claude Code's `/plugin marketplace add <owner/repo> && /plugin install <name>` command.** Two terminal lines, looks npm-ish, is actually GitHub + the plugin system. Not npx. Not MCP. Not uvx. The empirical answer.

### Competitive reset
- claude-mem: **38k stars, trending**, 38× bigger than I initially framed. Has the distribution win.
- CTX: 0 stars, has the MEASUREMENT win (utility telemetry, Wilson CI, T0+T1+T2 pipeline). Unique asset claude-mem doesn't replicate.
- Distribution gap is closable in ~3h by mirroring claude-mem's plugin structure. Measurement differentiation is the long-term moat.

### What changes about prior plans

| Prior plan | Status after Round 4 |
|---|---|
| pip+ctx-install as PRIMARY install | ⚠️ demoted to fallback path |
| ctx-install CLI (already built, atomic JSON merge) | ✅ kept — useful inside plugin's setup.sh + fallback for users without plugin system |
| `src/cli/settings_patcher.py` (atomic merge) | ✅ kept — reusable primitive regardless of path |
| uvx-prefixed hook commands | ❌ rejected — plugin system's `${CLAUDE_PLUGIN_ROOT}` is the actual convention |
| curl\|sh shell installer | ❌ rejected — `/plugin install ctx` is the ecosystem's one-command install |
| npm/`npx ctx-install` wrapper | ⚠️ deferred — not needed if `claude plugin install ctx` works |
| Smithery listing | ✅ added — free discovery surface for Skills, not only MCP |
| Claude Code `enabledPlugins`/`extraKnownMarketplaces` settings | ✅ CONFIRMED LIVE — already in use by 7 plugins in this session |
| Node.js rewrite of CTX | ❌ rejected — 2-4 weeks, quality regression |
| Hosted/remote CTX | ❌ rejected — breaks local-first value prop |

### Final v0.2 execution plan (~3h total)

**Hour 1: plugin scaffold**
- Add to CTX repo:
  ```
  .claude-plugin/
    plugin.json           # name, version, description, keywords, author
    marketplace.json      # owner=jaytoone, plugin=ctx
  plugin/
    hooks/
      hooks.json          # UserPromptSubmit×3 + PostToolUse(Grep) + Stop + SessionStart entries
      chat-memory.py      # copied from ~/.claude/hooks/
      bm25-memory.py
      memory-keyword-trigger.py
      g2-fallback.py
      utility-rate.py     # for Stop hook
    scripts/
      setup.sh            # pip install rank_bm25 sqlite_vec numpy (Setup event, 120s timeout)
      vec-daemon-start.sh # for SessionStart event
  ```
- All hook commands use `${CLAUDE_PLUGIN_ROOT}/hooks/<file>` path format

**Hour 2: local testing + publish**
- Test locally: `claude --plugin-dir ./CTX/plugin install ctx`
- Iterate until smoke test passes on fresh user
- Push to GitHub, tag v0.2
- Verify remote install: `/plugin marketplace add jaytoone/ctx && /plugin install ctx`

**Hour 3: README rewrite + discovery listings**
- README install section: lead with `/plugin marketplace add jaytoone/ctx && /plugin install ctx` as PRIMARY, demote pip to "for users without plugin system"
- Submit listings to: claudemarketplaces.com, aitmpl.com, Smithery Skills
- Update Show HN draft — lead with distribution parity + measurement honesty angle, not "new memory tool"

### What this replay did NOT resolve

1. **Anthropic official marketplace (`claude-plugins-official`) submission process** — unknown if third-party PRs are accepted or if Anthropic curates. Skip for v0.2; ship as independent marketplace first, accumulate stars, THEN submit.
2. **Windows compatibility** — `setup.sh` is bash. Need either a setup.bat or a Node.js fallback for Windows users. Defer to v0.3.
3. **Auto-update mechanism** — plugin system has `/plugin update` but unclear if it auto-triggers. Users may need to know to run it.
4. **Show HN launch timing vs plugin ship** — launch AFTER plugin is shipped and self-install verified, not before.

---

## Meta-lesson (for next time)

Every round corrected at least one fact from the prior round:
- Round 1 said plugin marketplace was "UNCERTAIN" → Round 1.5 empirically verified it IS live
- Round 2 recommended uvx → Round 3 corrected to `/plugin` pattern
- Round 3 said Smithery is MCP-only → Round 4 corrected to Smithery hosts Skills too
- Round 3 estimated claude-mem at 3-4k stars → Round 4 corrected to 38k stars

**Research-agent knowledge cutoff matters enormously in fast-moving ecosystem spaces.** For anything Claude Code / plugin / MCP related, CGR-verify against live filesystem + targeted web searches BEFORE acting on agent recommendations. Multiple rounds of research are cheaper than shipping the wrong install surface.

---

## Artifacts produced this session (pre-pivot)

Files already written that remain useful even after pivot:
- `~/Project/CTX/src/cli/__init__.py` — CLI package init
- `~/Project/CTX/src/cli/settings_patcher.py` — atomic JSON merger, self-test passing. Will be reused inside plugin's setup.sh as fallback OR for users on older Claude Code.
- `~/Project/CTX/src/cli/install.py` — ctx-install CLI. Demoted from primary install to fallback.
- `~/Project/CTX/pyproject.toml` — `[project.scripts] ctx-install = ...` registered. Keep.
- `~/Project/CTX/README.md` — install section rewritten. Will be re-rewritten in Hour 3 above.

## Artifacts produced this session (post-pivot — NOT YET BUILT)

Targets for the ~3h execution if approved:
- `~/Project/CTX/.claude-plugin/plugin.json` — plugin manifest
- `~/Project/CTX/.claude-plugin/marketplace.json` — third-party marketplace registration
- `~/Project/CTX/plugin/hooks/hooks.json` — 6 hook entries with ${CLAUDE_PLUGIN_ROOT}
- `~/Project/CTX/plugin/hooks/*.py` (5 files) — copied from ~/.claude/hooks/
- `~/Project/CTX/plugin/scripts/setup.sh` — pip deps on install
- `~/Project/CTX/plugin/scripts/vec-daemon-start.sh` — SessionStart daemon probe + restart

## Sources cited across research rounds

- [Create and distribute a plugin marketplace - Claude Code Docs](https://code.claude.com/docs/en/plugin-marketplaces)
- [Create plugins - Claude Code Docs](https://code.claude.com/docs/en/plugins)
- [anthropics/claude-plugins-official on GitHub](https://github.com/anthropics/claude-plugins-official)
- [claude-plugins-official marketplace.json](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)
- [thedotmack/claude-mem on GitHub](https://github.com/thedotmack/claude-mem)
- [claude-mem Installation Docs](https://docs.claude-mem.ai/installation)
- [Claude Code Plugins | Skills, MCP Servers & Marketplace Directory](https://claudemarketplaces.com/)
- [aitmpl.com plugin directory](https://www.aitmpl.com/plugins/)
- [How to Build Claude Code Plugins: DataCamp tutorial](https://www.datacamp.com/tutorial/how-to-build-claude-code-plugins)
- [Claude Code plugins README (anthropic/claude-code)](https://github.com/anthropics/claude-code/blob/main/plugins/README.md)
- [claude-code-plugin-builder Skill on Smithery](https://smithery.ai/skills/pleaseai/claude-code-plugin-builder)
