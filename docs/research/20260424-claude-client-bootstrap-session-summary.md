# Claude Client Bootstrap — 1-line Windows client onboarding (session summary)
**Date**: 2026-04-24  **Scope**: WSL2 hooks infrastructure (outside CTX project, related via same repo)

## Objective
Reduce Windows client onboarding from 4 manual steps (install OpenSSH, keygen, pubkey push, scp setup) to a single PowerShell line that sets up all 3 specs (popup / clipboard / browser tunnel).

## Final Result — true 1-line onboarding
```powershell
irm http://100.66.30.40:9955/bootstrap | iex
```
Covers Spec 1 (popup), Spec 2 (clipboard), Spec 3 (dynamic dev-server mirror) on any Tailscale-enrolled Windows client.

---

## Architecture evolution

### v1: SSH RemoteForward (retired)
Each client allocated a unique WSL2-side port (6789-6799) via `RemoteForward`. WSL2 hooks broadcast to the full port range on `localhost`.

**Problems:**
- Per-client port bookkeeping (registry file `client-ports.json`)
- SSH tunnel dependency — notifications died when VS Code Remote-SSH disconnected
- Port collision risk when multiple clients onboarded

### v2: Tailscale direct POST (shipped)
Each client binds `0.0.0.0:6789` on its own Tailscale IP. WSL2 hooks enumerate online Windows peers via `tailscale status --json` and POST directly to `http://{tailscale-ip}:6789/{endpoint}`.

**Wins:**
- One common port (6789) for all clients
- No port registry
- No SSH tunnel — works whenever client is online on tailnet
- Each client's Tailscale IP is its own socket namespace

**Required changes:**
- Listener: `http://127.0.0.1:6789/` → `http://+:6789/`
- URL ACL: wildcard (`netsh http add urlacl url=http://+:6789/`)
- Windows Firewall inbound rule for TCP 6789
- Task Scheduler `-RunLevel Highest` (needed for Spec 3 netsh portproxy)
- All WSL2 broadcast hooks switched from port-range loop to tailnet peer enumeration

**Related research:**
- `docs/research/20260424-windows-client-onboarding-simplification.md`
- `docs/research/20260424-common-port-fanout-tailscale-vs-ssh.md`

---

## Spec 3 — dynamic same-URL mirror (not hardcoded port list)

**Design decision:** reject pre-declared port lists (3000, 5173, 8000, ...) in favor of on-demand registration.

**Implementation:**
- Listener endpoints: `POST /expose {port: N}`, `POST /unexpose {port: N}`, `GET /exposed`
- Under the hood: `netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=N connectaddress=100.66.30.40 connectport=N`
- Result: client's `http://localhost:N` resolves to WSL2's `http://localhost:N` — **same URL on both sides**

**WSL2 CLI:**
```bash
wsl-expose 3003   # tailnet-wide: all online Windows peers get localhost:3003 → WSL2:3003
wsl-unexpose 3003
```

**Constraint:** netsh portproxy requires admin. Task Scheduler task registered with `-RunLevel Highest`. Task registration requires admin at bootstrap time.

**Verified on DESKTOP-8HIUJU8 and DESKTOP-BJOLBUL (jej98):**
```
127.0.0.1       3003        100.66.30.40    3003   (netsh portproxy rule created)
```

---

## Files changed (outside CTX repo — `~/.claude/` and `~/.local/`)

### Renamed
- `~/.claude/hooks/ctx-setup-server.py` → `~/.claude/hooks/claude-client-bootstrap.py`
- `~/.config/systemd/user/ctx-setup-server.service` → `~/.config/systemd/user/claude-client-bootstrap.service`

### Listener + setup (`~/.claude/hooks/client-setup-ps5.ps1`)
- Prefix: `http://127.0.0.1:6789/` → `http://+:6789/`
- `-RunLevel Limited` → `-RunLevel Highest`
- Added `netsh http add urlacl url=http://+:6789/`
- Added `New-NetFirewallRule` for port 6789
- Removed all SSH RemoteForward logic
- Added `/expose`, `/unexpose`, `/exposed` endpoints
- Added port-holder fallback kill (Get-NetTCPConnection → Stop-Process) before Start-ScheduledTask
- Reordered: URL ACL + Firewall registered BEFORE listener start (was after — caused silent listener deaths)

### WSL2 hook fan-out
- `~/.claude/hooks/windows-notify.sh`, `windows-stop.sh`, `close-popup.sh`, `~/.local/bin/clip-to-remote.sh`
  - Changed: `for port in $(seq 6789 6799); do curl localhost:$port ...`
  - To: `tailscale status --json | jq '.Peer[] | select(Online, OS==windows) | TailscaleIPs[0]' | while read ip; do curl $ip:6789 ...`

### New CLI (`~/.local/bin/`)
- `wsl-expose <port>` — tailnet fan-out `/expose`
- `wsl-unexpose <port>` — tailnet fan-out `/unexpose`

### Docs
- `~/.claude/CLAUDE.md` — Remote Notify Client Registry section rewritten
- `~/.claude/projects/-home-jayone-Project-CTX/memory/MEMORY.md` — architecture migration entries

---

## Pitfalls encountered and resolutions

### 1. PowerShell `irm | iex` parse error
**Problem:** `irm http://.../client-setup-ps5.ps1 | iex` failed to parse because the outer script contains a nested `@"..."@` heredoc whose contents include `[$cls]::SetWindowPos(...)` — `iex` tries to fully parse the string as PowerShell code.

**Fix:** `/bootstrap` endpoint returns a wrapper PS1 that uses `Invoke-WebRequest -OutFile` + `powershell -File` instead of `iex`.

### 2. `$listenerBody = @'...'@` premature close
**Problem:** The listener body contained a nested `Add-Type @'...using System...'@` inside the `Show-Square` function's `$psCode` heredoc. When embedded in the outer single-quoted `$listenerBody = @'...'@`, the inner `'@` on a line by itself closed the outer heredoc prematurely, turning lines 137+ into raw PowerShell code that failed to parse.

**Fix:** Replaced the inner `Add-Type @'...'@` with a single-line string + `-replace 'CLSNAME','$cls'` to avoid any `'@` at column 0 inside `$listenerBody`.

### 3. URL ACL order dependency
**Problem:** Bootstrap started the listener (step 3) BEFORE registering the URL ACL (step 4). Without the ACL, non-admin listener couldn't bind `http://+:6789/`, so it silently failed. Self-test passed only because the initial listener from earlier stable session was still running.

**Fix:** Reordered — URL ACL + Firewall rule now in step 3, listener start in step 4.

### 4. Old listener holds port 6789
**Problem:** After re-bootstrapping with new wildcard binding, old listener (bound to 127.0.0.1 only from previous version) is still running and holds the port. New listener fails with "다른 프로세스가 파일을 사용 중이기 때문에 프로세스가 액세스 할 수 없습니다".

**Fix:** Added explicit `Get-NetTCPConnection -LocalPort 6789 -State Listen` → `Stop-Process` fallback in the setup script before starting the new task.

### 5. Windows admin_authorized_keys quirk
**Problem:** `ssh Jayone@100.69.161.128` fails with "Permission denied" even after pushing pubkey to `~/.ssh/authorized_keys`. Jayone is in the Administrators group, so Windows OpenSSH ignores user-level authorized_keys and only reads `C:\ProgramData\ssh\administrators_authorized_keys`.

**Fix:** Push pubkey to `administrators_authorized_keys` with correct ACLs (`icacls /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F'`). Or, from WSL2, write directly to `/mnt/c/ProgramData/ssh/administrators_authorized_keys` (DrvFs allows rwxrwxrwx).

### 6. PowerShell over SSH console output crash
**Problem:** `Invoke-RestMethod` writes progress to console, which fails over non-interactive SSH with `"ReadConsoleOutput 0x5"` error.

**Fix:** `$ProgressPreference = 'SilentlyContinue'` + use `Invoke-WebRequest -OutFile` instead of piping.

### 7. Task Scheduler `Ready` vs `Running`
**Problem:** Listener dies shortly after bootstrap self-test when task was started via SSH session. Task state flips to `Ready` (not `Running` or `Queued`). `RestartCount=99` doesn't fire because the task "successfully completed" (exit 0 from session end).

**Fix (operational):** Manual `Start-ScheduledTask` brings it back up. **Root cause:** Task `-LogonType Interactive` bound to the SSH session. User-visible workaround: run bootstrap from a local interactive PowerShell session (the user's console) rather than SSH for persistence.

---

## Final client state (as of 2026-04-24)

| Client | IP | Spec 1 Popup | Spec 2 Clipboard | Spec 3 Tunnel |
|---|---|---|---|---|
| DESKTOP-8HIUJU8 (host) | 100.69.161.128 | ✓ | ✓ | ✓ |
| DESKTOP-BJOLBUL (jej98) | 100.81.207.35 | ✓ | ✓ | ✓ |
| DESKTOP-693UEOU (toomu) | 100.121.173.91 | ✓ | ✓ | ⚠ needs local admin re-run for spec 3 |
| DESKTOP-TI1C5VI (new PC) | 100.64.80.3 | offline | offline | offline |

---

## Why Tailscale SSH works for WSL2 but not Windows host

Tailscale SSH server is **Linux/macOS only** — depends on PAM + setuid. Windows auth uses LSA + impersonation tokens, which Tailscale hasn't implemented (tracked in tailscale/tailscale#14942). WSL2 is a full Linux kernel, so it runs Tailscale SSH natively. For Windows nodes, use standard OpenSSH over Tailscale IP (pubkey auth, same WireGuard transport).

---

## Related research documents
- `docs/research/20260424-windows-client-onboarding-simplification.md` — onboarding method comparison
- `docs/research/20260424-common-port-fanout-tailscale-vs-ssh.md` — why Tailscale direct beats SSH RemoteForward for multi-client
- `docs/research/20260424-mirrored-localhost-session-portability.md` — browser session portability across the mirror (cookies, Playwright storageState)

## Commands cheatsheet (WSL2)

```bash
# Fan-out health check
tailscale status --json | jq -r '.Peer[] | select(.Online and .OS=="windows") | .TailscaleIPs[0] + " " + .HostName' | while read ip host; do
    printf "%-18s %-20s " "$ip" "$host"
    curl -sf -m 3 "http://${ip}:6789/health" >/dev/null 2>&1 && echo "✓" || echo "✗"
done

# Spec 3: expose/unexpose a dev port
wsl-expose 3003    # all clients' localhost:3003 now mirror WSL2:3003
wsl-unexpose 3003

# Send a test notification to all
tailscale status --json | jq -r '.Peer[] | select(.Online and .OS=="windows") | .TailscaleIPs[0]' | while read ip; do
    curl -sf -X POST "http://${ip}:6789/notify" -H 'Content-Type: application/json' \
         --data '{"title":"test","message":"hello","kind":"notify"}'
done
```
