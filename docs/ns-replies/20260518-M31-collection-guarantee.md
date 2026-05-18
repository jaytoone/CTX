# M31 — Telemetry Collection Guarantee: Research Findings

**Date:** 2026-05-18  
**Context:** Current .pth mechanism achieves ~65-75% collection rate from v0.3.26 installs. User asked for solutions.

## Root Causes (Confirmed)

| Gap | Cause | Size |
|---|---|---|
| Primary | `.pth` suppressed inside venvs (`PYTHONNOUSERSITE=1`, poetry/conda/pyproject default) | ~15-25% |
| Secondary | `_send_install_ping()` no retry — single HTTP timeout = permanent miss | ~8-12% |
| Tertiary | `ctx-install` subprocess fails silently (editable install edge cases, never-start users) | ~3-5% |

**CPython behavior confirmed**: `user site-packages .pth` files are suppressed inside venvs unless `pyvenv.cfg` has `include-system-site-packages = true` — which is false by default in poetry, conda, and `python -m venv`.

---

## Solutions, Ranked by ROI

### 1. SessionStart hook as primary collection channel (RECOMMENDED FIRST)
**Gap closed: +15-25% | Complexity: LOW**

Claude Code hook subprocesses inherit the system/user Python (not venv Python) — the hook's `sys.executable` is venv-agnostic by construction. Add a check to `bm25-memory.py` or a new `session-start-telemetry.py` hook: if `~/.claude/ctx-autoinstall-done` doesn't exist, fire the install ping from the hook's interpreter.

Implementation: ~15 lines in `bm25-memory.py`. No packaging changes.

### 2. Stamp-file retry queue
**Gap closed: +8-12% | Complexity: LOW**

Pattern: On ping failure in `_send_install_ping()`, write `~/.claude/ctx-install-pending.json` with the payload. On next hook execution (SessionStart/UserPromptSubmit), retry once and delete on success. Mirrors Sentry's transport spec + PostHog's atexit flush pattern. No background threads.

### 3. `usercustomize.py` injection (highest ceiling, venv-safe)
**Gap closed: +10-20% | Complexity: MEDIUM**

`usercustomize.py` in `~/.local/lib/python3.x/site-packages/` runs on every Python startup INCLUDING inside venvs (unless `-s` / `PYTHONNOUSERSITE=1`). This is exactly how OpenTelemetry's auto-instrumentation works. Write a minimal check here during `ctx-install`. Risk: must append if file exists, not overwrite. Behind an opt-in initially.

### 4. `bm25-memory.py` retry check (belt-and-suspenders)
**Gap closed: +6-10% | Complexity: LOW**

Add 10 lines to existing `bm25-memory.py`: if `ctx-install-pending.json` exists and is <7 days old, attempt Turso ping with 5s timeout, delete on success. Zero packaging changes.

### 5. atexit flush in `_autoinstall.py`
**Gap closed: +3-5% | Complexity: LOW**

Register `atexit` handler inside `_autoinstall.py` to fire install ping when the `.pth`-loading Python process exits. Catches "installs but never starts Claude Code" case.

---

## Implementation Priority

| Order | Solution | Expected Cumulative Rate |
|---|---|---|
| Current | .pth only (v0.3.26) | ~65-75% |
| 1 | + SessionStart hook | ~80-90% |
| 2 | + Stamp-file retry | ~88-95% |
| 4 | + bm25-memory.py retry | ~92-96% |
| 3 | + usercustomize.py | ~95-99% |

**Doing solutions 1 + 2 + 4 together** (all within existing hook system, no packaging changes) closes the gap from ~70% to ~93%. Solution 3 is highest ceiling but needs careful append logic.

---

## References
- Python docs: `site` module — user site-packages `.pth` suppressed in venvs
- Sentry SDK transport spec (stamp-file pattern)
- OpenTelemetry `sitecustomize.py` auto-instrumentation source
- Claude Code hooks reference
- PostHog Python SDK atexit flush pattern
