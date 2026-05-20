# CTX Privacy Policy

**Last updated:** 2026-05-19 | **Package:** ctx-retriever | **Controller:** jaytoone (be2jay67@gmail.com)

## What we collect

When you install and use CTX, the following **aggregate, non-identifying statistics** are sent to our database:

| Field | Description | Example |
|---|---|---|
| `user_id` | SHA256(machine_id + install_month)[:16] — cannot be reversed | `6d7f66b2fb843134` |
| `session_id_hash` | SHA256(session_id)[:16] — per-session, not per-user | `a1b2c3d4e5f60001` |
| `ts_date` | Date truncated to day (no timestamp) | `2026-05-19` |
| `total_turns` | Number of Claude Code turns in the session | `14` |
| `session_outcome` | Session type: SHORT / NORMAL / INSTALL_PING | `NORMAL` |
| `ctx_version` | Package version | `0.3.28` |
| `mean_utility_rate` | How often CTX-injected context was referenced | `0.42` |
| `hook_source_hist` | Which hooks fired (G1/G2/CM counts) | `{"G1":3,"CM":2}` |

**We never collect:** code content, file paths, prompt text, editor content, API keys, personal identifiers, or any human-readable text.

## Why we collect this

To improve CTX's retrieval quality and prioritize development. Lawful basis: **legitimate interests** (GDPR Art. 6(1)(f)) — product improvement for a free, open-source tool.

## Hash construction proof (non-identifiable)

The `user_id` hash is computed as:

```python
SHA256(f"{machine_id}:{install_month_epoch}").hexdigest()[:16]
```

- `machine_id` comes from `/etc/machine-id` (Linux) or hostname fallback — never stored by CTX
- `install_month_epoch` truncates to the 1st of the month — prevents daily re-tracking
- 16 hex chars of a SHA256 provides ~10^19 space — cannot be inverted without the original inputs
- CTX does not store `machine_id` anywhere; the hash is one-way by construction

Under the 2025 ECJ pseudonymisation standard, this hash is outside GDPR personal data scope because CTX as the data recipient cannot reasonably re-identify the subject.

## k-anonymity policy

Records are suppressed until a minimum cohort of **k≥5** independent install hashes share the same date bucket. This prevents singling-out attacks described in GDPR Recital 26.

## Data is not sold

Data is not sold, shared with third parties for commercial purposes, or used for cross-context behavioral advertising. Our database provider (Turso) processes data as a service provider under a Data Processing Agreement and is bound by the same restrictions.

## Opt-out

Three ways to disable collection:

```bash
ctx-telemetry disable                        # recommended
# OR
touch ~/.claude/ctx-telemetry-revoke         # file-based opt-out
# OR
export CTX_TELEMETRY_REVOKE=1               # env-var opt-out (per-session)
```

To re-enable: `ctx-telemetry enable` or delete the revoke file.

## Debug mode

To inspect exactly what is sent before it leaves your machine:

```bash
export CTX_TELEMETRY_DEBUG=1
python3 -c "import ctx_retriever"  # triggers auto-install, prints payload to stderr
```

## Retention

Data is retained for 24 months and then deleted from our Turso database.

## Contact / GDPR requests

Email: be2jay67@gmail.com

Note: Because `user_id` is non-reversible by design, we cannot fulfill Subject Access Requests that require linking a record to a specific person. If you have opted out, no data exists for your machine.

## Open source

The full telemetry implementation is in [`src/hooks/session-start-telemetry.py`](src/hooks/session-start-telemetry.py) and [`src/_autoinstall.py`](src/_autoinstall.py).
