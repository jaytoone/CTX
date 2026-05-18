"""ctx-install — one-command CTX hook installer for Claude Code.

Usage:
    ctx-install                   # install / activate (idempotent)
    ctx-install --dry-run         # show what would change; touch nothing
    ctx-install --uninstall       # remove CTX hooks from settings.json
    ctx-install --no-seed         # skip git history vault pre-seeding
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
import sqlite3
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


# Feature-presence markers: if a hook file exists in dst but lacks its marker,
# treat it as outdated and overwrite (with .pre-upgrade.bak backup).
# Prevents upgraders from pre-telemetry CTX permanently missing _auto_upload_row.
_HOOK_REQUIRED_MARKERS = {
    "utility-rate.py": "_auto_upload_row",   # telemetry auto-upload
}


def step_copy_hooks(dry_run: bool = False) -> tuple[int, int, list[str]]:
    """Copy hook files from the installed package to ~/.claude/hooks/.
    Returns (copied, skipped, errors)."""
    src = _pkg_hooks_dir()
    if src is None:
        return 0, 0, ["Package hooks dir not found — run `pip install ctx-retriever` first"]

    CLAUDE_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    copied, skipped, errors = 0, 0, []

    # Hook filenames we care about (from CTX_HOOKS + telemetry helper)
    hook_files = [spec[0] for spec in CTX_HOOKS] + ["_ctx_telemetry.py", "utility-rate.py"]

    for fname in hook_files:
        src_file = src / fname
        dst_file = CLAUDE_HOOKS_DIR / fname
        if not src_file.is_file():
            continue  # optional file (utility-rate.py not in CTX_HOOKS list)
        if dst_file.is_file():
            # If outdated (missing required feature marker), overwrite with backup.
            required = _HOOK_REQUIRED_MARKERS.get(fname)
            if required:
                try:
                    existing = dst_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    existing = ""
                if required not in existing:
                    if not dry_run:
                        try:
                            backup = dst_file.with_suffix(dst_file.suffix + ".pre-upgrade.bak")
                            shutil.copy2(dst_file, backup)
                            shutil.copy2(src_file, dst_file)
                            dst_file.chmod(0o755)
                            copied += 1
                            continue
                        except OSError as e:
                            errors.append(f"upgrade {fname}: {e}")
                            continue
                    else:
                        copied += 1
                        continue
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
            copied += 1  # count as would-copy in dry-run

    return copied, skipped, errors


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


# ─────────────────────── vault seed ───────────────────────

_VAULT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        project    TEXT
    );
    CREATE TABLE IF NOT EXISTS messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role       TEXT,
        content    TEXT,
        timestamp  TEXT
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
        USING fts5(content, content=messages, content_rowid=id);
    CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END;
"""


def step_seed_vault(
    dry_run: bool = False,
    project_dir: Path | None = None,
    max_commits: int = 500,
    force: bool = False,
) -> tuple[int, str]:
    """Pre-populate vault.db with git commit history so G1 recall fires in session 1.

    Idempotent: skips silently if this project was already seeded.
    Returns (n_commits_inserted, status_message).
    """
    if project_dir is None:
        project_dir = Path.cwd()

    # Require a git repo
    try:
        check = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=5,
        )
        if check.returncode != 0:
            return 0, f"not a git repo ({project_dir.name}) — vault seed skipped"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0, "git unavailable — vault seed skipped"

    # Stable, per-project session ID (safe to re-run ctx-install)
    project_hash = hashlib.sha1(str(project_dir).encode()).hexdigest()[:8]
    session_id = f"git-seed-{project_hash}"
    vault_db = CLAUDE_VAULT_DIR / "vault.db"

    if not dry_run:
        # Skip if already seeded for this project (unless force=True)
        if vault_db.exists() and not force:
            try:
                conn = sqlite3.connect(f"file:{vault_db}?mode=ro", uri=True, timeout=2.0)
                count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id=?", (session_id,)
                ).fetchone()[0]
                conn.close()
                if count > 0:
                    return count, f"already seeded ({count} commits) — skipping (use --reseed to refresh)"
            except Exception:
                pass  # vault doesn't exist yet or schema mismatch → proceed

    # Fetch git log (no-merges, subject + body)
    try:
        log = subprocess.run(
            ["git", "-C", str(project_dir), "log",
             "--pretty=format:%ai\x1f%s\x1f%b\x1e",
             f"--max-count={max_commits}", "--no-merges"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return 0, "git log timed out — vault seed skipped"

    commits: list[tuple[str, str, str]] = []  # (session_id, role, content, timestamp) → built below
    rows: list[tuple[str, str, str, str]] = []
    for entry in log.stdout.split("\x1e"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("\x1f", 2)
        if len(parts) < 2:
            continue
        timestamp, subject = parts[0].strip(), parts[1].strip()
        body = parts[2].strip() if len(parts) > 2 else ""
        if len(subject) < 5:
            continue
        content = f"[git] {subject}"
        if body:
            content += f"\n{body}"
        rows.append((session_id, "assistant", content, timestamp))

    if not rows:
        return 0, "no commits found — vault seed skipped"

    if dry_run:
        return len(rows), f"would seed {len(rows)} commits into {vault_db}"

    CLAUDE_VAULT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(vault_db), timeout=5.0)
        conn.executescript(_VAULT_SCHEMA)

        if force:
            # FTS5-safe delete: remove index entries before deleting rows
            old = conn.execute(
                "SELECT id, content FROM messages WHERE session_id=?", (session_id,)
            ).fetchall()
            for row_id, content in old:
                conn.execute(
                    "INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', ?, ?)",
                    (row_id, content),
                )
            conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))

        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, project) VALUES (?, ?)",
            (session_id, str(project_dir)),
        )
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        return 0, f"vault write failed: {exc}"

    return len(rows), f"seeded {len(rows)} commits → {vault_db}"


# ─────────────────────── commands ───────────────────────

def cmd_install(args: argparse.Namespace) -> int:
    print("== ctx-install ==")
    print(f"Target: {CLAUDE_SETTINGS}")
    print(f"Hooks dir: {CLAUDE_HOOKS_DIR}\n")

    # 1. Copy hook files from package (if not already present)
    copied, skipped, errors = step_copy_hooks(dry_run=args.dry_run)
    print(f"1/4 hook files:  copied={copied}  already-present={skipped}")
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

    # 5. Seed vault.db with git history (cold-start fix)
    if not getattr(args, "no_seed", False):
        n_seeded, seed_msg = step_seed_vault(
            dry_run=args.dry_run,
            max_commits=args.max_commits,
            force=getattr(args, "reseed", False),
        )
        print(f"\n5/5 vault seed:  {seed_msg}")
    else:
        print("\n5/5 vault seed:  skipped (--no-seed)")

    print("\n" + "=" * 50)
    print("CTX installed. Restart Claude Code to activate.")
    print("Verify: claude -p 'list recent decisions'")
    if d_copied:
        print("\nSemantic layer (vec-daemon + bge-daemon) deployed.")
        print("To activate: nohup python3 ~/.local/share/claude-vault/vec-daemon.py &")
        print("  Optional BGE rerank: nohup python3 ~/.local/share/claude-vault/bge-daemon.py &")
        print("  (vec-daemon starts automatically on next Claude Code session)")
    print("=" * 50)
    print()
    print("CTX shares anonymous usage stats automatically (k-anonymized, no code/text).")
    print("  ctx-telemetry                 # preview what's shared")
    print("  touch ~/.claude/ctx-telemetry-revoke   # opt-out")
    print("  Schema: https://github.com/jaytoone/CTX#telemetry-opt-in-local-only")

    # Install-time ping — count the install itself, before any session data.
    # Independent of session-end flush so single-session/never-return users still appear.
    _send_install_ping()
    return 0


# Turso config — must stay in sync with src/hooks/utility-rate.py _TURSO_*
_TURSO_DB_URL = "https://frwp-jaytoone.aws-us-west-2.turso.io"
_TURSO_WRITE_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NzYxMzQ4MjksImlkIjoiMDE5Y2VjYzIt"
    "MWMwMS03MGNjLWJjMzktMTA2NjlhODhlOTgxIiwicmlkIjoiNTgwNzNiZjgtNDc4My00YjhiLWI4ZjAt"
    "ZDY0ZWU2ZDRkYzcxIn0.AjxxxM0v4fcz0mONEdpI2t6ulp1NvUM87FLMUuWyvFa0wx0qavjzBGf6HnS9B"
    "--DepuT0EbhwRRuc9HHRTGXAA"
)
_REVOKE_FILE = Path.home() / ".claude" / "ctx-telemetry-revoke"


def _compute_install_user_id() -> str:
    """Reproduce the same user_id_hash that utility-rate.py would generate.
    Source: SHA256(machine_id + install_month_epoch). Same algorithm used for sessions
    so the install ping clusters with a user's later session rows."""
    import hashlib
    machine_id = ""
    for mid_path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            machine_id = open(mid_path).read().strip()
            break
        except OSError:
            pass
    if not machine_id:
        import socket
        machine_id = socket.gethostname()
    claude_dir = Path.home() / ".claude"
    try:
        install_ts = int(claude_dir.stat().st_mtime) if claude_dir.exists() else 0
    except OSError:
        install_ts = 0
    from datetime import datetime, timezone
    d = datetime.fromtimestamp(install_ts, tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0)
    install_month_epoch = str(int(d.timestamp()))
    return hashlib.sha256(f"{machine_id}:{install_month_epoch}".encode()).hexdigest()[:16]


def _send_install_ping() -> None:
    """Fire-and-forget INSTALL_PING row to Turso so installs are counted even before
    any Claude Code session ends. Silent on failure — never breaks the install flow."""
    if _REVOKE_FILE.exists():
        return
    try:
        import urllib.request as _req
        import time as _time
        from datetime import date as _date
        try:
            import importlib.metadata as _meta
            ctx_ver = _meta.version("ctx-retriever")
        except Exception:
            ctx_ver = "unknown"
        sql = (
            "INSERT INTO ctx_session_aggregates "
            "(schema_version, user_id, session_id_hash, ts_date, total_turns, "
            "session_outcome, ctx_version) VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        args_list = [
            {"type": "text",    "value": "v1.7"},
            {"type": "text",    "value": _compute_install_user_id()},
            {"type": "text",    "value": f"install:{int(_time.time())}"},
            {"type": "text",    "value": str(_date.today())},
            {"type": "integer", "value": "0"},
            {"type": "text",    "value": "INSTALL_PING"},
            {"type": "text",    "value": ctx_ver},
        ]
        payload = json.dumps({"requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": args_list}}
        ]}).encode()
        token = _TURSO_WRITE_TOKEN.replace("\n", "")
        req = _req.Request(
            f"{_TURSO_DB_URL}/v2/pipeline", data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        with _req.urlopen(req, timeout=8) as resp:
            json.load(resp)
    except Exception:
        pass  # silent — never break install on telemetry failure


def cmd_uninstall(args: argparse.Namespace) -> int:
    print("== ctx-install --uninstall ==")
    # Build list of commands to remove (matching what install would have added)
    remove = []
    for spec in CTX_HOOKS:
        filename = spec[0]
        extra = spec[3] if len(spec) >= 4 else None
        remove.append(_hook_entry(filename, extra)["command"])

    result = unpatch_settings(CLAUDE_SETTINGS, remove, dry_run=args.dry_run)
    print(result.summary())
    if result.ok:
        print("\nCTX hooks removed from settings.json.")
        print("(Hook files at ~/.claude/hooks/ NOT deleted — remove manually if desired.)")
        return 0
    return 5


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

    # Pro status
    try:
        from ctx_retriever.pro.gate import ProGate
        gate = ProGate()
        if gate.is_active():
            info = gate.info()
            email = info.get("email") or "(no email)"
            tier = info.get("tier", "pro")
            print(f"\nPro: active (tier={tier}, email={email})")
        else:
            print("\nPro: free  (no license -- run `ctx-pro info` to learn about Pro features)")
    except Exception:
        pass

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
                   help="Remove CTX hook registrations from settings.json.")
    p.add_argument("--silent", action="store_true",
                   help="Suppress all output (used by autoinstall .pth trigger).")
    p.add_argument("--no-seed", action="store_true",
                   help="Skip vault pre-seeding with git history.")
    p.add_argument("--reseed", action="store_true",
                   help="Force re-seed vault even if already seeded (refreshes after new commits).")
    p.add_argument("--max-commits", type=int, default=500,
                   help="Max commits to seed into vault (default: 500).")
    p.add_argument("command", nargs="?", default=None,
                   help="Optional: 'status' to check current install state.")
    args = p.parse_args()

    if args.command == "status":
        return cmd_status(args)
    if args.uninstall:
        return cmd_uninstall(args)
    if getattr(args, "silent", False):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            args.no_seed = True  # silent mode skips slow vault seed
            rc = cmd_install(args)
        return rc
    return cmd_install(args)


if __name__ == "__main__":
    sys.exit(main())
