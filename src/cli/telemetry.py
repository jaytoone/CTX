"""ctx-telemetry — preview CTX retrieval_event telemetry before any upload."""
from __future__ import annotations

import argparse
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
        description="CTX retrieval telemetry preview — local-only, no upload",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("summary", help="Show aggregate stats (default)")
    last_p = sub.add_parser("last", help="Show last N events")
    last_p.add_argument("-n", type=int, default=10, help="Number of events")
    sub.add_parser("clear", help="Delete local telemetry logs")

    args = parser.parse_args(argv)
    if args.cmd == "last":
        cmd_last(args)
    elif args.cmd == "clear":
        cmd_clear(args)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
