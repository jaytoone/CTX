"""Auto-wires CTX hooks on first Python startup after pip install.

Invoked by ctx_retriever_autoinstall.pth placed in site-packages.
Design goals:
  - < 1 ms overhead after initial install (flag-file fast exit)
  - Never raises — a broken autoinstall must not break Python startup
  - Runs ctx-install in the foreground (once) then sets flag
  - Respects CLAUDE_CTX_NO_AUTOINSTALL=1 env-var opt-out
  - Prints one-time notice on first run (Homebrew pattern)
  - CTX_TELEMETRY_DEBUG=1 prints payload to stderr before upload
"""
import os
from pathlib import Path

_HOME = Path.home()
_FLAG = _HOME / ".claude" / "ctx-autoinstall-done"
_NOTICED_FLAG = _HOME / ".claude" / "ctx-telemetry-noticed"
_REVOKE = _HOME / ".claude" / "ctx-telemetry-revoke"


def _already_wired() -> bool:
    settings = _HOME / ".claude" / "settings.json"
    try:
        return "utility-rate.py" in settings.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False


def _print_notice() -> None:
    """Print one-time telemetry notice (shown only on first run, then silent)."""
    if _NOTICED_FLAG.exists() or _REVOKE.exists():
        return
    if os.environ.get("CTX_TELEMETRY_REVOKE"):
        return
    try:
        import sys
        sys.stderr.write(
            "[CTX] Anonymous usage stats will be collected. "
            "Opt out: ctx-telemetry disable  |  "
            "Details: github.com/jaytoone/CTX/blob/master/PRIVACY.md\n"
        )
        _NOTICED_FLAG.touch()
    except Exception:
        pass


def _run() -> None:
    # Fast exit: flag already set means we ran successfully before
    if _FLAG.exists():
        return
    # Env-var opt-out
    if os.environ.get("CLAUDE_CTX_NO_AUTOINSTALL"):
        return
    # If hooks already wired (e.g. manual install), just set flag and exit
    if _already_wired():
        try:
            _FLAG.touch()
            _print_notice()
        except Exception:
            pass
        return
    # Not wired — print notice then run ctx-install --silent
    _print_notice()
    try:
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "ctx_retriever.cli.install", "--silent"],
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            try:
                _FLAG.touch()
            except Exception:
                pass
        elif os.environ.get("CTX_TELEMETRY_DEBUG"):
            sys.stderr.write(
                f"[CTX debug] ctx-install --silent exited {result.returncode}\n"
                f"  stderr: {result.stderr.decode(errors='replace')[:200]}\n"
            )
    except Exception:
        pass  # never raise during Python startup


try:
    _run()
except Exception:
    pass
