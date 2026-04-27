# [expert-research-v2] Windows Client Onboarding Simplification via Tailscale
**Date**: 2026-04-24  **Skill**: expert-research-v2

## Original Question
Simplest 1-2 PowerShell line onboarding for a new Windows PC that needs to pull and run
`client-setup-ps5.ps1` from WSL2 — reduce from the 4-step OpenSSH flow.

## Web Facts
- [FACT-1] `tailscale serve /path` serves files on tailnet; WSL2 userspace mode has limitations (tailscale.com/kb/1242)
- [FACT-2] Tailscale SSH server not supported on Windows clients (github.com/tailscale/tailscale/issues/14942)
- [FACT-3] `irm URL | iex` is the standard PowerShell zero-dependency bootstrapper (PowerShell 5+)
- [FACT-4] Tailscale Funnel exposes services to public internet, no client Tailscale required (tailscale.com/kb/1311)
- [FACT-5] `python3 -m http.server PORT --directory PATH` creates instant HTTP file server
- [FACT-6] Win10 1809+/Win11: `Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0` installs SSH client without internet
- [FACT-7] WSL2's 172.x.x.x IP is not routable externally, but Tailscale IP IS reachable if tailscale0 is a kernel tun interface

## Key Finding (Verified)
WSL2 has a real `tailscale0` kernel tun interface (not userspace networking), so `python3 -m http.server`
on WSL2 listening on `0.0.0.0` IS reachable at `100.66.30.40:PORT` from all tailnet members.
The new PC (100.64.80.3 = desktop-ti1c5vi) was already enrolled in the tailnet.

## Final Solution

### WSL2 side (one-time, auto-starts on boot)
```bash
# systemd user service: ~/.config/systemd/user/ctx-setup-server.service
# Serves ~/.claude/hooks/ at port 9955, auto-start on WSL2 boot
systemctl --user enable --now ctx-setup-server.service
```

### New PC (admin PowerShell) — 1 line
```powershell
irm http://100.66.30.40:9955/client-setup-ps5.ps1 | iex
```

That's it. No SSH, no key generation, no GitHub zip download, no password prompts.

## Ranked Options (from analysis)
| Rank | Method | Lines (new PC) | Prerequisites | Notes |
|------|--------|---------------|---------------|-------|
| 1 | `irm http://tailscale-ip:9955/... \| iex` | 1 | Tailscale on new PC | **Best** — zero friction |
| 2 | `ssh user@tailscale-ip "cat script.ps1" \| iex` | 1 | OpenSSH client (Win10 1809+ built-in) | SSH auth required |
| 3 | `Add-WindowsCapability ...; scp ...` | 2 | None | Better than GitHub zip, still 2 steps |

## Caveats
- HTTP server is plain HTTP (not HTTPS) — acceptable for trusted tailnet
- Requires new PC to be enrolled in tailnet first (Tailscale installed + logged in)
- If tailscale0 is ever in userspace mode, add `netsh portproxy` on Windows host as fallback

## Sources
- [Tailscale Serve docs](https://tailscale.com/kb/1242/tailscale-serve)
- [Tailscale Funnel docs](https://tailscale.com/kb/1311/tailscale-funnel)
- [PowerShell irm|iex pattern](https://knowledge.buka.sh/powershell-one-liners-for-installation-what-does-irm-bun-sh-install-ps1-iex-really-do/)
- [Tailscale SSH Windows issue](https://github.com/tailscale/tailscale/issues/14942)

## Related
- [[projects/CTX/research/20260424-common-port-fanout-tailscale-vs-ssh|20260424-common-port-fanout-tailscale-vs-ssh]]
- [[projects/CTX/infra/20260423-wsl2-remote-tailscale-tunneling|20260423-wsl2-remote-tailscale-tunneling]]
- [[projects/CTX/infra/20260423-client-onboarding-north-star|20260423-client-onboarding-north-star]]
- [[projects/CTX/decisions/20260326-path-derived-module-to-file|20260326-path-derived-module-to-file]]
