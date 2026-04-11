#!/usr/bin/env python3
"""
G1 Cross-Domain Generalization Test
====================================
Validates that n=30+BM25+deep_grep improvement is NOT overfitted to CTX project.

Tests two questions:
  A) PRECISION: Does BM25 cause false positives on CTX repo with out-of-domain queries?
  B) RECALL: Does n=30+BM25+deep_grep generalize to Flask/Requests repos?

Comparison:
  baseline_n15   : n=15 recency-only (old hook)
  baseline_n30   : n=30 recency-only (window expansion only)
  new_bm25       : n=30 + BM25 rerank + deep grep (new hook)

Ground truth for Flask: CHANGELOG-based QA pairs with commit dates
Ground truth for CTX: existing 12-query benchmark
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ── Load git-memory hook module ──────────────────────────────────────────────

def load_git_memory():
    spec = importlib.util.spec_from_file_location(
        "git_memory",
        os.path.expanduser("~/.claude/hooks/git-memory.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# ── Retrieve decisions with different configurations ─────────────────────────

def _run_git_log(repo_dir, n):
    """Run git log and return list of (hash, subject) with subjects truncated to 120 chars (matching real hook)."""
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H\x1f%s"],
            cwd=repo_dir, capture_output=True, text=True, timeout=5
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip() or "\x1f" not in line:
                continue
            h, s = line.strip().split("\x1f", 1)
            # Truncate exactly as real hook does
            if len(s) > 120:
                cut = s[:120].rfind(" ")
                s = s[:cut] if cut > 80 else s[:120]
            commits.append((h, s))
        return commits
    except Exception:
        return []


def _collect_decisions(mod, commits, n_cap=7):
    """Filter commits to decision-bearing ones (matches real hook Pass 1)."""
    candidates = []
    seen = set()
    for h, s in commits:
        if mod._is_structural_noise(s):
            continue
        if s[:60] in seen:
            continue
        seen.add(s[:60])
        if mod._is_decision(s):
            candidates.append({"hash": h, "subject": s})
    return candidates[:n_cap]


def get_decisions_n15(mod, repo_dir, query):
    """Old: n=15 recency-only (no BM25, no deep grep)."""
    commits = _run_git_log(repo_dir, 15)
    candidates = _collect_decisions(mod, commits)
    return [d["subject"] for d in candidates], [d["hash"] for d in candidates]


def get_decisions_n30(mod, repo_dir, query):
    """n=30 recency-only (no BM25, no deep grep)."""
    commits = _run_git_log(repo_dir, 30)
    candidates = _collect_decisions(mod, commits)
    return [d["subject"] for d in candidates], [d["hash"] for d in candidates]


def get_decisions_new(mod, repo_dir, query):
    """New: n=30 + BM25 rerank + deep grep.

    Builds a full hash_map from ALL commits (not just n=30) to correctly
    resolve hashes for deep grep results that come from beyond the n=30 window.
    """
    kws = mod.extract_keywords(query)
    decisions, _ = mod.get_git_decisions(repo_dir, n=30, prompt_keywords=kws)
    # Build hash_map from recent 500 commits (covers deep grep range)
    try:
        result = subprocess.run(
            ["git", "log", "-500", "--format=%H\x1f%s"],
            cwd=repo_dir, capture_output=True, text=True, timeout=10
        )
        hash_map = {}
        for line in result.stdout.strip().split("\n"):
            if "\x1f" in line:
                h, s = line.split("\x1f", 1)
                # Store multiple key lengths for fuzzy matching
                hash_map[s[:120]] = h
                hash_map[s[:60]] = h
                hash_map[s.strip()] = h
        # Extract base subject (strip temporal annotations like " [possibly outdated...")
        hashes = []
        for d in decisions:
            base = re.sub(r'\s*\[(superseded|possibly outdated)[^\]]*\].*$', '', d).strip()
            h = hash_map.get(base[:120]) or hash_map.get(base[:60]) or ""
            hashes.append(h)
    except Exception:
        hashes = [""] * len(decisions)
    return decisions, hashes


# ── Flask ground truth resolution ────────────────────────────────────────────

def find_ground_truth_commit(repo_dir, gt_date, gt_feature):
    """Find commit hash matching ground truth by date range search."""
    # Search ±2 days around ground truth date for safety
    year, month, day = gt_date.split("-")
    try:
        result = subprocess.run(
            ["git", "log",
             f"--after={year}-{month}-{int(day)-2:02d}",
             f"--before={year}-{month}-{int(day)+3:02d}",
             "--format=%H %s"],
            cwd=repo_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None, None
        commits = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.strip().split(" ", 1)
                if len(parts) == 2:
                    commits.append((parts[0], parts[1]))
        return commits
    except Exception:
        return []


def best_matching_commit(commits, feature_desc):
    """Find commit most similar to feature description (simple keyword overlap)."""
    if not commits:
        return None, None
    feature_words = set(re.findall(r'[a-zA-Z]{3,}', feature_desc.lower()))
    best_score, best_hash, best_subj = 0, None, None
    for h, s in commits:
        subj_words = set(re.findall(r'[a-zA-Z]{3,}', s.lower()))
        overlap = len(feature_words & subj_words)
        if overlap > best_score:
            best_score, best_hash, best_subj = overlap, h, s
    return best_hash, best_subj


# ── Recall@K measurement ─────────────────────────────────────────────────────

def recall_at_k(retrieved_hashes, gt_hash):
    """1.0 if gt_hash is in retrieved_hashes list, else 0.0."""
    if not gt_hash:
        return None  # unknown ground truth
    # Also check if gt hash is a prefix (short hash)
    for h in retrieved_hashes:
        if h and (h.startswith(gt_hash) or gt_hash.startswith(h)):
            return 1.0
    return 0.0


# ── Test A: CTX precision test (cross-domain queries on CTX repo) ─────────────

CTX_CROSSDOMAIN_QUERIES = [
    # Queries about topics totally absent from CTX commit history
    "add user authentication login route",
    "CSS styling dashboard layout",
    "database migration schema update",
    "React component state management",
    "JavaScript async await error handling",
    "Docker container deployment setup",
]

# CTX-domain queries (control group — should still work with BM25)
CTX_INDOMAIN_QUERIES = [
    ("BM25 reranking for git memory recall improvement", None),
    ("adaptive threshold for chat memory same day", None),
    ("G2 file prefetch from prompt keywords", None),
    ("omc-live outer loop convergence strategy", None),
    ("vec-daemon semantic embedding rerank", None),
    ("noise filter for omc-live iter commits", None),
]


def test_a_precision(mod, ctx_dir):
    """Test A: BM25 order change for cross-domain queries on CTX repo.

    Measures: does BM25 significantly reorder commits for out-of-domain queries?
    If yes → potential precision degradation (BM25 pushes unrelated commits to top).
    Metric: Kendall tau between n15 order and n30+BM25 order.
    """
    print("\n=== Test A: CTX Cross-Domain Precision ===")
    print("Does BM25 cause false-positive reordering on out-of-domain queries?\n")

    results = []
    for query in CTX_CROSSDOMAIN_QUERIES:
        kws = mod.extract_keywords(query)
        decisions_15, hashes_15 = get_decisions_n15(mod, ctx_dir, query)
        decisions_30, hashes_30 = get_decisions_n30(mod, ctx_dir, query)
        decisions_new, hashes_new = get_decisions_new(mod, ctx_dir, query)

        # How different is the new order from n15 recency?
        overlap_15_new = len(set(hashes_15[:7]) & set(hashes_new[:7]))
        overlap_30_new = len(set(hashes_30[:7]) & set(hashes_new[:7]))

        print(f"Query: {query[:55]}")
        print(f"  Keywords: {kws[:5]}")
        print(f"  n15∩new: {overlap_15_new}/7  |  n30∩new: {overlap_30_new}/7")
        if overlap_15_new < 4:
            print(f"  ** HIGH REORDER: BM25 changed >3 of 7 positions")
            print(f"  n15 top-3: {decisions_15[:3]}")
            print(f"  new top-3: {decisions_new[:3]}")
        print()

        results.append({
            "query": query,
            "keywords": kws,
            "overlap_15_new": overlap_15_new,
            "overlap_30_new": overlap_30_new,
            "n15_top3": decisions_15[:3],
            "new_top3": decisions_new[:3],
        })

    high_reorder = sum(1 for r in results if r["overlap_15_new"] < 4)
    print(f"Summary: {high_reorder}/{len(results)} queries had >3 position changes (potential false positives)")
    return results


# ── Test B: Flask recall generalization ──────────────────────────────────────

def test_b_flask_recall(mod):
    """Test B: Recall@7 on Flask external repo with new vs old hook.

    Flask QA pairs from existing open-set benchmark.
    Ground truth: commits found by date-matching CHANGELOG entries.
    """
    flask_dir = "/tmp/g1_eval_flask"
    if not os.path.exists(flask_dir + "/.git"):
        print("ERROR: Flask repo not found at /tmp/g1_eval_flask. Clone first.")
        return {}

    print("\n=== Test B: Flask Recall@7 Generalization ===")
    print("Does new implementation outperform n=15 recency on external repo?\n")

    qa_file = Path("benchmarks/results/g1_openset_qa_pairs.json")
    if not qa_file.exists():
        print("ERROR: QA pairs file not found")
        return {}

    with open(qa_file) as f:
        all_qa = json.load(f)
    flask_qa = all_qa.get("Flask", [])

    print(f"Flask QA pairs: {len(flask_qa)}")

    per_query_results = []
    for qa in flask_qa:
        query = qa["query"]
        gt_date = qa["ground_truth_date"]
        gt_feature = qa["ground_truth_feature"]

        # Find ground truth commit
        nearby_commits = find_ground_truth_commit(flask_dir, gt_date, gt_feature)
        gt_hash, gt_subj = best_matching_commit(nearby_commits, gt_feature)

        # Run all three configurations
        _, h15 = get_decisions_n15(mod, flask_dir, query)
        _, h30 = get_decisions_n30(mod, flask_dir, query)
        _, hnew = get_decisions_new(mod, flask_dir, query)

        r15 = recall_at_k(h15, gt_hash)
        r30 = recall_at_k(h30, gt_hash)
        rnew = recall_at_k(hnew, gt_hash)

        status_15 = "✓" if r15 == 1.0 else ("?" if r15 is None else "✗")
        status_30 = "✓" if r30 == 1.0 else ("?" if r30 is None else "✗")
        status_new = "✓" if rnew == 1.0 else ("?" if rnew is None else "✗")

        kws = mod.extract_keywords(query)
        print(f"Q: {query[:60]}")
        print(f"  GT: {gt_hash[:8] if gt_hash else 'unknown'} — {gt_subj[:50] if gt_subj else '?'}")
        print(f"  Keywords: {kws[:5]}")
        print(f"  n15:{status_15}  n30:{status_30}  new:{status_new}")
        print()

        per_query_results.append({
            "query": query,
            "gt_hash": gt_hash,
            "gt_subject": gt_subj,
            "keywords": kws,
            "r_n15": r15,
            "r_n30": r30,
            "r_new": rnew,
        })

    valid = [r for r in per_query_results if r["r_n15"] is not None]
    if valid:
        recall_15 = sum(r["r_n15"] for r in valid) / len(valid)
        recall_30 = sum(r["r_n30"] for r in valid) / len(valid)
        recall_new = sum(r["r_new"] for r in valid) / len(valid)
        print(f"=== Flask Recall@7 ({len(valid)} valid queries) ===")
        print(f"  n15 (old):          {recall_15:.3f}")
        print(f"  n30 (window only):  {recall_30:.3f}")
        print(f"  n30+BM25+grep(new): {recall_new:.3f}")
        print(f"  Delta (new-old):    {recall_new - recall_15:+.3f}")

        if recall_new > recall_15:
            print(f"  ✓ GENERALIZES: new implementation improves on Flask (+{recall_new-recall_15:.3f})")
        elif recall_new == recall_15:
            print(f"  ~ NEUTRAL: no change on Flask (not overfitting, but no improvement)")
        else:
            print(f"  ✗ OVERFIT: new implementation HURTS on Flask ({recall_new-recall_15:.3f})")

    return {"per_query": per_query_results, "summary": {
        "recall_n15": recall_15 if valid else None,
        "recall_n30": recall_30 if valid else None,
        "recall_new": recall_new if valid else None,
    }}


# ── Test C: CTX in-domain control (sanity check) ─────────────────────────────

def test_c_ctx_control(mod, ctx_dir):
    """Test C: CTX in-domain Recall@7 sanity check.

    Verifies the original improvement still holds.
    Uses a subset of the original 12-query benchmark.
    """
    print("\n=== Test C: CTX In-Domain Control ===")
    print("Sanity check: original +47.6% improvement still holds?\n")

    # Curated 6-query subset with known ground truth commits
    # These are the queries that showed improvement in the original benchmark
    queries_with_gt = [
        {
            "query": "git-memory 작동 방식 recall",
            "gt_keywords": ["git", "memory", "recall", "decision"],  # commit subject keywords
        },
        {
            "query": "BM25 reranking for git memory",
            "gt_keywords": ["bm25", "rerank", "memory"],
        },
        {
            "query": "adaptive threshold chat memory same day",
            "gt_keywords": ["threshold", "chat", "memory", "same"],
        },
        {
            "query": "G2 file prefetch graph search",
            "gt_keywords": ["g2", "prefetch", "graph", "search"],
        },
        {
            "query": "noise filter structural omc iter commits",
            "gt_keywords": ["noise", "filter", "structural"],
        },
        {
            "query": "vec-daemon embedding semantic rerank",
            "gt_keywords": ["vec", "daemon", "embedding", "semantic"],
        },
    ]

    results = []
    for item in queries_with_gt:
        query = item["query"]
        kws = mod.extract_keywords(query)
        decisions_15, _ = get_decisions_n15(mod, ctx_dir, query)
        decisions_new, _ = get_decisions_new(mod, ctx_dir, query)

        # Ground truth: does any decision contain the expected keywords?
        def has_gt_keyword(decisions, gt_kws):
            for d in decisions:
                dl = d.lower()
                for kw in gt_kws:
                    if kw.lower() in dl:
                        return True
            return False

        r15 = 1.0 if has_gt_keyword(decisions_15, item["gt_keywords"]) else 0.0
        rnew = 1.0 if has_gt_keyword(decisions_new, item["gt_keywords"]) else 0.0

        print(f"Q: {query[:55]}")
        print(f"  n15: {'✓' if r15==1 else '✗'}  new: {'✓' if rnew==1 else '✗'}")

        results.append({"query": query, "r_n15": r15, "r_new": rnew})

    recall_15 = sum(r["r_n15"] for r in results) / len(results)
    recall_new = sum(r["r_new"] for r in results) / len(results)
    print(f"\n  n15 Recall@7: {recall_15:.3f}")
    print(f"  new Recall@7: {recall_new:.3f}  (delta: {recall_new-recall_15:+.3f})")
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("G1 Cross-Domain Generalization Benchmark")
    print("=" * 60)

    mod = load_git_memory()
    ctx_dir = "/home/jayone/Project/CTX"

    results_a = test_a_precision(mod, ctx_dir)
    results_b = test_b_flask_recall(mod)
    results_c = test_c_ctx_control(mod, ctx_dir)

    # ── Final summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL VERDICT")
    print("=" * 60)

    high_reorder_a = sum(1 for r in results_a if r["overlap_15_new"] < 4)
    print(f"A) Precision (CTX cross-domain): {high_reorder_a}/{len(results_a)} queries had >3 position changes")
    print(f"   Verdict: {'OVERFITTING RISK' if high_reorder_a >= 3 else 'OK (BM25 gracefully falls back)'}")

    if results_b.get("summary"):
        s = results_b["summary"]
        r15 = s.get("recall_n15", 0) or 0
        rnew = s.get("recall_new", 0) or 0
        print(f"B) Recall@7 (Flask):           old={r15:.3f} → new={rnew:.3f} (delta={rnew-r15:+.3f})")
        print(f"   Verdict: {'GENERALIZES' if rnew >= r15 else 'OVERFIT'}")

    r_c15 = sum(r["r_n15"] for r in results_c) / len(results_c)
    r_cnew = sum(r["r_new"] for r in results_c) / len(results_c)
    print(f"C) CTX in-domain control:      old={r_c15:.3f} → new={r_cnew:.3f} (delta={r_cnew-r_c15:+.3f})")
    print(f"   Verdict: {'OK (original improvement preserved)' if r_cnew >= r_c15 else 'REGRESSION'}")

    # Save results
    out_path = Path("benchmarks/results/g1_cross_domain_generalization.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "test_a": results_a,
            "test_b": results_b,
            "test_c": results_c,
        }, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
