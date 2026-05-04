"""ctx-install — one-command CTX hook installer for Claude Code.

Usage:
    ctx-install                   # install / activate (idempotent)
    ctx-install --dry-run         # show what would change; touch nothing
    ctx-install --uninstall       # remove CTX hooks from settings.json
    ctx-install status            # check current install state + hook health

Design goals (why this CLI exists):
  - Before:  pip install → manual cp → manual edit hook path → manual JSON paste
    (4 steps, 15 min, high failure rate at the JSON paste step)
  - After:   pipx install ctx-retriever && ctx-install    (2 steps, ~2 min, atomic-safe)

Atomic safety: settings.json is NEVER partially written, NEVER overwritten
without a timestamped backup, NEVER loses the user's existing hooks.

Hook files are shipped as package data (ctx_retriever.hooks) and auto-copied
to ~/.claude/hooks/ on first install. Subsequent installs are idempotent.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.resources
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    from .settings_patcher import patch_settings, unpatch_settings, _load
except ImportError:
    # Fallback when run via `python -m ctx_retriever.cli.install` without install
    sys.path.insert(0, str(Path(__file__).parent))
    from settings_patcher import patch_settings, unpatch_settings, _load


# ─────────────────────── config ───────────────────────
CLAUDE_HOOKS_DIR = Path.home() / ".claude" / "hooks"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CLAUDE_VAULT_DIR = Path.home() / ".local" / "share" / "claude-vault"

# Daemon scripts shipped in wheel → deployed to ~/.local/share/claude-vault/
CTX_DAEMONS = ["vec-daemon.py", "bge-daemon.py"]

# The 5 production hooks CTX ships. Each entry: (filename, event, async).
# Matched against current ~/.claude/settings.json structure.
CTX_HOOKS = [
    ("chat-memory.py",            "UserPromptSubmit", False),
    ("bm25-memory.py",            "UserPromptSubmit", False, ["--rich"]),
    ("memory-keyword-trigger.py", "UserPromptSubmit", False),
    ("g2-fallback.py",            "PostToolUse",      False),
    ("utility-rate.py",           "Stop",             True),   # telemetry — async
]


def _hook_entry(filename: str, extra_args: list[str] | None = None) -> dict:
    """Build the JSON hook entry for settings.json."""
    cmd = f"python3 $HOME/.claude/hooks/{filename}"
    if extra_args:
        cmd = cmd + " " + " ".join(extra_args)
    return {"type": "command", "command": cmd}


def _new_hooks_block() -> dict:
    """Compose the {event: [entries]} dict that gets merged into settings.json."""
    by_event: dict = {}
    post_tool_use_matchers: dict = {}   # PostToolUse needs a matcher field
    for spec in CTX_HOOKS:
        filename = spec[0]
        event = spec[1]
        extra = spec[3] if len(spec) >= 4 else None
        entry_hooks = [_hook_entry(filename, extra)]
        if event == "PostToolUse":
            # PostToolUse entries carry a matcher — default "Grep" for g2-fallback
            matcher = "Grep" if filename == "g2-fallback.py" else "Write|Edit"
            post_tool_use_matchers.setdefault(matcher, []).extend(entry_hooks)
        else:
            by_event.setdefault(event, []).append({"hooks": entry_hooks})
    for matcher, hooks in post_tool_use_matchers.items():
        by_event.setdefault("PostToolUse", []).append(
            {"matcher": matcher, "hooks": hooks}
        )
    return by_event


# ─────────────────────── steps ───────────────────────

def _pkg_hooks_dir() -> Path | None:
    """Return path to bundled hook files in the installed package, or None."""
    try:
        # Python 3.9+ importlib.resources API
        pkg = importlib.resources.files("ctx_retriever.hooks")
        # Materialise to a real path (works for both editable and wheel installs)
        with importlib.resources.as_file(pkg) as p:
            return p if p.is_dir() else None
    except (ModuleNotFoundError, TypeError, AttributeError):
        return None


def _file_sha256(path: Path) -> str:
    """Return hex SHA-256 of file contents."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _copy_hook_file(
    src_file: Path,
    dst_file: Path,
    *,
    force: bool,
    no_update: bool,
    dry_run: bool,
    chmod: int,
) -> str:
    """Copy src_file → dst_file with update policy.

    Returns one of: "copied", "updated", "unchanged", "skipped".
    Side-effects: creates backup before overwrite; skips if no_update.
    """
    if not dst_file.is_file():
        # New file — always copy
        if not dry_run:
            shutil.copy2(src_file, dst_file)
            dst_file.chmod(chmod)
        return "copied"

    if no_update:
        return "skipped"

    if not force and _file_sha256(src_file) == _file_sha256(dst_file):
        return "unchanged"

    # Hash differs (or --force) → update with timestamped backup
    if not dry_run:
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = dst_file.with_suffix(f".backup_{ts}{dst_file.suffix}")
        shutil.copy2(dst_file, backup)
        shutil.copy2(src_file, dst_file)
        dst_file.chmod(chmod)
    return "updated"


def step_copy_hooks(
    dry_run: bool = False,
    force: bool = False,
    no_update: bool = False,
) -> tuple[int, int, int, list[str]]:
    """Copy hook files from the installed package to ~/.claude/hooks/.

    Update policy (applied to each existing file):
      - Default:       hash-compare; update if different (creates .backup_<ts> first)
      - --force-hooks: overwrite unconditionally without hash check
      - --no-update-hooks: skip existing files (legacy behaviour)

    Returns (copied, updated, skipped, errors).
    """
    src = _pkg_hooks_dir()
    if src is None:
        return 0, 0, 0, ["Package hooks dir not found — run `pip install ctx-retriever` first"]

    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    copied, updated, skipped, errors = 0, 0, 0, []

    # Hook filenames we care about (from CTX_HOOKS + telemetry helper)
    hook_files = [spec[0] for spec in CTX_HOOKS] + ["_ctx_telemetry.py", "utility-rate.py"]

    for fname in hook_files:
        src_file = src / fname
        dst_file = CLAUDE_HOOKS_DIR / fname
        if not src_file.is_file():
            continue  # optional file
        try:
            action = _copy_hook_file(
                src_file, dst_file,
                force=force, no_update=no_update,
                dry_run=dry_run, chmod=0o755,
            )
        except OSError as e:
            errors.append(f"copy {fname}: {e}")
            continue
        if action == "copied":
            copied += 1
        elif action == "updated":
            updated += 1
        else:  # "unchanged" or "skipped"
            skipped += 1

    # Copy _bm25/ sub-package (required by bm25-memory.py at runtime).
    src_bm25 = src / "_bm25"
    dst_bm25 = CLAUDE_HOOKS_DIR / "_bm25"
    if src_bm25.is_dir():
        bm25_files = list(src_bm25.glob("*.py"))
        if not dry_run:
            dst_bm25.mkdir(parents=True, exist_ok=True)
        for py_file in bm25_files:
            dst_f = dst_bm25 / py_file.name
            try:
                action = _copy_hook_file(
                    py_file, dst_f,
                    force=force, no_update=no_update,
                    dry_run=dry_run, chmod=0o644,
                )
            except OSError as e:
                errors.append(f"copy _bm25/{py_file.name}: {e}")
                continue
            if action == "copied":
                copied += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1

    return copied, updated, skipped, errors


def step_copy_daemons(dry_run: bool = False) -> tuple[int, int, list[str]]:
    """Copy vec-daemon.py and bge-daemon.py from the installed package to
    ~/.local/share/claude-vault/. These power the semantic layer (hybrid
    CM/G1/G2-DOCS). BM25-only mode works without them.
    Returns (copied, skipped, errors)."""
    src = _pkg_hooks_dir()
    if src is None:
        return 0, 0, []  # non-fatal: daemons are optional

    CLAUDE_VAULT_DIR.mkdir(parents=True, exist_ok=True)
    copied, skipped, errors = 0, 0, []

    for fname in CTX_DAEMONS:
        src_file = src / fname
        dst_file = CLAUDE_VAULT_DIR / fname
        if not src_file.is_file():
            continue
        if dst_file.is_file():
            skipped += 1
            continue
        if not dry_run:
            try:
                shutil.copy2(src_file, dst_file)
                dst_file.chmod(0o755)
                copied += 1
            except OSError as e:
                errors.append(f"copy {fname}: {e}")
        else:
            copied += 1

    return copied, skipped, errors


def step_verify_hooks_present() -> tuple[bool, list[str], list[str]]:
    """Confirm expected hook files exist at ~/.claude/hooks/.
    Returns (all_present, found, missing)."""
    found, missing = [], []
    for spec in CTX_HOOKS:
        filename = spec[0]
        p = CLAUDE_HOOKS_DIR / filename
        (found if p.is_file() else missing).append(filename)
    return (not missing), found, missing


def step_smoke_test() -> tuple[bool, str]:
    """Fire bm25-memory.py with a dummy prompt and confirm it writes
    ~/.claude/last-injection.json. Validates end-to-end that the hook
    chain is wired correctly."""
    hook = CLAUDE_HOOKS_DIR / "bm25-memory.py"
    if not hook.is_file():
        return False, f"{hook} missing — skipping smoke test"
    inj = Path.home() / ".claude" / "last-injection.json"
    try:
        inj.unlink()
    except FileNotFoundError:
        pass
    try:
        result = subprocess.run(
            ["python3", str(hook), "--rich"],
            input=json.dumps({"prompt": "ctx-install smoke test: list recent decisions"}),
            capture_output=True, text=True, timeout=8,
            env={**os.environ, "CTX_DASHBOARD_INTERNAL": "1"},   # suppress telemetry
        )
    except Exception as e:
        return False, f"hook invocation failed: {e}"
    if result.returncode != 0:
        return False, f"hook exit {result.returncode}: {result.stderr[:200]}"
    # Fresh installs with no corpus won't write last-injection.json — that's valid.
    if inj.exists():
        return True, f"hook fired, wrote {inj} ({inj.stat().st_size} bytes)"
    return True, "hook fired OK (no corpus yet — last-injection.json not written on fresh install)"


# ─────────────────────── commands ───────────────────────

def cmd_install(args: argparse.Namespace) -> int:
    print("== ctx-install ==")
    print(f"Target: {CLAUDE_SETTINGS}")
    print(f"Hooks dir: {CLAUDE_HOOKS_DIR}\n")

    # 1. Copy hook files from package (update policy: hash-compare by default)
    force = getattr(args, "force_hooks", False)
    no_update = getattr(args, "no_update_hooks", False)
    copied, updated, skipped, errors = step_copy_hooks(
        dry_run=args.dry_run, force=force, no_update=no_update,
    )
    print(f"1/4 hook files:  copied={copied}  updated={updated}  unchanged/skipped={skipped}")
    if errors:
        for e in errors:
            print(f"   ✗ {e}")
    if not args.dry_run and errors:
        print("\n  Hook copy failed — cannot proceed.")
        return 2

    # Verify all hooks are in place
    ok, found, missing = step_verify_hooks_present()
    if missing and not args.dry_run:
        print(f"   Missing after copy: {missing}")
        print(f"   Place hook files manually at {CLAUDE_HOOKS_DIR}/ and retry.")
        return 2

    # 2. Copy daemon files (vec-daemon + bge-daemon) — optional semantic layer
    d_copied, d_skipped, d_errors = step_copy_daemons(dry_run=args.dry_run)
    if d_copied or d_skipped:
        print(f"2/4 daemons:     copied={d_copied}  already-present={d_skipped}"
              f"  (→ {CLAUDE_VAULT_DIR})")
    else:
        print(f"2/4 daemons:     not found in package (BM25-only mode active)")
    for e in d_errors:
        print(f"   ✗ {e}")

    # 3. Patch settings.json
    new_hooks = _new_hooks_block()
    result = patch_settings(CLAUDE_SETTINGS, new_hooks, dry_run=args.dry_run)
    print(f"\n3/4 settings.json patch:")
    print(result.summary())
    if not result.ok:
        return 3

    if args.dry_run:
        print("\n  [DRY RUN] — no smoke test (would require live install).")
        print("  Re-run without --dry-run to execute.")
        return 0

    # 4. Smoke test
    ok, msg = step_smoke_test()
    print(f"\n4/4 smoke test:  {'PASS' if ok else 'FAIL'}")
    print(f"   {msg}")
    if not ok:
        print("\n  Hook chain installed but smoke test failed.")
        print("  Check the hook files directly with: python3 ~/.claude/hooks/bm25-memory.py --rich")
        return 4

    print("\n" + "=" * 50)
    print("CTX installed. Restart Claude Code to activate.")
    print("Verify: claude -p 'list recent decisions'")
    if d_copied:
        print("\nSemantic layer (vec-daemon + bge-daemon) deployed.")
        print("To activate: nohup python3 ~/.local/share/claude-vault/vec-daemon.py &")
        print("  Optional BGE rerank: nohup python3 ~/.local/share/claude-vault/bge-daemon.py &")
        print("  (vec-daemon starts automatically on next Claude Code session)")
    print("=" * 50)
    return 0


def _cleanup_hook_files(
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """Remove CTX hook files and _bm25/ from ~/.claude/hooks/.

    Returns a dict with three lists:
      "removed"   — files deleted.
      "kept"      — files skipped because user modified them (hash mismatch) or
                    _bm25/ had extra files.
      "not_found" — files that did not exist (already gone).

    Safety rules:
      - Hook file: compare SHA-256 against package source.  If hash differs and
        force=False, keep file and emit a warning.
      - _bm25/ dir: remove only if every *.py inside matches a known CTX file.
        If extra files are present and force=False, skip the whole directory.
      - force=True: skip all hash checks and force-remove everything.
    """
    removed: list[str] = []
    kept: list[str] = []
    not_found: list[str] = []

    src = _pkg_hooks_dir()
    # Full list of hook files CTX installs
    hook_files = [spec[0] for spec in CTX_HOOKS] + ["_ctx_telemetry.py", "utility-rate.py"]

    for fname in hook_files:
        dst = CLAUDE_HOOKS_DIR / fname
        if not dst.exists():
            not_found.append(fname)
            continue
        # Hash-based safety check (skip when --force or src unavailable).
        if not force and src is not None:
            src_file = src / fname
            if src_file.is_file() and _file_sha256(dst) != _file_sha256(src_file):
                kept.append(fname)
                print(
                    f"   kept  {fname}  (user-modified; use --force to override)",
                    file=sys.stderr,
                )
                continue
        if not dry_run:
            dst.unlink()
        removed.append(fname)

    # Handle _bm25/ sub-directory
    dst_bm25 = CLAUDE_HOOKS_DIR / "_bm25"
    if dst_bm25.is_dir():
        present_files = list(dst_bm25.glob("*.py"))
        if src is not None and not force:
            src_bm25 = src / "_bm25"
            known_names: set[str] = set()
            if src_bm25.is_dir():
                known_names = {f.name for f in src_bm25.glob("*.py")}
            extra = [f for f in present_files if f.name not in known_names]
            modified = [
                f for f in present_files
                if f.name in known_names
                and (src_bm25 / f.name).exists()
                and _file_sha256(f) != _file_sha256(src_bm25 / f.name)
            ]
            if extra or modified:
                reasons = []
                if extra:
                    reasons.append(f"{len(extra)} unknown file(s)")
                if modified:
                    reasons.append(f"{len(modified)} user-modified file(s)")
                kept.append("_bm25/")
                print(
                    f"   kept  _bm25/  ({', '.join(reasons)}; use --force to override)",
                    file=sys.stderr,
                )
            else:
                if not dry_run:
                    shutil.rmtree(dst_bm25)
                removed.append("_bm25/")
        else:
            # force=True or no package source → remove unconditionally
            if not dry_run:
                shutil.rmtree(dst_bm25)
            removed.append("_bm25/")
    else:
        not_found.append("_bm25/")

    return {"removed": removed, "kept": kept, "not_found": not_found}


def cmd_uninstall(args: argparse.Namespace) -> int:
    print("== ctx-install --uninstall ==")
    force = getattr(args, "force", False)

    # 1. Remove hook registrations from settings.json.
    remove = []
    for spec in CTX_HOOKS:
        filename = spec[0]
        extra = spec[3] if len(spec) >= 4 else None
        remove.append(_hook_entry(filename, extra)["command"])

    result = unpatch_settings(CLAUDE_SETTINGS, remove, dry_run=args.dry_run)
    print(result.summary())
    if not result.ok:
        return 5

    print("\nCTX hooks removed from settings.json.")

    # 2. Clean up hook files and _bm25/ directory.
    print("\nCleaning up hook files …")
    cleanup = _cleanup_hook_files(force=force, dry_run=args.dry_run)

    prefix = "(dry-run) " if args.dry_run else ""
    for name in cleanup["removed"]:
        print(f"   {prefix}removed  {name}")
    for name in cleanup["not_found"]:
        print(f"   not found  {name}  (already gone)")

    if cleanup["kept"]:
        print(
            f"\n  {len(cleanup['kept'])} file(s) kept due to user modification"
            " — re-run with --force to remove."
        )

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print("== ctx-install status ==")
    print(f"Settings: {CLAUDE_SETTINGS}  ({'present' if CLAUDE_SETTINGS.exists() else 'MISSING'})")
    print(f"Hooks dir: {CLAUDE_HOOKS_DIR}")

    # Hook files
    ok, found, missing = step_verify_hooks_present()
    print(f"\nHook files: {len(found)}/{len(CTX_HOOKS)} present")
    for f in found:
        size = (CLAUDE_HOOKS_DIR / f).stat().st_size
        print(f"   ✓ {f}  ({size} bytes)")
    for f in missing:
        print(f"   ✗ {f}  (missing)")

    # Settings registration
    settings = _load(CLAUDE_SETTINGS)
    installed_cmds = []
    for event, entries in settings.get("hooks", {}).items():
        for entry in entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if any(f in cmd for f, *_ in CTX_HOOKS):
                    installed_cmds.append((event, cmd))
    print(f"\nRegistered in settings.json: {len(installed_cmds)}/{len(CTX_HOOKS)} commands")
    for event, cmd in installed_cmds:
        print(f"   ✓ {event}: {cmd[:80]}")

    # Last injection
    inj = Path.home() / ".claude" / "last-injection.json"
    if inj.exists():
        age = time.time() - inj.stat().st_mtime
        print(f"\nlast-injection.json: age {age/60:.1f} min")
    else:
        print(f"\nlast-injection.json: absent (no hook fire yet)")

    # Daemon files
    print(f"\nDaemons ({CLAUDE_VAULT_DIR}):")
    import socket as _socket
    for daemon in CTX_DAEMONS:
        dst = CLAUDE_VAULT_DIR / daemon
        if not dst.is_file():
            print(f"   ✗ {daemon}  (missing — semantic layer disabled)")
            continue
        # Probe socket liveness
        sock_name = daemon.replace(".py", ".sock")
        sock_path = CLAUDE_VAULT_DIR / sock_name
        alive = False
        if sock_path.exists():
            try:
                s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect(str(sock_path))
                s.close()
                alive = True
            except Exception:
                pass
        status = "running" if alive else "stopped"
        print(f"   {'✓' if alive else '○'} {daemon}  ({status})")

    # Stale path check (CLAUDE_PLUGIN_ROOT update bug — anthropics/claude-code#18517)
    stale = []
    for event, cmd in installed_cmds:
        if "CLAUDE_PLUGIN_ROOT" not in cmd and ".claude/hooks/" not in cmd:
            # Absolute versioned path like /home/user/.claude/plugins/ctx@0.1.0/...
            if "/plugins/" in cmd and cmd.endswith(".py"):
                stale.append(cmd)
    if stale:
        print(f"\n  WARNING: {len(stale)} hook(s) may have stale plugin paths (after /plugin update).")
        print(f"  Fix: run `/plugin install ctx` (not /plugin update) to re-expand paths.")
        print(f"  Or: run `ctx-install` to re-patch settings.json with ~/.claude/hooks/ paths.")

    return 0


# ─────────────────────── main ───────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        prog="ctx-install",
        description="Install CTX hooks into Claude Code settings.json (atomic, backup-first).",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would change; touch no files.")
    p.add_argument("--uninstall", action="store_true",
                   help="Remove CTX hook registrations from settings.json and clean up hook files.")
    p.add_argument("--force", action="store_true",
                   help="With --uninstall: remove hook files unconditionally (skip hash check).")
    p.add_argument("--force-hooks", action="store_true",
                   help="Overwrite existing hook files unconditionally (no hash check).")
    p.add_argument("--no-update-hooks", action="store_true",
                   help="Skip existing hook files even if outdated (legacy behaviour).")
    p.add_argument("command", nargs="?", default=None,
                   help="Optional: 'status' to check current install state.")
    args = p.parse_args()

    if args.command == "status":
        return cmd_status(args)
    if args.uninstall:
        return cmd_uninstall(args)
    return cmd_install(args)


if __name__ == "__main__":
    sys.exit(main())
