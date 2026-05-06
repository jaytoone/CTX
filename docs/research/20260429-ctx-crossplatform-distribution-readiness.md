# [expert-research-v2] CTX Cross-Platform Distribution Readiness
**Date**: 2026-04-29  **Skill**: expert-research-v2

## Original Question
Before distributing/publishing CTX to users, what cross-platform issues must be addressed for both Linux and Windows users? CTX uses Python hooks wired into Claude Code's settings.json, a vec-daemon with Unix sockets, BM25/vector search, and a notify listener. The team just migrated from WSL2 to Windows-native (Git Bash/MSYS2).

## Web Facts

[FACT-1] Claude Code hooks with shell commands cause stdio pipe deadlocks on Windows (Git Bash/MSYS2) — every second message hangs 5+ minutes. Issue #34457 OPEN as of v2.1.73, no fix. (source: https://github.com/anthropics/claude-code/issues/34457)

[FACT-2] 9 recurring Git Bash command compatibility bugs: `nul` vs `/dev/null`, `python3` vs `python`, MSYS2 path translation failures, backslash escaping, `//` flag doubling, `cmd /c` CWD issues. (source: https://github.com/anthropics/claude-code/issues/29346)

[FACT-3] Unix domain sockets unavailable on Windows-native. Cross-platform alternatives: Windows Named Pipes or TCP loopback. `pipe-wrench` library abstracts this automatically. (source: https://github.com/suchipi/pipe-wrench)

[FACT-4] `python3` not available on standard Windows installs — triggers Microsoft Store UI redirect, silently breaking hooks. (source: https://github.com/anthropics/claude-code/issues/29346)

[FACT-5] MSYS2/Git Bash: `$HOME` resolves to POSIX path, fails when passed to Windows-native executables. Use `pathlib.Path.home()` instead. (source: https://github.com/anthropics/claude-code/issues/29346)

[FACT-6] Enterprise Windows AD usernames (firstname.lastname) trigger MSYS2 bug making Claude Code completely non-functional. Issue #25628 open. (source: https://github.com/anthropics/claude-code/issues/25628)

[FACT-7] Azure CLI (Python cross-platform) uses `os.name == 'nt'`, `pathlib`, TCP loopback as universal IPC fallback. (source: https://www.python.org/success-stories/building-an-open-source-and-cross-platform-azure-cli-with-python/)

[FACT-8] Cross-platform hooks best practice: use `node` runner in settings.json, `os.homedir()`, `os.tmpdir()`, `path.join()`. (source: https://claudefa.st/blog/tools/hooks/cross-platform-hooks)

[FACT-9] CTX vec-daemon uses Unix socket → broken on Windows-native. chat-memory.py (hybrid) fails; bm25-memory.py (BM25-only) works fine.

[FACT-10] CTX notify listener: WinForms/HTTP on Windows, notify-send on Linux. No unified abstraction.

## Multi-Lens Analysis

### Domain Expert (Lens 1)

**Insight 1 — stdio pipe deadlock is a distribution-blocking risk on Windows-native**
Every Claude Code hook on Windows Git Bash/MSYS2 causes a 5-minute hang every second message (FACT-1). Issue open, no upstream fix. CTX cannot fix this internally — must either scope to WSL2/Linux or test if Python-only hooks avoid the deadlock trigger condition.

**Insight 2 — Unix socket makes chat-memory.py's hybrid mode completely non-functional on Windows**
vec-daemon uses Unix domain socket (FACT-3, FACT-9). Windows-native has no Unix socket support. The fix is TCP loopback replacement (e.g., localhost:6790). bm25-memory.py is unaffected. The failure mode depends on whether the socket error is caught and falls back cleanly — if not, it compounds the deadlock risk.

**Insight 3 — `python3` shebang/command silently breaks hooks on Windows**
Standard Windows Python provides `python`, not `python3` (FACT-4). Hooks invoking `python3` open the Microsoft Store instead — zero output returned. This is the worst failure mode: CTX appears installed but retrieval never runs.

**Insight 4 — Hardcoded path strings will break cross-environment vault.db access**
`~/.local/share/claude-vault/` resolved via string ops fails when MSYS2 POSIX path is passed to Windows-native Python/SQLite (FACT-5). All path construction in bm25-memory.py, chat-memory.py, vec-daemon.py, utility-rate.py must use `pathlib.Path.home()`.

**Insight 5 — Notification system has no cross-platform abstraction**
No OS-branching logic for notify: Windows path on Linux causes ImportError; no-op fallback missing (FACT-10). Non-fatal for retrieval but creates hook crashes on wrong platform.

### Self-Critique (Lens 2)

- **[OVERCONFIDENT]** Insight 1: the exact deadlock trigger is unknown — pure Python hooks with clean stdout may avoid it. CTX-specific testing needed before committing to "WSL2 only" scope decision.
- **[MISSING]** Enterprise AD username bug (FACT-6): omitted from Lens 1. Installer must detect `firstname.lastname` and warn users — CTX can't fix it but can save support overhead.
- **[MISSING]** sqlite-vec (vec0) Windows availability: requires a compiled `.dll` vs Linux `.so`. If not pre-bundled, vault.db initialization silently fails on Windows. Whether the CTX installer handles this is unknown.
- **[MISSING]** Installation automation: CTX install is entirely manual (copy hooks, hand-edit settings.json). No installer, no prerequisite validation. This is a distribution UX blocker independent of platform compatibility.
- **[CONFLICT]** Insight 3 correction: `python3` on Windows is not entirely "silent" — it opens the Microsoft Store UI. The hook returns nothing, but the UX failure is different from a silent null return.

### Synthesis (Lens 3) — Prioritized Action Plan

**P0 — Blockers (must fix before any public distribution)**

| # | Issue | Fix |
|---|-------|-----|
| P0-A | Windows stdio pipe deadlock (FACT-1) | Decide scope: either block Windows-native install with clear error + redirect to WSL2, OR test if node-runner wrapper (FACT-8) avoids the deadlock. Do not distribute without resolving this. |
| P0-B | Unix socket in vec-daemon (FACT-3, FACT-9) | Replace Unix socket path with TCP loopback (localhost:6790). Ensure chat-memory.py catches connection failure and falls back to BM25-only with a clear warning line in output. |
| P0-C | pathlib audit (FACT-5) | Rewrite every `~/.local/share/...` and `~/.claude/...` path construction to use `pathlib.Path.home()` in all 5 hook files. |
| P0-D | `python3` invocation (FACT-4) | Ship a setup script that detects correct Python binary and writes it into settings.json. Never hardcode `python3` in the distributed settings.json template. |

**P1 — Important (fix before wide release)**

| # | Issue | Fix |
|---|-------|-----|
| P1-A | Notify listener OS branching (FACT-10) | Add `sys.platform` dispatch: `win32` → localhost:6789, `linux` → notify-send with no-op fallback, `darwin` → osascript. Prevents ImportErrors on wrong platform. |
| P1-B | sqlite-vec Windows availability | Validate whether pre-built vec0 `.dll` is available from sqlite-vec maintainer. If not, detect vec0 unavailability at startup and fall back to FTS5-only (disable hybrid). |
| P1-C | Enterprise AD username warning (FACT-6) | Installer detects `'.' in os.getenv('USERNAME', '')` on Windows and prints: "⚠ Username contains a dot — Claude Code may not function correctly on MSYS2 (issue #25628)." |
| P1-D | Automated installer | One-command setup: detects OS, validates prerequisites (Python, rank_bm25, sqlite-vec), writes settings.json, initializes vault.db, verifies vec-daemon startup. |

**P2 — Post-launch**

- macOS audit (Unix socket ✓, python3 ✓ via Homebrew, notify via osascript)
- Telemetry path validation on Windows (`CTX_TELEMETRY=1` + `ctx-telemetry.enabled` file detection)
- WSL2 migration guide: document which features work where and what settings.json differences exist

## Final Conclusion

CTX has 4 hard blockers before distribution: (1) the upstream Claude Code stdio deadlock on Windows-native that may hang hooks on every second message, (2) vec-daemon's Unix-socket-only IPC that is completely broken on Windows, (3) `python3` invocation that silently opens the Microsoft Store instead of running the hook, and (4) hardcoded path construction that breaks vault.db access cross-environment. The fastest path to a distributable release is to scope support as **Linux-native + WSL2 only** for v1.0 (bypassing P0-A and P0-B), while shipping an automated installer that handles P0-C and P0-D. Full Windows-native support requires a TCP loopback migration for vec-daemon plus upstream Claude Code fix for issue #34457.

## Sources
- [Issue #34457: Hooks hang/crash on Windows](https://github.com/anthropics/claude-code/issues/34457)
- [Issue #29346: Git Bash recurring command issues](https://github.com/anthropics/claude-code/issues/29346)
- [Issue #25628: AD username period bug](https://github.com/anthropics/claude-code/issues/25628)
- [pipe-wrench: cross-platform IPC](https://github.com/suchipi/pipe-wrench)
- [Azure CLI cross-platform Python success story](https://www.python.org/success-stories/building-an-open-source-and-cross-platform-azure-cli-with-python/)
- [Claude Code cross-platform hooks guide 2026](https://claudefa.st/blog/tools/hooks/cross-platform-hooks)
