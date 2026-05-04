# Empirical measurement: Context Mode interaction with CTX hooks in headless mode

Hi mksglu,

I ran an empirical eval of `context-mode` running alongside another UserPromptSubmit hook (CTX, retrieval-based memory injection — `hang-in/tunaCtx`) in headless `claude -p` mode. Sharing the data because two patterns surfaced that might be relevant.

## Setup

- **context-mode version**: 1.0.107 (plugin)
- **Model**: claude-opus-4-7
- **Invocation**: `claude -p --output-format=stream-json --no-session-persistence`
- **States compared**: 
  - A = both active
  - B = Context Mode only (CTX hooks removed from settings.json)
  - C = CTX only (`enabledPlugins.context-mode@context-mode` removed)
  - D = neither
- **Total**: 5 scenarios × 4 states = 20 measurements at ~$8 of Opus

## Two patterns observed in headless mode

### Pattern 1 — `ctx_batch_execute` permission denial in non-interactive sessions

In two scenarios (commit analysis, TODO grep across .py files), the response with Context Mode active contained explicit error text like:

```
"ctx_batch_execute 권한 거부됨" / permission denied for ctx_batch_execute
"Permission needed. Asking the user to grant ctx_batch_execute..."
```

The model attempted to use Context Mode's batch tool but the headless environment couldn't surface the permission prompt, so the call was denied and the entire task aborted. The "both active" state initially ranked 4th of 4 in those two scenarios.

**Verification with `--dangerously-skip-permissions`** (8 additional measurements, +$2.57):

| Scenario | default permissions (1st run) | with `--dangerously-skip-permissions` |
|---|---|---|
| 30-commit analysis (state A) | `Permission needed. Asking the user to grant...` (abort) | `## seCall 최근 30개 commit 분석... feat: 9건, fix: 6건...` (full analysis) |
| TODO grep across .py (state A) | `ctx_batch_execute 권한 거부됨. Grep tool로 진행` (partial fallback) | `프로젝트 .py 파일 203개 중 # TODO/FIXME/XXX/HACK 주석은 0건` (precise, includes .venv-golden noise filtering) |

So the "Pattern 1" ranking issue is **definitely a headless permission artifact**, not a defect in Context Mode itself. Cost goes up 13–21% with skip-perm because `ctx_batch_execute` actually runs — which is the intended behavior.

Possible mitigations from your side:

- Ship a documented `--allow-ctx-tools` env var or settings flag for headless use
- Or auto-skip ctx_batch_execute when stdin/stdout aren't TTY
- Or document the headless permission story in the README (e.g. recommend `--dangerously-skip-permissions` for CI)

### Pattern 2 — `ctx_batch_execute` cost in low-tool-density scenarios

For scenarios where the model would have used 1-2 simple tools anyway (e.g. "summarize last 5 commits"), Context Mode's tool routing added overhead without value:

| Scenario | A (both) cost | C (CTX only) cost | D (none) cost | A's judge rank |
|---|---:|---:|---:|---:|
| 5-commit summary | $0.334 | $0.158 | $0.205 | 2nd of 4 (C won) |
| 30-commit analysis | $0.393 | $0.168 | $0.191 | **4th** (timeout/permission) |

For "small" tasks, Context Mode's batching infrastructure activates but doesn't compress meaningfully more than a 1-line `git log`. The C state (Context Mode off) was cheaper and equal-or-better quality.

For "large" tasks where compression would matter (the 30-commit analysis), the permission pattern from #1 cancelled any benefit.

The scenarios where Context Mode added clear value were:
- Code search with line-number precision (1st place, both active)
- Korean docstring search across mixed Rust/TS codebases (1st place)

Both involved `Read` heavy paths where Context Mode's plumbing helped — but those wins are inside the `ctx_batch_execute` flow, not the `ctx_execute` raw-output one.

## Suggestion (optional)

A `~/.claude/context-mode-config.json` style toggle for "tool-heavy / tool-light" workloads, or a heuristic that auto-disables `ctx_batch_execute` when the prompt looks small (e.g. expected response < 1KB), might capture both wins (compress when valuable) and avoid the friction in light/headless cases.

## Data

- Full report: `docs/refactor/EVAL_RESULTS.md` in `hang-in/tunaCtx`
- Korean dev env (mixed Korean prompts + Korean comments + English code)
- 1 prompt × 4 states per scenario (no variance estimate; LLM-as-judge has known biases)

Happy to re-run with different prompt sets or share raw stream-json output if useful for context-mode improvements. Not asking for any specific change — just figured Korean + headless data might be a corner of your user base you don't see often.
