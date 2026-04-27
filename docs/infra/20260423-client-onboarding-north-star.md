# Client Onboarding North Star — 3-spec contract

**Date**: 2026-04-23
**Purpose**: From a single bootstrap script on a new PC (Windows/Linux/Mac), the client should achieve the same capabilities as the existing remote PC (`100.121.173.91`) against this WSL2 server.

---

## The 3 specs

| # | Spec | Direction | Status |
|---|---|---|---|
| 1 | Popups — WSL hook events (notify/stop) appear on client | WSL → client | ✅ Working (pre-existing) |
| 2 | Clipboard — text selected on server CLI (zellij) lands on client's clipboard | WSL → client | ✅ Working (pre-existing) |
| 3 | Browser tunnel — `localhost:<PORT>` on client = WSL's `localhost:<PORT>` (same URL invariant) | client ← WSL | ✅ **Shipped this round** |

---

## Spec 1 — Popups

### Architecture
```
WSL hook (windows-notify.sh / windows-stop.sh)
  POST http://localhost:6789/notify
    │ (SSH RemoteForward 6789)
    ▼
Client's :6789 (claude-notify-listener.ps1 / notify-listener.py)
  Balloon / toast on client
```

### Server side (this WSL) — already in place
- `~/.claude/hooks/windows-notify.sh`, `windows-stop.sh` — fire on Stop, PermissionRequest events
- `CLAUDE_REMOTE_NOTIFY_URL: "http://localhost:6789/notify"` (settings.json env)
- `~/.claude/hooks/client-setup-ps5.ps1` — canonical Windows-client installer
- `~/.claude/hooks/notify-listener.py` — stdlib cross-OS alternative

### Client side — installed by `client-setup-ps5.ps1`
1. `claude-notify-listener.ps1` at `%USERPROFILE%\` — HTTPListener on `:6789`
2. Task Scheduler entry `ClaudeNotifyListener` — auto-start at login
3. `RemoteForward 6789 127.0.0.1:6789` in `~/.ssh/config` under `Host home-wsl`

---

## Spec 2 — Clipboard

### Architecture
```
zellij copy event (mouse-drag or keybind)
  copy_command ~/.local/bin/clip-to-remote.sh
    │ reads stdin
    ▼
  POST http://localhost:6789/clipboard
    │ (SSH RemoteForward 6789 — same tunnel as spec 1)
    ▼
Client's listener /clipboard endpoint
  Set-Clipboard (or clip.exe fallback)
```

### Server side — already in place
- `~/.config/zellij/config.kdl:378` — `copy_command "/home/jayone/.local/bin/clip-to-remote.sh"`
- `~/.local/bin/clip-to-remote.sh` — fire-and-forget POST to `:6789/clipboard`

### Client side — same listener as spec 1
- `claude-notify-listener.ps1:197` — `/clipboard` endpoint calls `Set-Clipboard`
- Falls back to `cmd /c "clip < $tmp"` if Session 0 `Set-Clipboard` fails
- `%LOCALAPPDATA%\claude-clip-bridge\pending.txt` — Session 1 daemon bridge file (for Session 0 → user session clipboard hand-off when needed)

---

## Spec 3 — Browser tunnel (same URL invariant)

### Problem statement
> "Client should access WSL's dev server at `http://localhost:3003` — **same URL**."

`tailscale serve` does **path-based routing**: `https://<tailnet-hostname>/dashboard → WSL:8787`. That breaks the same-URL contract (client must use a different URL). Wrong tool.

### Solution: SSH LocalForward
`LocalForward N 127.0.0.1:N` in client's `~/.ssh/config` under `Host home-wsl` makes client's `localhost:N` tunnel to WSL's `localhost:N`. Client uses identical URL; SSH transparently forwards.

### What's pre-declared (covers 90% of dev work)

```ssh-config
Host home-wsl
    ...
    LocalForward 3000 127.0.0.1:3000    # Next.js / React default
    LocalForward 3001 127.0.0.1:3001    # Next.js dev server
    LocalForward 3003 127.0.0.1:3003    # user-mentioned example
    LocalForward 4200 127.0.0.1:4200    # Angular default
    LocalForward 5000 127.0.0.1:5000    # Flask / uvicorn default
    LocalForward 5173 127.0.0.1:5173    # Vite default
    LocalForward 8000 127.0.0.1:8000    # FastAPI / Django default
    LocalForward 8080 127.0.0.1:8080    # HTTP common
    LocalForward 8787 127.0.0.1:8787    # CTX dashboard
    LocalForward 9000 127.0.0.1:9000    # Various dev tools
    ExitOnForwardFailure no             # tolerate port collisions on client side
```

### Dynamic port exposure (for ports not in the default list)

**Linux / Mac / WSL client:**
```bash
~/scripts/wsl-expose-client.sh 8888
# → reconnect SSH / VS Code Remote-SSH → http://localhost:8888 on client = WSL:8888
```

**Windows client:**
```powershell
~\scripts\wsl-expose-client.ps1 8888
# → reconnect SSH → http://localhost:8888 on client = WSL:8888
```

Both scripts:
- Idempotent (no-op if port already declared)
- Backup `~/.ssh/config` before edit
- Inject inside the `Host home-wsl` block (not at EOF)
- Refuse if bootstrap not yet run

---

## Full end-to-end flow for a new client

```
Step 1 (new client):  Run wsl-client-bootstrap.{ps1,sh}
  → Tailscale check
  → ssh-keygen
  → SSH config written (home-wsl with RemoteForward 6789 + 10 LocalForwards + home-pc)
  → Fetch + run client-setup-ps5.ps1 (popup listener, Task Scheduler, self-test)
  → Print pubkey

Step 2 (server): Receive pubkey, run register-client-key.sh
  → authorized_keys appended on WSL + Windows

Step 3 (new client): First SSH to home-wsl
  → All forwards activate
  → ssh home-wsl hostname → DESKTOP-8HIUJU8

Verify:
  → popup: curl -XPOST localhost:6789/notify -d '{"title":"t","message":"hi"}' on WSL → balloon on client
  → clipboard: zellij mouse-select on WSL → paste on client with Ctrl-V
  → browser: start `python3 -m http.server 3003` on WSL → http://localhost:3003 on client
```

---

## File index

| Side | File | Role |
|---|---|---|
| server | `~/.claude/hooks/windows-notify.sh`, `windows-stop.sh` | Spec 1 WSL side |
| server | `~/.local/bin/clip-to-remote.sh` | Spec 2 WSL side |
| server | `~/.config/zellij/config.kdl` | Wires zellij → clip-to-remote.sh |
| server | `~/.claude/hooks/client-setup-ps5.ps1` | Canonical Windows-client installer |
| server | `~/.claude/hooks/notify-listener.py` | stdlib cross-OS listener alternative |
| server | `~/scripts/wsl-client-bootstrap.{ps1,sh}` | New-client bootstrap (updated this round) |
| server | `~/scripts/wsl-expose-client.{ps1,sh}` | Dynamic-port expose CLI (new this round) |
| server | `~/scripts/register-client-key.sh` | Pubkey registrar |
| client | `%USERPROFILE%\claude-notify-listener.ps1` | Popup/clipboard receiver |
| client | `~/.ssh/config` | home-wsl + home-pc with forwards |
| client | Task `ClaudeNotifyListener` | Auto-start at login |
| client | Task `ClaudeNotifyTunnel` | Persistent SSH tunnel keeper |

---

## Security notes

- All forwards bind to `127.0.0.1` on both ends — no LAN exposure
- SSH authentication is pubkey-only (no password)
- Tailscale mesh is encrypted (WireGuard), tailnet ACL restricts to authorized members
- `ExitOnForwardFailure no` means if the client already has a local service on `:3000`, the SSH connection still works; the forward just doesn't bind (benign warning)

## Related
- [[projects/CTX/research/20260424-claude-client-bootstrap-session-summary|20260424-claude-client-bootstrap-session-summary]]
- [[projects/CTX/research/20260424-common-port-fanout-tailscale-vs-ssh|20260424-common-port-fanout-tailscale-vs-ssh]]
- [[projects/CTX/infra/20260423-wsl2-remote-tailscale-tunneling|20260423-wsl2-remote-tailscale-tunneling]]
- [[projects/CTX/research/20260424-windows-client-onboarding-simplification|20260424-windows-client-onboarding-simplification]]
- [[projects/CTX/research/20260424-mirrored-localhost-session-portability|20260424-mirrored-localhost-session-portability]]
- [[projects/CTX/research/20260411-auto-index-necessity-analysis|20260411-auto-index-necessity-analysis]]
- [[projects/CTX/decisions/20260326-path-derived-module-to-file|20260326-path-derived-module-to-file]]
