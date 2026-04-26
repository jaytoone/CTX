"""
Citation Probe — Measure actual citation rate of retrieved G1/G2 nodes.

Architecture:
  1. bm25-memory.py logs retrieved nodes to .omc/retrieval_log.jsonl per turn
  2. This script cross-references those logs with vault.db chat history
  3. Heuristic: a node is "cited" if ≥2 distinctive keywords from its text
     appear verbatim in the assistant response for the same session turn

Usage:
    python3 benchmarks/eval/citation_probe.py [--log-path .omc/retrieval_log.jsonl]
                                               [--vault ~/.local/share/claude-vault/vault.db]
                                               [--min-turns 10]
                                               [--summary-only]

Output:
    Citation rate table by block type (g1_decisions / g2_docs / g2_prefetch)
    Session-level breakdown
    Top cited and top uncited nodes

Research context (iter 37 finding):
    85.8% of retrieved G1 nodes are surface-match-only (homograph FPs).
    This script measures what fraction of those nodes Claude actually REFERENCES
    in its response — i.e., the actual harmful FP rate vs. the theoretical ceiling.

    Hypothesis: if citation rate is >50%, FP reduction IS the right priority.
    If citation rate is <20%, recall is the binding constraint (not FP reduction).
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime


# ── Tokenizer (shared with bm25-memory.py logic) ─────────────────────────────

STOPWORDS = {
    "a","an","the","and","or","in","on","for","to","of","is","are","was","were",
    "with","from","by","at","this","that","it","be","been","have","has","do","not",
    "we","our","i","you","your","the","its","as","up","down","into","out","after",
    "before","when","if","then","so","will","can","how","what","why","where","also",
    "per","via","vs","iter","live","inf","ctx","2026","04","26","25","24","23",
}

def tokenize(text):
    """Extract distinctive keyword tokens from a node text."""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_]*", text.lower())
    tokens = [t for t in tokens if len(t) >= 4 and t not in STOPWORDS]
    return list(dict.fromkeys(tokens))  # deduplicate, preserve order


# ── Vault DB — assistant response retrieval ───────────────────────────────────

def load_vault_turns(vault_path, session_id=None):
    """
    Load (session_id, turn_content) pairs from vault.db.
    Returns dict: {session_id: [{"role": str, "content": str, "ts": float}]}
    """
    if not os.path.exists(vault_path):
        return {}
    try:
        db = sqlite3.connect(vault_path)
        if session_id:
            rows = db.execute(
                "SELECT session_id, role, content, created_at FROM messages "
                "WHERE session_id=? ORDER BY created_at",
                (session_id,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT session_id, role, content, created_at FROM messages "
                "ORDER BY session_id, created_at"
            ).fetchall()
        db.close()
        turns = defaultdict(list)
        for sid, role, content, ts in rows:
            turns[sid].append({"role": role, "content": content or "", "ts": ts})
        return dict(turns)
    except Exception as e:
        print(f"[WARN] vault.db read failed: {e}", file=sys.stderr)
        return {}


# ── Citation heuristic ────────────────────────────────────────────────────────

def is_cited(node_text, response_text, min_keyword_hits=2):
    """
    Returns True if node_text appears to be cited in response_text.
    Heuristic: ≥2 distinctive keywords from node_text appear in response_text.

    Stricter than simple substring match — avoids false positives from
    common technical terms that appear in many responses.
    """
    node_tokens = tokenize(node_text)
    if len(node_tokens) < 2:
        return False  # node too short to distinguish
    resp_lower = response_text.lower()
    hits = sum(1 for t in node_tokens[:8] if t in resp_lower)  # check first 8 tokens
    return hits >= min_keyword_hits


# ── Main analysis ─────────────────────────────────────────────────────────────

def run_analysis(log_path, vault_path, min_turns=5, summary_only=False):
    # Load retrieval log
    if not os.path.exists(log_path):
        print(f"No retrieval log at {log_path}.")
        print("Start a few Claude Code sessions to accumulate data, then re-run.")
        return

    retrieval_events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                retrieval_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not retrieval_events:
        print("Retrieval log is empty.")
        return

    print(f"Loaded {len(retrieval_events)} retrieval events from {log_path}")

    # Load vault.db
    vault_turns = load_vault_turns(vault_path)
    print(f"Loaded {len(vault_turns)} sessions from vault.db")

    # Group events by session
    events_by_session = defaultdict(list)
    for ev in retrieval_events:
        events_by_session[ev.get("session_id", "unknown")].append(ev)

    sessions_analyzed = 0
    block_stats = defaultdict(lambda: {"retrieved": 0, "cited": 0, "no_response": 0})
    top_cited = []
    top_uncited = []

    for session_id, events in events_by_session.items():
        session_turns = vault_turns.get(session_id, [])
        assistant_responses = [t["content"] for t in session_turns if t["role"] == "assistant"]

        if not assistant_responses:
            # No vault data for this session — count as no_response
            for ev in events:
                for item in ev.get("items", []):
                    block_stats[ev["block"]]["retrieved"] += 1
                    block_stats[ev["block"]]["no_response"] += 1
            continue

        sessions_analyzed += 1
        # For each retrieval event, check if any subsequent response cites the node
        for ev in events:
            block = ev.get("block", "unknown")
            # Find responses that came after this retrieval (by timestamp)
            ev_ts = ev.get("ts", 0)
            subsequent = [
                t["content"] for t in session_turns
                if t["role"] == "assistant" and (t.get("ts") or 0) > ev_ts
            ] or assistant_responses  # fallback: check all responses if no timestamps

            for item in ev.get("items", []):
                block_stats[block]["retrieved"] += 1
                node_text = item.get("text", "")
                cited = any(is_cited(node_text, r) for r in subsequent[:3])  # check next 3 responses
                if cited:
                    block_stats[block]["cited"] += 1
                    top_cited.append({"block": block, "text": node_text[:80]})
                else:
                    top_uncited.append({"block": block, "text": node_text[:80]})

    # Print results
    print()
    print("=" * 70)
    print("CITATION PROBE RESULTS")
    print("=" * 70)
    print(f"Sessions analyzed: {sessions_analyzed} (with vault data)")
    print(f"Sessions without vault data: {len(events_by_session) - sessions_analyzed}")
    print()

    print(f"{'Block':<20} {'Retrieved':>10} {'Cited':>8} {'Citation%':>10} {'No resp':>8}")
    print("-" * 60)
    total_r, total_c = 0, 0
    for block, stats in sorted(block_stats.items()):
        r = stats["retrieved"]
        c = stats["cited"]
        no_r = stats["no_response"]
        pct = f"{c/r*100:.1f}%" if r > 0 else "n/a"
        print(f"{block:<20} {r:>10} {c:>8} {pct:>10} {no_r:>8}")
        total_r += r
        total_c += c

    print("-" * 60)
    total_pct = f"{total_c/total_r*100:.1f}%" if total_r > 0 else "n/a"
    print(f"{'TOTAL':<20} {total_r:>10} {total_c:>8} {total_pct:>10}")

    if not summary_only and top_cited:
        print()
        print("TOP CITED NODES (sample):")
        for item in top_cited[:5]:
            print(f"  [{item['block']}] {item['text']}")

    if not summary_only and top_uncited:
        print()
        print("TOP UNCITED NODES (sample — potential FPs):")
        for item in top_uncited[:5]:
            print(f"  [{item['block']}] {item['text']}")

    print()
    if total_r == 0:
        print("No data — run more sessions to accumulate retrieval logs.")
        return

    citation_rate = total_c / total_r
    print("INTERPRETATION:")
    if citation_rate > 0.50:
        print(f"  ⚠ Citation rate {total_pct} is HIGH → FP reduction IS the right priority.")
        print("  Many retrieved nodes are being used by Claude — quality of retrieval matters.")
    elif citation_rate > 0.20:
        print(f"  ◆ Citation rate {total_pct} is MODERATE → balanced: both recall and FP matter.")
        print("  Some improvement in precision would help, but recall is also important.")
    else:
        print(f"  ✓ Citation rate {total_pct} is LOW → recall is the binding constraint.")
        print("  Claude selects from retrieved candidates — FP reduction is low priority.")
        print("  Priority: improve recall (get more relevant nodes into the pool).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CTX Citation Probe — measure actual node citation rate")
    parser.add_argument("--log-path", default=".omc/retrieval_log.jsonl",
                        help="Path to retrieval_log.jsonl (default: .omc/retrieval_log.jsonl)")
    parser.add_argument("--vault", default=os.path.expanduser("~/.local/share/claude-vault/vault.db"),
                        help="Path to vault.db (default: ~/.local/share/claude-vault/vault.db)")
    parser.add_argument("--min-turns", type=int, default=5,
                        help="Minimum turns per session to include in analysis")
    parser.add_argument("--summary-only", action="store_true",
                        help="Only print summary table, skip node samples")
    args = parser.parse_args()

    run_analysis(
        log_path=args.log_path,
        vault_path=args.vault,
        min_turns=args.min_turns,
        summary_only=args.summary_only,
    )
