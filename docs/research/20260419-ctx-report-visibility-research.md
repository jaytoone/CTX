# [expert-research-v2] ctx-report.py — easier invocation + Claude Code visibility

**Date**: 2026-04-19  **Skill**: expert-research-v2

## Original Question
How should `ctx-report.py` (a local Python script that reads a JSONL telemetry log and prints a text report) be made easier to invoke AND/OR visible directly inside Claude Code's UX, without losing the "terminal report form factor" discipline that kept it from becoming a premature dashboard?

## Web Facts

[FACT-1] Custom slash commands: markdown files in `~/.claude/commands/[name].md` (user-level) or `.claude/commands/[name].md` (project-level). Filename without `.md` = command name. `$ARGUMENTS` captures args passed after the command. (source: https://skillsplayground.com/guides/claude-code-slash-commands/, https://en.bioerrorlog.work/entry/claude-code-custom-slash-command)

[FACT-2] Skills replaced commands as the recommended path in Claude Code v2.1.101 (2026-04-11), unified under `.claude/skills/` but old `.claude/commands/` still works. Skills support YAML frontmatter for `allowed-tools`, `model`, `description`. (source: https://code.claude.com/docs/en/skills, https://supalaunch.com/blog/claude-code-skills-tutorial-custom-slash-commands-and-automations-guide)

[FACT-3] Slash command frontmatter can restrict `allowed-tools` (e.g., only Bash), set model, and provide description shown in `/help`. (source: https://skillsplayground.com/guides/claude-code-slash-commands/)

[FACT-4] Status line: customizable bar at bottom of Claude Code. Configured in `~/.claude/settings.json` under `statusLine: { type: "command", command: "sh ~/my-script.sh" }`. Runs any shell script, receives JSON session data (model, context_window.used_percentage, cost, workspace, rate_limits) on stdin. Runs on EACH update, not one-shot. Supports ANSI colors + OSC 8 clickable links. (source: https://code.claude.com/docs/en/statusline)

[FACT-5] MCP vs slash command: "Use an MCP server if you need Claude to access an external tool, API, or data source; use a skill if you need to change how Claude writes code/communicates/thinks; use a hook if you need something to happen automatically when Claude acts; use a command if you need a reusable prompt shortcut." (source: https://www.morphllm.com/claude-code-skills-mcp-plugins, https://skiln.co/blog/claude-code-plugins-vs-skills-vs-mcp-decision-guide)

[FACT-6] MCP resources are `@`-mentionable, appear in autocomplete alongside files. MCP servers connect via stdio (local process) or SSE. For a local script that's a report generator (not repeatedly queried during Claude's reasoning), MCP is overkill. (source: https://code.claude.com/docs/en/mcp)

## Multi-Lens Analysis

### Domain Expert (Lens 1) — integration patterns

1. **Slash command is the idiomatic "run script, inline output in chat" pattern** [GROUNDED: FACT-1, FACT-5]. `~/.claude/commands/ctx-status.md` with `allowed-tools: [Bash]` and prompt `Run python3 ~/.claude/hooks/ctx-report.py $ARGUMENTS and output stdout verbatim`. Smallest possible change; zero new dependencies.

2. **Status line is a POOR fit for on-demand reports** [GROUNDED: FACT-4]. Runs on every Claude Code update → either constant noise OR a 1-line squeeze that loses the report's real value. Ambient indicators (event count, daemon health) WOULD fit, but that violates "stay out of it" discipline.

3. **MCP server is overkill** [GROUNDED: FACT-5, FACT-6]. MCP is for data sources Claude queries during reasoning; a user-invoked report is not that. Building an MCP server adds stdio boilerplate without benefit for a single script.

4. **Shell alias or `~/.local/bin` symlink for terminal-only** [REASONED: standard Unix ergonomics]. `alias ctxr='python3 ~/.claude/hooks/ctx-report.py'` in rc file = 10 seconds. Symlink `~/.local/bin/ctx-report` works if that dir is in PATH.

### Self-Critique (Lens 2)

1. **[OVERCONFIDENT]** "Slash command idiomatic" — the newer pattern is SKILLS (v2.1.101). Commands still work but are legacy. For this trivial pass-through, skill frontmatter adds complexity. Resolution: use `.claude/commands/` deliberately — simpler is right here.

2. **[MISSING]** Claude may reformat the script's output — model default is to summarize. Fix: prompt must explicitly say "output stdout VERBATIM, do not summarize, do not rephrase."

3. **[MISSING]** Discoverability — slash commands only appear in `/help` if `description:` is set in frontmatter.

4. **[CONFLICT]** Status line would violate the "stay out of it during gathering" principle from prior session. Confirmed NOT to add a status line entry.

5. **[MISSING]** Shell rc cross-platform — bash vs zsh aliases differ. For personal n=1, bash alias is fine. For portable, use symlink.

### Synthesizer (Lens 3) — smallest shippable

**Smallest viable implementation (~12 min total):**

- **Slash command** at `~/.claude/commands/ctx-status.md`:
  - frontmatter: `description`, `allowed-tools: [Bash]`
  - body: "Run `python3 ~/.claude/hooks/ctx-report.py $ARGUMENTS`. Output stdout verbatim, do not summarize or rephrase."
- **Shell alias** in bash/zsh rc:
  - `alias ctxr='python3 ~/.claude/hooks/ctx-report.py'`

Both together cost ~12 minutes, zero ambient noise, works in both surfaces (in-chat via `/ctx-status`, terminal via `ctxr`).

**DO NOT build (adversarially-verified anti-patterns):**
- MCP server (script isn't a data source)
- Status line entry (ambient = noise = violates "stay out of it")
- Skill version (overhead > value for trivial pass-through)

## Final Conclusion

### Key answer
Ship a slash command (`/ctx-status`) + a shell alias (`ctxr`). Both together take ~12 minutes, require no new dependencies, and meet the "visible when I want it, invisible when I don't" bar.

### Recommendations

**1. Create `~/.claude/commands/ctx-status.md`** (user-level, available in every project):

```markdown
---
description: Show CTX telemetry report (events/day, CM mode split, G1/G2 usage, latency)
allowed-tools: [Bash]
---
Run the following command and output its stdout VERBATIM — do not summarize, do not rephrase, do not add commentary before or after the report.

```bash
python3 $HOME/.claude/hooks/ctx-report.py $ARGUMENTS
```
```

Usage: `/ctx-status` (last 7d), `/ctx-status --since=today`, `/ctx-status --since=all`.

**2. Add shell alias** to `~/.bashrc` (or `~/.zshrc`):

```bash
alias ctxr='python3 $HOME/.claude/hooks/ctx-report.py'
```

Usage in terminal: `ctxr`, `ctxr --since=today`, etc.

### Trade-off matrix

| Path | Cost | Discoverability | "Stay out of it" | Fit |
|---|---|---|---|---|
| **Slash command `/ctx-status`** | 1 file, ~10 min | HIGH (`/help`) | PERFECT (only on demand) | ✅ Ship |
| **Shell alias `ctxr`** | 1 rc line | LOW (memory) | PERFECT | ✅ Ship |
| MCP server | 1h + boilerplate | MEDIUM | OK | ❌ Overkill |
| Status line badge | 1 setting + 1 script | HIGH | POOR (ambient) | ❌ Noise |
| Symlink `~/.local/bin/ctx-report` | 1 ln command | LOW | PERFECT | Alternative to alias |

### Critical implementation note
**The slash command body MUST explicitly instruct verbatim output.** Without that, Claude's default behavior will reformat or summarize the report, destroying the point. The phrasing "output stdout VERBATIM — do not summarize, do not rephrase, do not add commentary" is the minimal incantation.

### Confidence: HIGH
Grounded in Claude Code docs for both slash commands (FACT-1, FACT-2, FACT-5) and status line (FACT-4). The MCP/skill/command decision framework (FACT-5) directly matches the recommendation.

## Sources
- [Claude Code slash commands guide](https://skillsplayground.com/guides/claude-code-slash-commands/)
- [Create custom slash commands (bioerrorlog)](https://en.bioerrorlog.work/entry/claude-code-custom-slash-command)
- [Claude Code skills docs (official)](https://code.claude.com/docs/en/skills)
- [Status line docs (official)](https://code.claude.com/docs/en/statusline)
- [MCP docs (official)](https://code.claude.com/docs/en/mcp)
- [Skills vs MCP vs Plugins decision guide (Skiln)](https://skiln.co/blog/claude-code-plugins-vs-skills-vs-mcp-decision-guide)
- [Claude Code full stack explained (alexop.dev)](https://alexop.dev/posts/understanding-claude-code-full-stack/)

## Remaining Uncertainties
- Exact `allowed-tools` YAML syntax may vary between Claude Code versions — verify against one of the linked tutorials when implementing
- Whether `/help` auto-surfaces user-level commands from `~/.claude/commands/` in current version — very likely yes, but worth a post-creation check

## Related
- [[projects/CTX/research/20260410-session-6c4f589e-chat-memory|20260410-session-6c4f589e-chat-memory]]
- [[projects/CTX/research/20260402-project-understanding-evaluation-framework|20260402-project-understanding-evaluation-framework]]
- [[projects/CTX/research/20260330-ctx-academic-critique-web-grounded|20260330-ctx-academic-critique-web-grounded]]
- [[projects/CTX/research/20260327-ctx-real-project-self-eval|20260327-ctx-real-project-self-eval]]
- [[projects/CTX/research/20260411-hook-comparison-auto-index-vs-chat-memory|20260411-hook-comparison-auto-index-vs-chat-memory]]
- [[projects/CTX/research/20260408-g1-longterm-memory-evaluation-framework|20260408-g1-longterm-memory-evaluation-framework]]
- [[projects/CTX/research/20260411-chat-memory-threshold-principled|20260411-chat-memory-threshold-principled]]
- [[projects/CTX/decisions/20260326-path-derived-module-to-file|20260326-path-derived-module-to-file]]
