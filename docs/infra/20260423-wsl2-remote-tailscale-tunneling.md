# WSL2 ↔ Remote PC — Tailscale Tunneling Architecture

**Date**: 2026-04-23
**Scope**: End-to-end documentation of how the remote PC (`desktop-693ueou`) reaches services running inside WSL2 on the local Windows laptop (`desktop-8hiuju8`) over a Tailscale mesh network.
**Audience**: Anyone needing to diagnose, extend, or rebuild this setup from scratch.

---

## 1. High-level goal

Enable this workflow:

> "I sit at the remote PC and open VS Code → `Remote-SSH: Connect to Host → home-wsl` → I'm editing files inside the WSL2 guest running on my laptop, as if the WSL2 box were a server on my LAN."

And additionally:

> "I sit at the remote PC and open `https://desktop-8hiuju8.tailb5ab18.ts.net/` → the CTX dashboard running inside WSL2 on `127.0.0.1:8787` loads."

With three invariants:
- **Private**: only members of my tailnet can reach these services (no public exposure)
- **Durable**: works after Windows reboot, WSL shutdown, and from any tailnet node
- **Zero credentials in transit**: key-based auth everywhere, TLS terminated by Tailscale

---

## 2. Network topology

```
                          ┌─────────────────────────────────────────┐
                          │  TAILSCALE MESH (100.64.0.0/10 CGNAT)   │
                          │  Encrypted overlay, WireGuard transport │
                          └─────────────────────────────────────────┘
                                        ▲                  ▲
                                        │                  │
               ┌────────────────────────┘                  └─────────────────────────┐
               │                                                                      │
               ▼                                                                      ▼
┌───────────────────────────────────┐                              ┌──────────────────────────────────┐
│  REMOTE PC                         │                              │  LOCAL LAPTOP                     │
│  Windows                           │                              │  Windows + WSL2                   │
│  Host: desktop-693ueou             │                              │  Host: desktop-8hiuju8            │
│  User: toomu                       │                              │  User: Jayone                     │
│  Tailnet IP: 100.121.173.91        │                              │  Tailnet IP: 100.69.161.128       │
│                                    │                              │                                   │
│  ┌─────────────────────────────┐   │                              │  ┌────────────────────────────┐   │
│  │ VS Code (Remote-SSH)        │   │      SSH (:2222 via ts)      │  │ Windows OpenSSH Server     │   │
│  │  config: ~/.ssh/config      │───┼──────────────────────────────┼─▶│  (C:\WINDOWS\System32\      │   │
│  │  host = home-wsl            │   │                              │  │   OpenSSH\sshd.exe)         │   │
│  └─────────────────────────────┘   │                              │  └─────────┬──────────────────┘   │
│                                    │                              │            │                      │
│  ┌─────────────────────────────┐   │      HTTPS (:443 via ts)     │  ┌─────────▼──────────────────┐   │
│  │ Browser                     │   │                              │  │ tailscale serve proxy      │   │
│  │  → ts hostname              │───┼──────────────────────────────┼─▶│  (Tailscale daemon on Win) │   │
│  └─────────────────────────────┘   │                              │  └─────────┬──────────────────┘   │
│                                    │                              │            │                      │
└────────────────────────────────────┘                              │  ┌─────────▼──────────────────┐   │
                                                                    │  │ netsh portproxy :2222      │   │
                                                                    │  │  → WSL-IP:22               │   │
                                                                    │  └─────────┬──────────────────┘   │
                                                                    │            │                      │
                                                                    │  ┌─────────▼──────────────────┐   │
                                                                    │  │ WSL2 guest (Ubuntu)        │   │
                                                                    │  │  - sshd on :22             │   │
                                                                    │  │  - CTX dashboard on :8787  │   │
                                                                    │  │  - user: jayone            │   │
                                                                    │  └────────────────────────────┘   │
                                                                    └───────────────────────────────────┘
```

---

## 3. The two flows, end-to-end

### 3.1 Flow A — SSH into WSL for VS Code Remote-SSH

```
remote PC                             Windows laptop                           WSL2
─────────                             ──────────────                           ────
1. VS Code resolves `home-wsl`
   from C:\Users\toomu\.ssh\config
        │
        │ Match-exec pre-check fires (see §4)
        ▼
2. ssh.exe opens TCP to
   100.69.161.128 port 2222
                          ─────────────▶  Tailscale WireGuard encapsulates;
                                          routes on overlay; decaps at Windows side
                                                       │
                                                       ▼
                                          sshd on :22 already serving?
                                                       │
                                     ┌─────── NO ──────┴────── YES ───────┐
                                     ▼                                     ▼
                                  Match-exec                          netsh portproxy
                                  already woke                        forwards :2222 → :22
                                  WSL via §4                                │
                                     │                                      ▼
                                     └──────────────────┬─────────▶ sshd auth (pubkey, id_ed25519)
                                                        │                   │
                                                        ▼                   ▼
                                                    Session established, bash or VS Code server runs
```

### 3.2 Flow B — HTTPS to CTX dashboard

```
remote PC                                    Windows laptop                           WSL2
─────────                                    ──────────────                           ────
1. Browser: https://desktop-8hiuju8.tailb5ab18.ts.net/
        │
        │ Tailscale MagicDNS resolves hostname → 100.69.161.128
        │ TLS cert issued by Tailscale (LetsEncrypt ACME on tailnet)
        ▼
2. TCP :443 opens
                          ─────────────▶  Windows Tailscale daemon terminates TLS
                                          Consults `tailscale serve` config:
                                              path "/"  →  proxy to  http://localhost:8787
                                                       │
                                                       ▼
                                          WSL2 localhost-forwarding translates
                                          Windows-localhost:8787 → WSL-eth0:8787
                                                       │
                                                       ▼
                                                   FastAPI server (uvicorn)
                                                   responds with HTML/API
```

---

## 4. Component-by-component detail

### 4.1 Tailscale on Windows

- **Role**: mesh network membership + tunnel termination
- **Install**: pre-existing, version 1.96.3, logged in as `be2jay67@gmail.com`
- **Identity on tailnet**: `desktop-8hiuju8.tailb5ab18.ts.net` → `100.69.161.128` (IPv4) + `fd7a:115c:a1e0::8d01:a182` (IPv6)
- **Important capabilities enabled on tailnet**:
  - `serve` feature — allows publishing local HTTP services to tailnet with auto-TLS
  - MagicDNS — `<hostname>.<tailnet>.ts.net` resolves without external DNS
  - HTTPS certificates — Tailscale issues Let's Encrypt certs for MagicDNS hostnames
- **How to query state** (from this WSL via interop):
  ```bash
  TS='/mnt/c/Program Files/Tailscale/tailscale.exe'
  "$TS" status             # all peers on tailnet
  "$TS" ip                 # this node's tailnet IPs
  "$TS" serve status       # what's published
  ```

### 4.2 Windows OpenSSH Server

- **Role**: terminates inbound SSH from `toomu@remote PC` on Tailscale port 22
- **Path**: `C:\WINDOWS\System32\OpenSSH\sshd.exe`
- **Service**: `sshd` (Windows service), StartupType=Automatic
- **Auth**: public-key only (`id_ed25519.pub` of WSL's `jayone` was appended to `C:\Users\Jayone\.ssh\authorized_keys` out-of-band). Password auth exists as fallback.
- **Config**: `C:\ProgramData\ssh\sshd_config` (stock Windows defaults)
- **Listen**: `0.0.0.0:22` (accepts any interface, including Tailscale's `100.69.161.128`)

### 4.3 netsh portproxy (:2222 → WSL-IP:22)

- **Role**: bridges Tailscale IP's port 2222 to WSL guest's sshd on port 22
- **Why needed**: WSL2 is a Hyper-V VM with NAT'd IP (172.18.18.240/20). Tailscale on Windows can't see 172.18.x.x directly — only the Windows host's interfaces. `netsh` forwards TCP traffic across the NAT boundary.
- **Current rule**:
  ```
  Listen on  100.69.161.128:2222  →  Connect to  172.18.18.240:22
  ```
- **Maintained by scheduled task `WSL_SSH_PortForward`** (boot trigger):
  - Script: `C:\scripts\wsl-portforward.ps1`
  - At Windows boot: `$wslIP = (wsl hostname -I).Trim().Split()[0]`
  - The `wsl hostname -I` call has a critical side-effect: **it wakes the WSL VM** (LxssManager boots it to answer the command). So the task transparently starts WSL on every Windows boot.
  - Then: `netsh interface portproxy add v4tov4 listenport=2222 listenaddress=100.69.161.128 connectport=22 connectaddress=$wslIP`
- **Query current state** (via double-hop SSH from this box):
  ```bash
  ssh toomu@100.121.173.91 'ssh home-pc netsh interface portproxy show v4tov4'
  ```

### 4.4 WSL2 guest configuration

- **Distro**: Ubuntu (WSL2, kernel 6.6.114.1-microsoft-standard-WSL2)
- **User**: jayone
- **IP**: `172.18.18.240/20` on eth0 (NAT'd by Windows)
- **Services running**:
  - `sshd` on `:22` (manages incoming SSH from netsh portforward)
  - CTX dashboard on `:8787` (FastAPI / uvicorn, bound to `127.0.0.1` by default)
  - `vec-daemon` on Unix socket `~/.local/share/claude-vault/vec-daemon.sock` (semantic rerank for chat-memory hook)
- **Keep-alive configuration** (`/mnt/c/Users/Jayone/.wslconfig`):
  ```ini
  [wsl2]
  memory=40GB
  processors=16
  localhostForwarding=true   # Windows localhost:PORT ↔ WSL localhost:PORT (see §4.5)
  vmIdleTimeout=-1           # NEVER auto-shutdown from idle
  ```
- **Boot hook** (`/etc/wsl.conf`): runs `/home/jayone/Project/Secure/forensic_capture_daemon.sh` on VM start (user's own infra, unrelated to Tailscale but documented here so it's not lost)

### 4.5 WSL2 localhost forwarding (for the HTTPS flow)

- **What it is**: a kernel-level mapping that makes `127.0.0.1:PORT` inside WSL visible as `localhost:PORT` on Windows host
- **Enabled by**: `localhostForwarding=true` in `.wslconfig`
- **Flow for CTX dashboard**:
  1. `uvicorn` binds to `127.0.0.1:8787` inside WSL
  2. WSL kernel mirrors that binding to Windows-side loopback
  3. Anything on Windows that hits `http://localhost:8787` gets routed to WSL's bound process
- **Why it matters for Tailscale serve**: Windows Tailscale daemon is a Windows process; it asks Windows networking for `localhost:8787`; gets answered by WSL. Zero config from the Tailscale side.

### 4.6 `tailscale serve` (Windows side, for HTTPS flow)

- **Command that set this up** (ran once via WSL interop):
  ```bash
  '/mnt/c/Program Files/Tailscale/tailscale.exe' serve --bg --https=443 http://localhost:8787
  ```
- **What it does**:
  - Registers a persistent serve config on Windows Tailscale daemon
  - Incoming HTTPS on `100.69.161.128:443` → decrypt TLS → HTTP GET to `localhost:8787` → WSL
- **Config storage**: Tailscale's internal state file on Windows (survives reboots)
- **Current state**:
  ```
  https://desktop-8hiuju8.tailb5ab18.ts.net (tailnet only)
  |-- /  proxy http://localhost:8787
  ```
- **Teardown**: `tailscale serve --https=443 off`

### 4.7 SSH config on remote PC (`C:\Users\toomu\.ssh\config`)

Current v3 contents:

```ssh-config
# Auto-wake WSL + wait until sshd inside WSL is actually listening.
# Prevents cold-boot races where VS Code Remote-SSH connects mid-boot.
# Note: commented out — current WSL auto-start + vmIdleTimeout=-1 makes it redundant.
#Match host home-wsl exec "ssh -o ConnectTimeout=5 home-pc wsl -d Ubuntu -- //home/jayone/scripts/wake-ready.sh"

Host home-wsl
    HostName 100.69.161.128
    Port 2222
    User jayone
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 3
    RemoteForward 6789 127.0.0.1:6789

Host home-pc
    HostName 100.69.161.128
    User Jayone
    IdentityFile ~/.ssh/id_ed25519
    RemoteForward 6789 127.0.0.1:6789
```

- `home-wsl` → direct path to WSL sshd via portforward
- `home-pc` → Windows host (useful for running `wsl.exe` remotely, or executing anything that requires Windows)
- `RemoteForward 6789` → forwards WSL's `:6789` back to the remote PC's claude-notify endpoint (bonus — not tunneling-related)

### 4.8 Match-exec wake path (currently DISABLED, documented for reference)

- **Purpose**: transparently wake WSL *if it's shut down* before a connection attempt
- **Mechanism**: SSH's `Match exec` runs a side-effect command before resolving the host config
- **Command**: `ssh -o ConnectTimeout=5 home-pc wsl -d Ubuntu -- //home/jayone/scripts/wake-ready.sh`
- **`//` prefix**: escapes MSYS path-translation (when Git Bash runs the config) so the Unix path reaches WSL unmangled. WSL bash treats `//` as `/` per POSIX, so the path resolves correctly.
- **`wake-ready.sh`** (`/home/jayone/scripts/wake-ready.sh`):
  ```bash
  #!/bin/bash
  # Waits up to 15s for sshd:22 to actually listen inside WSL.
  # Called from home-pc by SSH Match-exec wake chain.
  for i in {1..15}; do
    if ss -lnt sport = :22 2>/dev/null | grep -q LISTEN; then
      exit 0
    fi
    sleep 1
  done
  exit 1
  ```
- **Why it's commented out**: `vmIdleTimeout=-1` + the boot task's implicit wake mean the Match-exec is almost never needed. When active it triggered edge-case failures in VS Code Remote-SSH. See §7 for diagnosis.

### 4.9 Windows-side scheduled tasks

| Task | Trigger | Action | Purpose |
|---|---|---|---|
| `WSL_SSH_PortForward` | At Windows boot | Runs `wsl-portforward.ps1` | Sets up netsh rule + implicitly wakes WSL |
| `WSL_AutoStart_OnLogin` | At user logon | `wsl.exe -d Ubuntu -- true` | Ensures WSL is up whenever `Jayone` signs in |

Both are idempotent. No actions required unless you rebuild from scratch.

---

## 5. Key files + their locations

| File | Where | Role |
|---|---|---|
| `.wslconfig` | `C:\Users\Jayone\.wslconfig` | Sets `vmIdleTimeout=-1`, `localhostForwarding=true` |
| `wsl-portforward.ps1` | `C:\scripts\wsl-portforward.ps1` | Sets netsh portproxy at Windows boot |
| `sshd_config` | `C:\ProgramData\ssh\sshd_config` | Windows OpenSSH server config |
| `authorized_keys` (Windows user) | `C:\Users\Jayone\.ssh\authorized_keys` | Contains WSL jayone's pubkey for SSH-to-Windows |
| `authorized_keys` (WSL user) | `/home/jayone/.ssh/authorized_keys` | Contains remote PC toomu's pubkey for SSH-to-WSL |
| `id_ed25519` (remote PC) | `C:\Users\toomu\.ssh\id_ed25519` | Private key for all outbound SSH |
| Remote SSH config | `C:\Users\toomu\.ssh\config` | `home-wsl` + `home-pc` host definitions |
| `wake-ready.sh` | `/home/jayone/scripts/wake-ready.sh` | WSL-side readiness probe |
| WSL boot script | `/home/jayone/Project/Secure/forensic_capture_daemon.sh` | User's own daemon, runs at WSL boot |
| Tailscale serve state | Windows Tailscale daemon's internal state (not user-editable as a file) | Holds `:443 → localhost:8787` mapping |

---

## 6. Failure modes + recovery

### 6.1 "Remote VS Code can connect, but WSL feels unresponsive"

- **Check**: `ssh home-pc wsl hostname -I` from remote PC
- **If that fails**: WSL VM is down despite all safeguards. Run `ssh home-pc "wsl -d Ubuntu -- true"` — wakes it.

### 6.2 "Remote VS Code: timeout on connect"

- **Common cause**: netsh portforward points to stale WSL IP (WSL got new IP after reboot but portforward rule is old)
- **Verify**:
  ```bash
  ssh home-pc "wsl hostname -I"                            # current WSL IP
  ssh home-pc "netsh interface portproxy show v4tov4"      # what netsh points to
  ```
- **Fix** (run on Windows):
  ```powershell
  powershell -File C:\scripts\wsl-portforward.ps1
  ```

### 6.3 "Remote browser can reach Tailscale URL but 502 Bad Gateway"

- **Cause**: CTX dashboard died; `tailscale serve` config is intact but backend is gone
- **Fix**: `ssh home-wsl "bash ~/.claude/hooks/ctx-dashboard/launch.sh"` — dashboard restarts, 502 resolves

### 6.4 "Tailscale URL completely unreachable"

- **Check `tailscale serve status` on Windows**: should show `/ proxy http://localhost:8787`
- **If empty**: re-publish with `tailscale serve --bg --https=443 http://localhost:8787`
- **Check Tailscale ACL**: tailnet's HTTPS/serve feature must be enabled at `https://login.tailscale.com/admin/dns`

### 6.5 "14-second disconnect loop in VS Code Remote-SSH"

- **Root cause**: `remote.SSH.useLocalServer` and `remote.SSH.useExecServer` were enabled (experimental), triggering an exec-server handshake watchdog that kills SSH after ~14s when reconnect tokens don't match
- **Fix** (already applied to remote PC's `%APPDATA%\Code\User\settings.json`):
  ```json
  "remote.SSH.useLocalServer": false,
  "remote.SSH.useExecServer": false
  ```
- **Important**: VS Code must be fully restarted to pick up these settings (it caches them at startup)

### 6.6 "Match-exec wake breaks VS Code entirely"

- **Root cause**: still under investigation — isolated tests (`ssh home-wsl echo`) work perfectly with the Match-exec active; but VS Code's specific invocation pattern (`-T -D port home-wsl bash` with stdin) breaks when it fires
- **Current mitigation**: Match line commented out (leading `#`). Since `vmIdleTimeout=-1` + login auto-start task keep WSL alive 24/7, the wake is rarely needed.
- **Manual wake when truly needed** (after explicit `wsl --shutdown`):
  ```powershell
  ssh home-pc "wsl -d Ubuntu -- true"
  ```

### 6.7 Authentication failures

- **"Permission denied (publickey)"**: the remote box doesn't have your pubkey in `authorized_keys`
- **Windows OpenSSH admin-user quirk**: if target user is in Administrators group, keys go in `%ProgramData%\ssh\administrators_authorized_keys`, NOT `%USERPROFILE%\.ssh\authorized_keys`
- **Tailscale-level ACL**: check `https://login.tailscale.com/admin/acls` — default ACL allows all tailnet peers to reach each other, but custom ACLs can block specific paths

---

## 7. How each piece was tested and what was learned

### 7.1 Match-exec path mangling (MSYS vs cmd.exe)

- **Test**: ran `ssh home-pc wsl -d Ubuntu -- /home/jayone/scripts/wake-ready.sh` from Git Bash
- **Result**: bash error: `/bin/bash: line 1: C:/Program: No such file or directory`
- **Diagnosis**: MSYS bash auto-translated `/home/jayone/...` → `C:/Program Files/Git/home/jayone/...` because the leading `/` pattern-matches MSYS mount-point rules
- **Fix**: `//home/jayone/...` (double-leading-slash) suppresses MSYS translation; WSL bash still treats `//path` as `/path` per POSIX
- **Verified through**: Git Bash ssh.exe, Windows OpenSSH ssh.exe, and native Linux ssh — all three accept the `//` form and deliver the correct path to WSL

### 7.2 VS Code experimental SSH flags

- **Test**: enabled logs showed `remote.SSH.useLocalServer = true` / `useExecServer = true` paired with 14-second "closed gracefully" disconnect every session, "Unknown reconnection token (never seen)" in server log
- **Diagnosis**: these flags spawn an exec-server with a short client-server handshake watchdog (undocumented ~14s timeout); when the client side has a stale token (normal on reconnect), the watchdog expires
- **Fix**: set both to `false` in `%APPDATA%\Code\User\settings.json`, fully restart VS Code
- **Result**: stable sessions (30+ min uptime verified)

### 7.3 Cold-boot race

- **Test**: immediately after `wsl --shutdown`, first 2–3 SSH attempts drop at ~14s because WSL sshd is still initializing when SSH auth succeeds
- **Mitigation 1**: Match-exec calls `wake-ready.sh` which polls for `:22` listening before returning
- **Mitigation 2** (current preferred): `vmIdleTimeout=-1` + login auto-start task ensure WSL is always up → race never occurs in normal use

### 7.4 WSL localhost forwarding path

- **Test**: from Windows PowerShell: `Invoke-WebRequest http://localhost:8787/` → returned HTML from CTX dashboard (running in WSL)
- **Diagnosis**: `.wslconfig`'s `localhostForwarding=true` handles this transparently — no extra netsh rule needed for the HTTPS flow
- **Result**: Tailscale serve can proxy to `localhost:8787` as if it were a native Windows service

---

## 8. Rebuild from zero — exact steps if everything is lost

Assuming a new Windows laptop + a new remote PC, both with Tailscale installed and logged in to your tailnet:

1. **Install Windows OpenSSH** on laptop: `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0`, then `Start-Service sshd; Set-Service -Name sshd -StartupType Automatic`
2. **Install WSL2** with Ubuntu: `wsl --install -d Ubuntu`
3. **Write `.wslconfig`** (see §4.4) in `C:\Users\<you>\.wslconfig`
4. **Generate key pair on WSL jayone**: `ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519`
5. **Trust WSL key on Windows `Jayone` account**: append `~/.ssh/id_ed25519.pub` (from WSL) to `C:\Users\Jayone\.ssh\authorized_keys` (create if missing)
   - If Jayone is admin: append to `C:\ProgramData\ssh\administrators_authorized_keys` instead
   - `icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"`
6. **Write portforward script** at `C:\scripts\wsl-portforward.ps1` (see §4.3)
7. **Register scheduled task** `WSL_SSH_PortForward` (boot trigger, runs the portforward script)
8. **Register scheduled task** `WSL_AutoStart_OnLogin` (logon trigger, runs `wsl -d Ubuntu -- true`)
9. **On remote PC**: copy `id_ed25519` + `id_ed25519.pub` to `C:\Users\toomu\.ssh\`
10. **On remote PC**: create `C:\Users\toomu\.ssh\config` (contents from §4.7)
11. **On Windows laptop**: run `tailscale serve --bg --https=443 http://localhost:8787` (once the CTX dashboard is running)
12. **Verify full chain**: from remote PC, `ssh home-wsl hostname` → should return `DESKTOP-8HIUJU8` (actually WSL reports Windows hostname due to `/etc/hostname` sync)

---

## 9. Appendix — useful diagnostic one-liners

```bash
# (from remote PC) test the full VS Code SSH path without opening VS Code
ssh home-wsl "hostname && uname -a && ss -lnt sport = :22"

# (from remote PC) double-hop probe: remote → Windows → WSL
ssh home-pc "wsl -d Ubuntu -- hostname -I"

# (from this WSL) inspect Tailscale state
'/mnt/c/Program Files/Tailscale/tailscale.exe' status
'/mnt/c/Program Files/Tailscale/tailscale.exe' serve status

# (from this WSL, via interop) query netsh current state
'/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe' -Command "netsh interface portproxy show v4tov4"

# (from Windows PowerShell) verify localhost forwarding works
Invoke-WebRequest http://localhost:8787/ -UseBasicParsing | Select-Object StatusCode, RawContentLength
```
