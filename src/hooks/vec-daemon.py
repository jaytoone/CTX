#!/usr/bin/env python3
"""
vec-daemon.py — Unix socket daemon for fast vector queries.
Loads multilingual-e5-small once, then serves embedding requests
via a Unix domain socket. chat-memory.py connects with 0.3s timeout.

Protocol (line-oriented JSON over Unix socket):
  Request:  {"q": "query text"}\n
  Response: {"ok": true, "emb": [0.1, 0.2, ...]}\n  (384 floats)
  Response: {"ok": false, "error": "..."}\n

Usage:
  python3 vec-daemon.py &          # start in background
  python3 vec-daemon.py --stop     # create stop file
"""
import sys, os, json, socket, threading, time, struct
from pathlib import Path

SOCKET_PATH = Path.home() / ".local/share/claude-vault/vec-daemon.sock"
PID_FILE    = Path.home() / ".local/share/claude-vault/vec-daemon.pid"
STOP_FILE   = Path.home() / ".local/share/claude-vault/vec-daemon.stop"
MODEL_NAME  = "intfloat/multilingual-e5-small"

if "--stop" in sys.argv:
    STOP_FILE.write_text("stop")
    print("Stop file written.")
    sys.exit(0)

# Guard: exit if already running
if PID_FILE.exists():
    try:
        existing_pid = int(PID_FILE.read_text().strip())
        os.kill(existing_pid, 0)
        print(f"[vec-daemon] Already running (PID {existing_pid}). Exiting.")
        sys.exit(0)
    except (ProcessLookupError, ValueError):
        pass  # stale PID file, continue

def load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def handle_client(conn: socket.socket, model):
    """Handle one client connection."""
    try:
        conn.settimeout(5.0)
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf += chunk
        line = buf.split(b"\n")[0]
        req = json.loads(line.decode("utf-8"))
        q = req.get("q", "")
        if not q:
            raise ValueError("empty query")

        # Add query prefix for asymmetric embedding
        text = "query: " + q[:1000]
        emb = model.encode([text], normalize_embeddings=True)[0]
        resp = json.dumps({"ok": True, "emb": emb.tolist()}) + "\n"
        conn.sendall(resp.encode("utf-8"))
    except Exception as e:
        try:
            resp = json.dumps({"ok": False, "error": str(e)}) + "\n"
            conn.sendall(resp.encode("utf-8"))
        except Exception:
            pass
    finally:
        conn.close()


def main():
    t0 = time.time()
    print(f"[vec-daemon] Loading {MODEL_NAME}...", flush=True)
    model = load_model()
    print(f"[vec-daemon] Model ready in {time.time()-t0:.1f}s", flush=True)

    # Clean up stale socket
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    # Write PID
    PID_FILE.write_text(str(os.getpid()))

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCKET_PATH))
    srv.listen(5)
    srv.settimeout(1.0)  # 1s accept timeout for stop-check loop
    print(f"[vec-daemon] Listening on {SOCKET_PATH}", flush=True)

    while True:
        if STOP_FILE.exists():
            print("[vec-daemon] Stop file detected. Shutting down.")
            STOP_FILE.unlink()
            break
        try:
            conn, _ = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, model), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[vec-daemon] Accept error: {e}", flush=True)

    srv.close()
    SOCKET_PATH.unlink(missing_ok=True)
    PID_FILE.unlink(missing_ok=True)
    print("[vec-daemon] Stopped.")


if __name__ == "__main__":
    main()
