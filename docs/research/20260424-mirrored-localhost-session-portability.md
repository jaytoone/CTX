# [expert-research-v2] Mirrored localhost: session portability across browsers
**Date**: 2026-04-24  **Skill**: expert-research-v2 (Quick Mode)

## Original Question
If a client PC's browser accesses `http://localhost:3003` (mirrored via netsh portproxy + Tailscale to WSL2 dev server), does login state sync to a browser on the WSL2 side?

## Web Facts
- [FACT-1] Cookies stored per-browser-profile in the user's cookie jar, not in URL origin state. Same URL does NOT imply shared cookies across browsers/machines. (w3tutorials.net)
- [FACT-2] Localhost cookies ARE shared across ports on same browser (RFC 6265 port-agnostic), BUT `localhost` and `127.0.0.1` are treated as different domains — cookies don't cross. (node-security.com)
- [FACT-3] Playwright `storageState()` exports cookies + localStorage + sessionStorage + IndexedDB to JSON. `.storageState({path: 'auth.json'})` saves; `browser.newContext({storageState: 'auth.json'})` loads. Standard pattern for test automation. (playwright.dev/docs/auth)
- [FACT-4] Server-side session state is shared because both sides hit the same dev server — whoever presents the right cookie/token gets authenticated.
- [FACT-5] OAuth redirect to `localhost:3003` resolves per-browser — whichever browser initiated the OAuth flow receives the redirect callback with the token; not automatically shared.

## Final Conclusion

### Short answer
**No automatic sync. Yes, portable via Playwright `storageState`.**

### Detailed

(a) **Cookies sync across profiles?** NO. Each browser (client Chrome, WSL2's browser or Playwright) has its own cookie jar. Same-origin URL doesn't help.

(b) **Legitimate way to port login state?** YES — Playwright's `storageState`:
```bash
# On client — after manually logging in:
# (using Chrome devtools extension like EditThisCookie, or Playwright MCP)
# Save to a JSON file with cookies + localStorage + IndexedDB

# Transfer auth.json to WSL2 (scp, shared filesystem, etc.)

# On WSL2 Playwright:
await browser.newContext({ storageState: './auth.json' })
# → new context is "pre-logged-in"
```
For `curl`-style testing from WSL2, grab the session cookie from Chrome DevTools → `curl -b "session=XYZ" http://localhost:3003/api/...`

(c) **OAuth to localhost:3003?** Works fine on BOTH sides independently. Whichever browser initiates the OAuth flow gets the redirect callback. If client completes OAuth, its cookies have the session; WSL2's Playwright doesn't — until you export/import storageState.

(d) **Security concerns with same-URL port-forward:**
- Any process on the client PC can access `localhost:3003` and inherit the authenticated browser's cookies (if cookies are SameSite=Lax and the app doesn't check origin strictly)
- `storageState.json` files are equivalent to stolen credentials — never commit to git, never share outside trusted context
- If Tailscale node is compromised, attacker gets the tunnel endpoint on the attacker's machine
- Mitigations: use SameSite=Strict on auth cookies in the dev app; never commit storageState; use short-lived tokens in dev

### Recommended workflow for "mirror + test from WSL2"

1. Client browser: log in normally at `http://localhost:3003`
2. Export session via Playwright MCP or ChromeDriver → `auth.json`
3. Copy `auth.json` to WSL2 (`scp` or shared mount)
4. WSL2 Playwright loads with `storageState: 'auth.json'` → pre-authenticated
5. For quick `curl` tests: grab the `session=` cookie from DevTools → `curl -b 'session=XYZ' ...`

### Confidence: HIGH

## Sources
- [w3tutorials.net — Cookies are not port specific](https://www.w3tutorials.net/blog/are-http-cookies-port-specific/)
- [node-security.com — Cookies, Ports and Subdomains](https://node-security.com/posts/cookies-ports-and-subdomains/)
- [Playwright Authentication docs](https://playwright.dev/docs/auth)
- [BrowserStack — Playwright storageState guide](https://www.browserstack.com/guide/playwright-storage-state)
