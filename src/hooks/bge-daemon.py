#!/usr/bin/env python3
"""
bge-daemon.py — Unix socket daemon for BGE cross-encoder reranking.
Loads BAAI/bge-reranker-v2-m3 once (~7s cold), then serves (query, docs) pairs
over a Unix domain socket. Mirror of vec-daemon.py pattern, but for rerank
instead of bi-encoder embedding.

Protocol (line-oriented JSON):
  Request:  {"query": "...", "docs": ["text1", "text2", ...]}\n
  Response: {"ok": true, "scores": [3.1, -2.0, ...]}\n   (raw logits, caller sigmoids)
  Response: {"ok": false, "error": "..."}\n

Why separate from vec-daemon:
  - Model class is different (CrossEncoder, not SentenceTransformer bi-encoder)
  - Inference call is different (predict pairs, not encode single texts)
  - VRAM footprint differs (~2GB vs ~500MB); keeping them separate means
    users without GPU still get vec-daemon and skip bge-daemon

Usage:
  python3 bge-daemon.py &          # start in background
  python3 bge-daemon.py --stop     # create stop file
  python3 bge-daemon.py --status   # show PID + uptime + health probe

Env vars:
  CTX_BGE_MODEL        — override model name (default BAAI/bge-reranker-v2-m3)
  CTX_BGE_DEVICE       — "cuda" / "cpu" (default: auto-detect)
  CTX_BGE_FP16         — "1" to load fp16 on GPU (halves VRAM; default "1")
"""
import sys, os, json, socket, threading, time
from pathlib import Path

SOCKET_PATH = Path.home() / ".local/share/claude-vault/bge-daemon.sock"
PID_FILE    = Path.home() / ".local/share/claude-vault/bge-daemon.pid"
STOP_FILE   = Path.home() / ".local/share/claude-vault/bge-daemon.stop"
LOG_FILE    = Path.home() / ".local/share/claude-vault/bge-daemon.log"
MODEL_NAME  = os.environ.get("CTX_BGE_MODEL", "BAAI/bge-reranker-v2-m3")

# ── control flags ──────────────────────────────────────────────
if "--stop" in sys.argv:
    STOP_FILE.write_text("stop")
    print("Stop file written.")
    sys.exit(0)

if "--status" in sys.argv:
    if not PID_FILE.exists():
        print("[bge-daemon] not running (no pid file)")
        sys.exit(1)
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        print(f"[bge-daemon] stale pid file (pid {pid} not alive)")
        sys.exit(1)
    # socket probe
    ok = False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(str(SOCKET_PATH))
        s.sendall(b'{"query":"ping","docs":["pong"]}\n')
        resp = b""
        while b"\n" not in resp:
            chunk = s.recv(4096)
            if not chunk: break
            resp += chunk
        data = json.loads(resp.split(b"\n")[0])
        ok = bool(data.get("ok"))
        s.close()
    except Exception as e:
        print(f"[bge-daemon] pid={pid} alive, but socket probe failed: {e}")
        sys.exit(2)
    print(f"[bge-daemon] pid={pid} alive, socket ok={ok}")
    sys.exit(0 if ok else 2)

# ── single-instance guard ──────────────────────────────────────
if PID_FILE.exists():
    try:
        existing_pid = int(PID_FILE.read_text().strip())
        os.kill(existing_pid, 0)
        print(f"[bge-daemon] Already running (PID {existing_pid}). Exiting.")
        sys.exit(0)
    except (ProcessLookupError, ValueError):
        pass   # stale PID file, continue

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def load_model():
    from sentence_transformers import CrossEncoder
    import torch
    device = os.environ.get("CTX_BGE_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
    kwargs = {"device": device, "trust_remote_code": False}
    # fp16 on GPU halves VRAM footprint; on CPU keeps fp32
    if device == "cuda" and os.environ.get("CTX_BGE_FP16", "1") == "1":
        try:
            # CrossEncoder exposes .model after __init__; reload in fp16 after ctor
            m = CrossEncoder(MODEL_NAME, **kwargs)
            m.model.half()
            log(f"loaded {MODEL_NAME} on {device} (fp16)")
            return m, device, "fp16"
        except Exception as e:
            log(f"fp16 failed ({e}); falling back to fp32")
    m = CrossEncoder(MODEL_NAME, **kwargs)
    log(f"loaded {MODEL_NAME} on {device} (fp32)")
    return m, device, "fp32"


def handle_client(conn: socket.socket, model):
    try:
        conn.settimeout(10.0)
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            if len(buf) > 10_000_000:   # 10MB request cap
                raise ValueError("request too large")
        line = buf.split(b"\n")[0]
        req = json.loads(line.decode("utf-8"))
        q = req.get("query", "")
        docs = req.get("docs", []) or []
        if not q:
            raise ValueError("empty query")
        if not docs:
            resp = json.dumps({"ok": True, "scores": []}) + "\n"
            conn.sendall(resp.encode("utf-8"))
            return
        if len(docs) > 500:
            raise ValueError("too many docs (max 500)")

        # Truncate docs to keep inference bounded
        pairs = [(q[:400], str(d)[:400]) for d in docs]
        t0 = time.time()
        scores = model.predict(pairs, show_progress_bar=False, batch_size=32)
        dt = (time.time() - t0) * 1000
        # raw logits — caller applies sigmoid/filter
        out = [float(s) for s in scores]
        resp = json.dumps({"ok": True, "scores": out, "latency_ms": round(dt, 1)}) + "\n"
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
    log(f"starting — loading {MODEL_NAME}")
    model, device, dtype = load_model()
    log(f"model ready in {time.time()-t0:.1f}s (device={device}, dtype={dtype})")

    # Warm-up pass to move weights to GPU & compile any JIT paths
    try:
        _ = model.predict([("warmup query", "warmup document")], show_progress_bar=False)
        log("warmup ok")
    except Exception as e:
        log(f"warmup failed: {e}")

    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    PID_FILE.write_text(str(os.getpid()))

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCKET_PATH))
    os.chmod(str(SOCKET_PATH), 0o600)
    srv.listen(8)
    srv.settimeout(1.0)
    log(f"listening on {SOCKET_PATH}")

    while True:
        if STOP_FILE.exists():
            log("stop file detected — shutting down")
            STOP_FILE.unlink()
            break
        try:
            conn, _ = srv.accept()
            t = threading.Thread(target=handle_client, args=(conn, model), daemon=True)
            t.start()
        except socket.timeout:
            continue
        except Exception as e:
            log(f"accept error: {e}")

    srv.close()
    SOCKET_PATH.unlink(missing_ok=True)
    PID_FILE.unlink(missing_ok=True)
    log("stopped")


if __name__ == "__main__":
    main()
