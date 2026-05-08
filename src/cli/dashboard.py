"""ctx-dashboard — launch the CTX telemetry dashboard server."""
from __future__ import annotations

import argparse
import importlib.resources
import subprocess
import sys
from pathlib import Path


def _server_path() -> Path:
    """Find dashboard server.py — installed package or dev src."""
    try:
        pkg = importlib.resources.files("ctx_retriever.dashboard")
        with importlib.resources.as_file(pkg) as p:
            srv = p / "server.py"
            if srv.exists():
                return srv
    except Exception:
        pass
    # Dev mode
    dev = Path(__file__).parent.parent / "dashboard" / "server.py"
    if dev.exists():
        return dev
    raise FileNotFoundError("ctx-dashboard server.py not found. Reinstall ctx-retriever.")


def main() -> None:
    parser = argparse.ArgumentParser(description="CTX telemetry dashboard")
    parser.add_argument("--port", type=int, default=8787, help="Port (default 8787)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    parser.add_argument("--public", action="store_true", help="Bind to Tailscale IP (100.x.x.x)")
    args = parser.parse_args()

    host = args.host
    if args.public:
        import subprocess as _sp, re as _re
        out = _sp.run(["ip", "addr", "show"], capture_output=True, text=True).stdout
        m = _re.search(r"(100\.\d+\.\d+\.\d+)/32", out)
        host = m.group(1) if m else "0.0.0.0"

    srv = _server_path()
    print(f"CTX Dashboard → http://{host}:{args.port}")
    print(f"Server:          {srv}")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "server:app",
         "--host", host, "--port", str(args.port), "--app-dir", str(srv.parent)],
        check=False,
    )


if __name__ == "__main__":
    main()
