"""Auto-wires CTX hooks on first Python startup after pip install.

Invoked by ctx_retriever_autoinstall.pth placed in site-packages.
Design goals:
  - < 1 ms overhead after initial install (flag-file fast exit)
  - Never raises — a broken autoinstall must not break Python startup
  - Runs ctx-install in the foreground (once) then sets flag
  - Respects CLAUDE_CTX_NO_AUTOINSTALL=1 env-var opt-out
"""
import os
from pathlib import Path


def _already_wired() -> bool:
    settings = Path.home() / ".claude" / "settings.json"
    try:
        return "utility-rate.py" in settings.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False


def _run() -> None:
    flag = Path.home() / ".claude" / "ctx-autoinstall-done"
    # Fast exit: flag already set means we ran successfully before
    if flag.exists():
        return
    # Env-var opt-out
    if os.environ.get("CLAUDE_CTX_NO_AUTOINSTALL"):
        return
    # If hooks already wired (e.g. manual install), just set flag and exit
    if _already_wired():
        try:
            flag.touch()
        except Exception:
            pass
        return
    # Not wired — run ctx-install --silent
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
                flag.touch()
            except Exception:
                pass
    except Exception:
        pass  # never raise during Python startup


try:
    _run()
except Exception:
    pass
