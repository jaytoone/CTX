"""ctx-telemetry — preview CTX retrieval_event telemetry before any upload."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

LOG = Path.home() / ".claude" / "ctx-retrieval-events.jsonl"
AGG_LOG = Path.home() / ".claude" / "ctx-session-aggregates.jsonl"


def _load(path: Path) -> list:
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    return events


def cmd_summary(args):
    events = _load(LOG)
    if not events:
        print("No retrieval_event records yet.")
        print("Records are written by utility-rate.py (Stop hook) when CTX injects context.")
        print(f"Log: {LOG}")
        return

    total = len(events)
    by_source = defaultdict(lambda: {"count": 0, "utility_sum": 0, "cited": 0, "injected": 0})
    by_method = defaultdict(int)
    # query_type × hook_source cross-tab (core moat metric per flywheel research)
    by_qtype = defaultdict(lambda: {"count": 0, "utility_sum": 0})
    by_src_qtype = defaultdict(lambda: defaultdict(lambda: {"count": 0, "utility_sum": 0}))
    vec_up = sum(1 for e in events if e.get("vec_daemon_up"))
    bge_up = sum(1 for e in events if e.get("bge_daemon_up"))
    has_qtype = any(e.get("query_type") not in (None, "UNKNOWN") for e in events)

    for e in events:
        src = e.get("hook_source", "?")
        qt = e.get("query_type", "UNKNOWN")
        ur = e.get("utility_rate", 0)
        by_source[src]["count"] += 1
        by_source[src]["utility_sum"] += ur
        by_source[src]["cited"] += e.get("total_cited", 0)
        by_source[src]["injected"] += e.get("total_injected", 0)
        by_method[e.get("retrieval_method", "UNKNOWN")] += 1
        by_qtype[qt]["count"] += 1
        by_qtype[qt]["utility_sum"] += ur
        by_src_qtype[src][qt]["count"] += 1
        by_src_qtype[src][qt]["utility_sum"] += ur

    print(f"\nCTX Retrieval Telemetry — {total} session-turn records (schema v1.1)")
    print(f"Log: {LOG}")
    print(f"Semantic layer: vec-daemon up {vec_up}/{total} | bge-daemon up {bge_up}/{total}")
    print()
    print(f"{'Block':<14} {'Turns':>6} {'Avg Util%':>10} {'Cited':>8} {'Injected':>10}")
    print("-" * 55)
    for src, d in sorted(by_source.items()):
        avg = d["utility_sum"] / d["count"] * 100 if d["count"] > 0 else 0
        print(f"{src:<14} {d['count']:>6} {avg:>9.1f}% {d['cited']:>8} {d['injected']:>10}")

    print()
    print("Retrieval method distribution:")
    for method, count in sorted(by_method.items(), key=lambda x: -x[1]):
        print(f"  {method:<12} {count:>5}  ({count / total * 100:.1f}%)")

    if has_qtype:
        print()
        print("Query type × utility_rate (moat metric):")
        print(f"  {'QueryType':<12} {'Turns':>6} {'Avg Util%':>10}")
        print("  " + "-" * 32)
        for qt, d in sorted(by_qtype.items(), key=lambda x: -x[1]["count"]):
            avg = d["utility_sum"] / d["count"] * 100 if d["count"] > 0 else 0
            print(f"  {qt:<12} {d['count']:>6} {avg:>9.1f}%")
        print()
        print("  Block × query_type utility breakdown:")
        for src in sorted(by_src_qtype):
            qtd = by_src_qtype[src]
            parts = []
            for qt in sorted(qtd):
                d = qtd[qt]
                avg = d["utility_sum"] / d["count"] * 100 if d["count"] > 0 else 0
                parts.append(f"{qt}={avg:.0f}%({d['count']})")
            print(f"  {src:<10} {' | '.join(parts)}")

    agg_events = _load(AGG_LOG)
    if agg_events:
        n = len(agg_events)
        avg_turns = sum(e.get("total_turns", 0) for e in agg_events) / n
        avg_util = sum(e.get("mean_utility_rate", 0) for e in agg_events) / n * 100
        print(f"\nSession aggregates: {n} sessions | avg turns={avg_turns:.1f} | avg utility={avg_util:.1f}%")
    else:
        print("\nSession aggregates: none yet (flush on session_id change)")

    print()
    print("Note: local-only. Stage 2 upload pipeline not yet implemented.")


def cmd_last(args):
    events = _load(LOG)
    if not events:
        print("No records.")
        return
    n = getattr(args, "n", 10)
    print(f"\nLast {min(n, len(events))} retrieval_event records:\n")
    for e in events[-n:]:
        print(f"  [{e.get('ts_unix_hour', '?')}h] {e.get('hook_source', '?'):10} "
              f"method={e.get('retrieval_method', '?'):8} "
              f"injected={e.get('total_injected', 0):2} cited={e.get('total_cited', 0):2} "
              f"util={e.get('utility_rate', 0) * 100:4.0f}%  "
              f"vec={'v' if e.get('vec_daemon_up') else '-'}  bge={'b' if e.get('bge_daemon_up') else '-'}")


def cmd_calibrate(args):
    """Citation bias detection analysis.

    Validates the utility_rate signal quality. Key concern from flywheel research:
    Claude may cite whatever is in context due to position/recency bias — not genuine
    relevance. This command analyzes the retrieval_event log for calibration signals.

    Flags potential bias if:
    - Mean utility_rate > 0.80 across all records (ceiling effect → position bias)
    - Utility rate does NOT vary by query_type (all types within 5pp of each other)
    - Utility rate does NOT vary by total_injected volume (more injected = same rate)
    - High fraction of records at exactly 1.0 utility_rate
    """
    events = _load(LOG)
    if not events:
        print("No retrieval_event records. Run CTX for some sessions first.")
        return

    n = len(events)
    if n < 10:
        print(f"Only {n} records — calibration needs ≥10 records for signal. Keep using CTX.")
        return

    rates = [e.get("utility_rate", 0.0) for e in events]
    mean_rate = sum(rates) / len(rates)
    perfect_rate = sum(1 for r in rates if r >= 0.999) / len(rates)

    # Variance by query_type (v1.1+ only)
    by_qt = defaultdict(list)
    for e in events:
        qt = e.get("query_type")
        if qt and qt != "UNKNOWN":
            by_qt[qt].append(e.get("utility_rate", 0.0))

    # Variance by injected volume
    by_vol = defaultdict(list)
    for e in events:
        vol = e.get("total_injected", 0)
        bucket = "low(1-3)" if vol <= 3 else "mid(4-7)" if vol <= 7 else "high(8+)"
        by_vol[bucket].append(e.get("utility_rate", 0.0))

    print(f"\nCTX Utility Rate Calibration — {n} retrieval_event records")
    print("=" * 56)
    print(f"\nOverall mean utility_rate: {mean_rate * 100:.1f}%")
    print(f"Perfect (1.0) rate:        {perfect_rate * 100:.1f}% of records")

    flags = []

    if mean_rate > 0.80:
        flags.append(("WARN", "mean_utility > 80%", "possible position/recency bias — Claude cites all injected context"))
    if perfect_rate > 0.50:
        flags.append(("WARN", f"{perfect_rate*100:.0f}% perfect-rate records", "ceiling effect — all injected items cited regardless of relevance"))

    if by_qt and len(by_qt) >= 2:
        qt_means = {qt: sum(v)/len(v) for qt, v in by_qt.items()}
        qt_range = max(qt_means.values()) - min(qt_means.values())
        print(f"\nUtility variance by query_type (range={qt_range*100:.1f}pp):")
        for qt, v in sorted(qt_means.items()):
            print(f"  {qt:<12} mean={v*100:.1f}%  (n={len(by_qt[qt])})")
        if qt_range < 0.05:
            flags.append(("WARN", f"query_type variance={qt_range*100:.1f}pp", "utility rate flat across query types — may not reflect actual relevance"))
        else:
            flags.append(("OK", f"query_type variance={qt_range*100:.1f}pp", "utility varies by query type — healthy signal"))
    else:
        print("\nQuery type breakdown: insufficient v1.1+ records for analysis")

    if len(by_vol) >= 2:
        vol_means = {k: sum(v)/len(v) for k, v in by_vol.items()}
        vol_range = max(vol_means.values()) - min(vol_means.values())
        print(f"\nUtility variance by injection volume (range={vol_range*100:.1f}pp):")
        for k, v in sorted(vol_means.items()):
            print(f"  {k:<12} mean={v*100:.1f}%  (n={len(by_vol[k])})")
        if vol_range < 0.05:
            flags.append(("WARN", f"volume variance={vol_range*100:.1f}pp", "utility rate flat regardless of how many items injected — potential bulk citation"))
        else:
            flags.append(("OK", f"volume variance={vol_range*100:.1f}pp", "utility varies with injection volume — healthy signal"))

    print(f"\nCalibration flags ({len([f for f in flags if f[0]=='WARN'])} warnings, {len([f for f in flags if f[0]=='OK'])} OK):")
    for status, label, detail in flags:
        icon = "⚠" if status == "WARN" else "✓"
        print(f"  {icon} [{label}] {detail}")

    warn_count = len([f for f in flags if f[0] == "WARN"])
    print()
    if warn_count == 0:
        print("CALIBRATION: PASS — utility_rate signal appears trustworthy as flywheel input.")
    elif warn_count == 1:
        print("CALIBRATION: MARGINAL — one warning; monitor as more records accumulate.")
    else:
        print("CALIBRATION: WARN — multiple bias signals detected.")
        print("  Recommendation: inject known-irrelevant context for 10 sessions, re-run.")
        print("  If false citation rate > 15%, weight utility_rate by semantic distance.")

    print()
    print(f"Note: Reliable calibration requires ≥100 records (current: {n}).")
    if n < 100:
        print("      Continue using CTX to accumulate more signal.")


AUTO_TUNE_FILE = Path.home() / ".claude" / "ctx-auto-tune.json"
CONSENT_FILE = Path.home() / ".claude" / "ctx-telemetry-consent.json"
_CONSENT_SCHEMA_VERSION = "v1.4"


def cmd_tune(args):
    """Compute optimal retrieval parameters from local telemetry and write ctx-auto-tune.json.

    This is the flywheel turning: collected usage data → parameter recommendations
    → better retrieval on future queries.

    Recommendations computed:
    - prefer_hybrid_{G1,G2_DOCS}: True if HYBRID utility rate beats BM25 by >5pp
    - temporal_utility_gap: utility delta between TEMPORAL and KEYWORD (informs keyword tuning)
    - bm25_min_score_recommendation: suggested min_score threshold based on KEYWORD utility

    bm25-memory.py reads ctx-auto-tune.json at startup to apply these recommendations.
    """
    import datetime as _dt

    events = _load(LOG)
    if not events:
        print("No retrieval_event records. Enable with: export CTX_TELEMETRY=1")
        return

    n = len(events)
    MIN_RECORDS = 15
    if n < MIN_RECORDS:
        print(f"Only {n} records (need ≥{MIN_RECORDS} for reliable tuning).")
        print("Keep using CTX with CTX_TELEMETRY=1 to accumulate signal.")
        return

    # Compute HYBRID vs BM25 utility delta per hook_source
    by_src_method = defaultdict(lambda: defaultdict(list))
    by_qtype_rates = defaultdict(list)

    for e in events:
        src = e.get("hook_source", "?")
        method = e.get("retrieval_method", "UNKNOWN")
        qt = e.get("query_type", "UNKNOWN")
        ur = e.get("utility_rate", 0.0)
        by_src_method[src][method].append(ur)
        if qt not in ("UNKNOWN", None):
            by_qtype_rates[qt].append(ur)

    recommendations = {
        "schema_version": "v1",
        "computed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "based_on_n": n,
    }

    print(f"\nCTX Auto-Tune — {n} records\n")
    print(f"{'Source':<12} {'HYBRID':>10} {'BM25':>10} {'Delta':>8} {'Recommendation'}")
    print("-" * 62)

    for src in sorted(by_src_method):
        sm = by_src_method[src]
        hybrid_rates = sm.get("HYBRID", [])
        bm25_rates = sm.get("BM25", [])
        if len(hybrid_rates) >= 3 and len(bm25_rates) >= 3:
            hybrid_mean = sum(hybrid_rates) / len(hybrid_rates)
            bm25_mean = sum(bm25_rates) / len(bm25_rates)
            delta = hybrid_mean - bm25_mean
            prefer = delta > 0.05
            key = f"prefer_hybrid_{src.replace('-', '_')}"
            recommendations[key] = prefer
            rec = "prefer HYBRID" if prefer else "BM25 sufficient"
            print(f"{src:<12} {hybrid_mean*100:>9.1f}% {bm25_mean*100:>9.1f}% {delta*100:>+7.1f}pp  {rec}")
        elif hybrid_rates:
            hybrid_mean = sum(hybrid_rates) / len(hybrid_rates)
            recommendations[f"prefer_hybrid_{src.replace('-', '_')}"] = True
            print(f"{src:<12} {hybrid_mean*100:>9.1f}%  {'n/a':>9}  {'n/a':>8}  HYBRID only (no BM25 comparison)")
        elif bm25_rates:
            bm25_mean = sum(bm25_rates) / len(bm25_rates)
            recommendations[f"prefer_hybrid_{src.replace('-', '_')}"] = False
            print(f"{src:<12} {'n/a':>10} {bm25_mean*100:>9.1f}%  {'n/a':>8}  BM25 only")

    # Query type utility analysis
    if len(by_qtype_rates) >= 2:
        print()
        print("Query type utility rates:")
        qt_means = {qt: sum(v)/len(v) for qt, v in by_qtype_rates.items()}
        for qt, mean_rate in sorted(qt_means.items(), key=lambda x: -x[1]):
            print(f"  {qt:<12} {mean_rate*100:.1f}%  (n={len(by_qtype_rates[qt])})")
        if "KEYWORD" in qt_means and "TEMPORAL" in qt_means:
            gap = qt_means["KEYWORD"] - qt_means["TEMPORAL"]
            recommendations["temporal_utility_gap"] = round(gap, 4)
            if gap > 0.10:
                print(f"\n  TEMPORAL queries are {gap*100:.0f}pp below KEYWORD — temporal keyword expansion may need tuning.")
                recommendations["temporal_boost_hint"] = "increase"
            elif gap < -0.05:
                print(f"\n  TEMPORAL queries outperform KEYWORD by {-gap*100:.0f}pp — temporal routing is working well.")
                recommendations["temporal_boost_hint"] = "maintain"

    # Write auto-tune file
    AUTO_TUNE_FILE.write_text(json.dumps(recommendations, indent=2))
    print(f"\nAuto-tune parameters written to: {AUTO_TUNE_FILE}")
    print("bm25-memory.py will read these recommendations at next session start.")
    print()
    print("To re-run as more data accumulates: ctx-telemetry tune")


_UPLOAD_ENDPOINT = "https://telemetry.ctx-retriever.com/v1/session_aggregate"
_UPLOAD_MIN_USERS_K = 5    # k-anonymity gate: suppress if < 5 users per date window
_UPLOAD_STATE_FILE = Path.home() / ".claude" / "ctx-telemetry-upload-state.json"


def cmd_upload(args):
    """Stage 2 upload — POST k-anonymized session_aggregate rows to CTX telemetry endpoint.

    Privacy gates (all must pass before any upload):
    1. Consent file must exist (ctx-telemetry consent grant)
    2. Consent must be for current schema version
    3. k-anonymity: rows with fewer than 5 users in same ts_date window are suppressed

    Current status: endpoint not yet active (Stage 2 launch pending).
    This command validates local data and previews what would be uploaded.
    Use --dry-run (default) to inspect without sending.
    Use --send to actually POST when endpoint is live.
    """
    import datetime as _dt

    send = getattr(args, "send", False)

    # Gate 1: consent
    if not CONSENT_FILE.exists():
        print("No consent on file. Run: ctx-telemetry consent grant")
        return

    try:
        consent = json.loads(CONSENT_FILE.read_text())
    except Exception:
        print("Consent file corrupted. Run: ctx-telemetry consent grant")
        return

    if consent.get("schema_version") != "v1.4":
        print(f"Consent was for schema {consent.get('schema_version')}, current is v1.4.")
        print("Re-run: ctx-telemetry consent grant")
        return

    # Load session aggregates
    agg_events = _load(AGG_LOG)
    if not agg_events:
        print("No session_aggregate records yet. Keep using CTX to accumulate sessions.")
        return

    # Load upload state (track which rows were already sent)
    upload_state = {}
    if _UPLOAD_STATE_FILE.exists():
        try:
            upload_state = json.loads(_UPLOAD_STATE_FILE.read_text())
        except Exception:
            pass

    already_sent = set(upload_state.get("sent_hashes", []))

    # Gate 2: k-anonymity — suppress rows where this user's ts_date has < 5 total rows
    # (Without cross-user data, we simulate: if a single ts_date has < k records from
    #  this user, suppress — prevents pinpointing rare-usage days.)
    by_date = defaultdict(list)
    for e in agg_events:
        by_date[e.get("ts_date", "unknown")].append(e)

    eligible = []
    suppressed = []
    for date, rows in by_date.items():
        if len(rows) >= _UPLOAD_MIN_USERS_K:
            for r in rows:
                row_hash = hashlib.sha256(
                    f"{r.get('session_id_hash','')}{r.get('ts_date','')}".encode()
                ).hexdigest()[:16]
                if row_hash not in already_sent:
                    eligible.append((row_hash, r))
        else:
            suppressed.extend(rows)

    print(f"\nCTX Stage 2 Upload Preview")
    print(f"{'=' * 40}")
    print(f"Total session_aggregate rows: {len(agg_events)}")
    print(f"Already sent:                 {len(already_sent)}")
    print(f"K-anonymity suppressed:       {len(suppressed)} (< {_UPLOAD_MIN_USERS_K} rows/date)")
    print(f"Eligible for upload:          {len(eligible)}")
    print()

    if not eligible:
        if suppressed:
            print(f"All rows suppressed by k-anonymity gate ({_UPLOAD_MIN_USERS_K}-row threshold).")
            print("More sessions needed before upload is possible.")
        else:
            print("All rows already sent.")
        return

    print("Fields that would be uploaded (from each eligible row):")
    sample = eligible[0][1]
    upload_fields = ["schema_version", "user_id", "session_id_hash", "ts_date",
                     "total_turns", "mean_utility_rate", "hook_source_hist",
                     "retrieval_method_hist", "session_outcome",
                     "vault_entry_count", "index_staleness_hours"]
    for f in upload_fields:
        if f in sample:
            val = sample[f]
            print(f"  {f:<28} {json.dumps(val)[:40]}")
    print()

    if not send:
        print(f"Endpoint: {_UPLOAD_ENDPOINT}")
        print("Stage 2 endpoint is NOT yet active.")
        print()
        print("To upload when endpoint is live: ctx-telemetry upload --send")
        print("To monitor endpoint status:      https://github.com/jaytoone/CTX/issues (watch for Stage 2 announcement)")
        return

    # Actual send (when endpoint is live)
    try:
        import urllib.request as _req
        import urllib.error as _err
        payload = [r for _, r in eligible]
        data = json.dumps({"rows": payload, "client_version": "v1.4"}).encode()
        req = _req.Request(
            _UPLOAD_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/json", "X-CTX-Schema": "v1.4"},
            method="POST",
        )
        with _req.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read().decode()[:200]
        if status == 200:
            new_sent = already_sent | {h for h, _ in eligible}
            upload_state["sent_hashes"] = list(new_sent)
            upload_state["last_upload"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            upload_state["total_sent"] = len(new_sent)
            _UPLOAD_STATE_FILE.write_text(json.dumps(upload_state, indent=2))
            print(f"Upload successful: {len(eligible)} rows sent.")
            print(f"Response: {body}")
        else:
            print(f"Upload failed: HTTP {status} — {body}")
    except Exception as exc:
        print(f"Upload failed: {exc}")
        print("Check that the Stage 2 endpoint is active.")


def cmd_consent(args):
    """Stage 2 consent management — opt-in to k-anonymized session_aggregate upload.

    Writes ~/.claude/ctx-telemetry-consent.json when granted.
    Consent is per schema version — must be re-granted after schema upgrades.

    Usage:
      ctx-telemetry consent          # show current status
      ctx-telemetry consent grant    # grant consent (after reviewing schema)
      ctx-telemetry consent revoke   # revoke consent + delete consent file
    """
    subcmd = getattr(args, "consent_cmd", None)

    if subcmd == "revoke":
        if CONSENT_FILE.exists():
            CONSENT_FILE.unlink()
            print("Consent revoked. ctx-telemetry-consent.json deleted.")
            print("Stage 2 upload (when available) will not proceed.")
        else:
            print("No consent file found — already revoked.")
        return

    if CONSENT_FILE.exists():
        try:
            c = json.loads(CONSENT_FILE.read_text())
            print(f"Consent status: GRANTED")
            print(f"  Schema version: {c.get('schema_version', '?')}")
            print(f"  Granted at:     {c.get('granted_at', '?')}")
            print(f"  User ID:        {c.get('user_id', '?')}")
            if c.get("schema_version") != _CONSENT_SCHEMA_VERSION:
                print(f"\n  WARNING: Consent was for schema {c.get('schema_version')} "
                      f"but current schema is {_CONSENT_SCHEMA_VERSION}.")
                print("  Re-run `ctx-telemetry consent grant` to update consent.")
        except Exception:
            print("Consent file exists but could not be parsed. Run `ctx-telemetry consent grant`.")
        if subcmd != "grant":
            return

    if subcmd != "grant":
        if not CONSENT_FILE.exists():
            print("Consent status: NOT GRANTED")
            print()
            print("Stage 2 telemetry upload is not yet available.")
            print("When available, it will upload only k-anonymized session_aggregate rows.")
            print()
            print("To grant consent: ctx-telemetry consent grant")
            print("Schema: https://github.com/jaytoone/CTX#telemetry-opt-in-local-only")
        return

    # Grant consent — show preview first
    agg_events = _load(AGG_LOG)
    print(f"\n=== CTX Telemetry Stage 2 Consent ===")
    print(f"\nYou are about to grant consent for k-anonymized upload of session_aggregate rows.")
    print(f"Schema version: {_CONSENT_SCHEMA_VERSION}")
    print()
    print("What would be uploaded (when Stage 2 launches):")
    print("  - session_aggregate rows only (one row per completed session)")
    print("  - Fields: user_id, session_id_hash, ts_date, total_turns, mean_utility_rate,")
    print("            hook_source_hist, retrieval_method_hist, session_outcome,")
    print("            vault_entry_count, index_staleness_hours")
    print()
    print("Privacy guarantees:")
    print("  - user_id = SHA256(machine-id + install-month)[:16] — non-reversible")
    print("  - Rows with < 5 users in same (ts_date × schema_version) window are suppressed")
    print("  - No query text, code, file names, or content — numeric/categorical only")
    print("  - Full schema: https://github.com/jaytoone/CTX#telemetry-opt-in-local-only")
    print()
    if agg_events:
        print(f"  {len(agg_events)} session_aggregate rows currently in local log.")
    else:
        print("  No session_aggregate rows in local log yet (runs are flushed on session end).")
    print()
    print("Stage 2 upload endpoint is NOT yet active — consent is recorded locally")
    print("and will be used when the upload pipeline launches.")
    print()

    try:
        response = input("Grant consent? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return

    if response != "y":
        print("Consent not granted.")
        return

    import datetime
    import hashlib

    # Derive user_id same way as utility-rate.py
    uid = "unknown"
    try:
        machine_id = ""
        for mid_path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                machine_id = open(mid_path).read().strip()
                break
            except Exception:
                pass
        if not machine_id:
            import socket
            machine_id = socket.gethostname()
        claude_dir = Path.home() / ".claude"
        install_ts = int(claude_dir.stat().st_mtime) if claude_dir.exists() else 0
        d = datetime.datetime.fromtimestamp(install_ts, tz=datetime.timezone.utc).replace(
            day=1, hour=0, minute=0, second=0
        )
        uid = hashlib.sha256(f"{machine_id}:{int(d.timestamp())}".encode()).hexdigest()[:16]
    except Exception:
        pass

    consent = {
        "schema_version": _CONSENT_SCHEMA_VERSION,
        "granted_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "user_id": uid,
        "stage": "2",
        "note": "k-anonymized session_aggregate upload — upload endpoint not yet active",
    }
    CONSENT_FILE.write_text(json.dumps(consent, indent=2))
    print(f"\nConsent granted. Stored at: {CONSENT_FILE}")
    print(f"User ID: {uid}")
    print("When Stage 2 launches, run `ctx-telemetry consent` to verify status.")


def cmd_clear(args):
    deleted = []
    for path in [LOG, AGG_LOG]:
        if path.exists():
            path.unlink()
            deleted.append(str(path))
    if deleted:
        print("Deleted:", ", ".join(deleted))
    else:
        print("No telemetry logs to delete.")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ctx-telemetry",
        description=(
            "CTX retrieval telemetry — local-only, no upload (schema v1.4). "
            "Enable with: export CTX_TELEMETRY=1  "
            "Schema docs: https://github.com/jaytoone/CTX#telemetry-opt-in-local-only"
        ),
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("summary", help="Show aggregate stats (default)")
    last_p = sub.add_parser("last", help="Show last N events")
    last_p.add_argument("-n", type=int, default=10, help="Number of events")
    sub.add_parser("clear", help="Delete local telemetry logs")
    sub.add_parser("calibrate", help="Citation bias detection — validate utility_rate signal")
    sub.add_parser("tune", help="Compute optimal BM25 parameters from local telemetry (flywheel)")
    upload_p = sub.add_parser("upload", help="Stage 2 upload — POST k-anonymized session_aggregate rows")
    upload_p.add_argument("--send", action="store_true", help="Actually POST (default: dry-run preview)")
    consent_p = sub.add_parser("consent", help="Stage 2 consent management (opt-in upload)")
    consent_sub = consent_p.add_subparsers(dest="consent_cmd")
    consent_sub.add_parser("grant", help="Grant Stage 2 upload consent")
    consent_sub.add_parser("revoke", help="Revoke consent and delete consent file")

    args = parser.parse_args(argv)
    if args.cmd == "last":
        cmd_last(args)
    elif args.cmd == "clear":
        cmd_clear(args)
    elif args.cmd == "calibrate":
        cmd_calibrate(args)
    elif args.cmd == "tune":
        cmd_tune(args)
    elif args.cmd == "upload":
        cmd_upload(args)
    elif args.cmd == "consent":
        cmd_consent(args)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
