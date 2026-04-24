# [expert-research-v2] Common port for all clients: Tailscale direct POST vs SSH RemoteForward
**Date**: 2026-04-24  **Skill**: expert-research-v2

## Original Question
Can multiple SSH clients share a single RemoteForward port on the server side so I don't need per-client port bookkeeping? WSL2 is the SSH server. Want one common port (e.g., 6789) for all clients.

## Web Facts
- [FACT-1] OpenSSH RemoteForward: if two clients both specify `RemoteForward 6789 ...`, the second fails with "bind: Address already in use". Cannot share the same listen port on the server side. (howtouselinux.com, github.com/hashicorp/vagrant/issues/12729)
- [FACT-2] `GatewayPorts clientspecified` in sshd_config allows client to choose bind IP. Clients CAN bind the same port to different interfaces/IPs (e.g., `RemoteForward 100.66.30.40:6789` vs `RemoteForward 127.0.0.1:6789`). But each client still needs a unique bind address. (snailbook.com, oneuptime.com)
- [FACT-3] Tailscale assigns each device a unique 100.64.0.0/10 IP; any tailnet member can HTTP POST directly to any other member's IP on any open port. No SSH tunnel required for traversal — WireGuard handles transport. (tailscale.com/kb/1257/connection-types)
- [FACT-4] Tailscale default ACL allows all devices under the same account to communicate freely on all ports. No explicit rules needed for single-user tailnets. (tailscale.com/docs/features/tailscale-ssh)
- [FACT-5] Windows HttpListener requires `netsh http add urlacl url=http://+:6789/` (wildcard) to bind non-localhost; Windows Defender Firewall needs an inbound rule via `New-NetFirewallRule -LocalPort 6789 -Direction Inbound -Action Allow`.

## Multi-Lens Analysis

### Lens 1: Domain Expert
1. **[GROUNDED]** Option A (GatewayPorts clientspecified) does NOT solve the bookkeeping — each client still needs a unique bind IP, which IS bookkeeping in a different form. Not a simplification.
2. **[GROUNDED]** Option B (GatewayPorts yes, single client binds wildcard) — only ONE client can bind `0.0.0.0:6789` at a time on the server. Other clients would collide. Fails.
3. **[GROUNDED]** Option C (message broker) works but adds a persistent service (Redis/MQTT) on WSL2, plus client-side broker library. Overkill for notifications.
4. **[GROUNDED]** Option D (direct Tailscale POST): since all clients have unique Tailscale IPs, WSL2 can POST to `http://{tailscale-ip}:6789/notify` for each client. ONE common port (6789) because each client has its own IP namespace. No RemoteForward, no SSH tunnel, no port registry.

### Lens 2: Devil's Advocate
- **[OVERCONFIDENT]** Option D requires the Windows listener to bind `0.0.0.0:6789` instead of `127.0.0.1:6789`, which increases surface area. On a single-user tailnet this is fine; on a shared tailnet, any tailnet member could fire notifications.
- **[MISSING]** Windows Firewall must allow inbound TCP 6789. This is a NEW setup step that doesn't exist in the current SSH-tunnel architecture.
- **[MISSING]** Without SSH tunnel as a persistence signal, WSL2 doesn't know which clients are "connected". It would need to enumerate clients via `tailscale status --json` or a static registry and just POST to all — some posts will fail for offline clients. Acceptable (curl with short timeout).
- **[MISSING]** The `netsh http add urlacl url=http://+:6789/` change requires admin privileges at setup time — already the case, so no regression.

### Lens 3: Practical Synthesizer
Option D is cleanest **if** we accept these trade-offs:
- Listener binds `0.0.0.0:6789` (one-time setup change in `client-setup-ps5.ps1`)
- Windows Firewall rule added by setup script
- WSL2 hooks enumerate tailnet clients and POST to each
- Port registry becomes a simple hostname/IP list (no port mapping)

Current SSH-RemoteForward approach is equivalent security (both Tailscale WireGuard and SSH are encrypted), and Option D is structurally simpler.

## Final Conclusion

### Direct Tailscale POST (Option D) — winning design

**Client setup changes** (`client-setup-ps5.ps1`):
```powershell
# Listener prefix: 127.0.0.1 → wildcard
$listener.Prefixes.Add("http://+:6789/")   # was: http://127.0.0.1:6789/

# URL ACL: wildcard instead of 127.0.0.1
netsh http add urlacl url=http://+:6789/ user=$env:USERNAME

# NEW: firewall rule
New-NetFirewallRule -DisplayName "Claude Notify 6789" -Direction Inbound `
                     -LocalPort 6789 -Protocol TCP -Action Allow `
                     -ErrorAction SilentlyContinue | Out-Null

# REMOVED: RemoteForward block in SSH config (no longer needed)
```

**WSL2 hook changes** (e.g., `windows-stop.sh`, `close-popup.sh`):
```bash
# Enumerate online Tailscale clients and POST directly
for ip in $(tailscale status --json 2>/dev/null | jq -r '.Peer[] | select(.Online==true and .OS=="windows") | .TailscaleIPs[0]'); do
    curl -sf -m 2 -X POST "http://${ip}:6789/notify" \
         -H 'Content-Type: application/json' \
         --data "$payload" >/dev/null 2>&1 || true
done
```

**Benefits over RemoteForward approach:**
- ONE common port (6789) for every client — zero port bookkeeping
- No `/next-port` allocation logic needed in setup server
- No SSH tunnel dependency — works even when VS Code Remote-SSH disconnects
- Notifications keep working between SSH sessions, during idle
- Simpler `client-setup-ps5.ps1` (remove SSH config block entirely)

**Trade-offs accepted:**
- Listener reachable by any tailnet member (acceptable for single-user tailnet)
- Requires Windows Firewall rule (one-time admin action)
- Offline clients → curl fails silently (safe, same as port-range broadcast behavior)

### Confidence: HIGH
Security parity (both use encrypted transport), structural simplicity clearly favors Option D, grounded in Tailscale's per-device IP allocation and P2P connectivity model.

### Remaining Uncertainties
- Tailscale direct UDP hole-punching may fail behind some symmetric NATs → falls back to DERP relay (still works, just slower). Negligible for localhost/LAN scenarios.

## Sources
- [OpenSSH port forwarding wiki (Ubuntu)](https://help.ubuntu.com/community/SSH/OpenSSH/PortForwarding)
- [Tailscale connection types](https://tailscale.com/kb/1257/connection-types)
- [SSH GatewayPorts explained (snailbook)](http://www.snailbook.com/faq/gatewayports.auto.html)
- [SSH bind tunnel to specific IP](https://oneuptime.com/blog/post/2026-03-20-ssh-bind-tunnel-specific-ipv4/view)
- [Vagrant race condition issue #12729](https://github.com/hashicorp/vagrant/issues/12729)
