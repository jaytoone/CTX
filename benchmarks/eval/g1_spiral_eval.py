#!/usr/bin/env python3
"""
G1 Spiral Long-Term Memory Evaluation Benchmark
================================================
Measures G1's ability to inject the right iteration of recurring project decisions.

Metrics:
  IP@7  : IterationPriority@7 — newest iteration of topic cluster in injected top-7
  DA@7  : DirectionAlignment@7 — git-oracle proxy (file still active = ALIGNED)
  SD    : SpiralDepth — commit message layer classification (Layer 0-3)
  SNR   : SpiralNoise Rate — multiple iterations of same topic all injected (redundancy)
  SMR   : SpiralMiss Rate — newest iteration in n=20 window but falls outside top-7 cap

Usage:
  python3 benchmarks/eval/g1_spiral_eval.py
"""

import subprocess
import re
import json
import os
from datetime import datetime
from collections import defaultdict

# Match git-memory.py parameters exactly
N_LOG = 20          # git log -N (same as get_git_decisions n=20)
DECISION_CAP = 7    # top-7 cap

# Decision keywords (mirrored from git-memory.py)
_CONV_PREFIXES = (
    "feat:", "fix:", "refactor:", "perf:", "security:", "design:", "test:",
    "docs:", "chore:", "ci:", "build:", "style:", "deprecat",
)
_DECISION_KEYWORDS = (
    "implement", "add", "remove", "replace", "switch", "migrate", "upgrade",
    "introduce", "refactor", "redesign", "rewrite", "convert", "integrate",
    "change", "update", "use ", "adopt", "drop", "deprecate", "move",
    "extract", "split", "merge", "consolidate", "simplify", "extend",
)
_NOISE_PREFIXES = ("# ", "wip:", "merge ", "revert \"")
_VERSION_RE = re.compile(r"^v?\d+\.\d+")

# SpiralDepth layer keywords
LAYER_KEYWORDS = {
    3: ["hybrid", "converge", "converged", "integrate", "combine", "finalize", "complete"],
    2: ["fix", "resolve", "replace", "switch back", "use tf-only", "revert", "fallback",
        "workaround", "adjust", "tune", "correct", "patch"],
    1: ["problem", "issue", "fail", "break", "wrong", "bad", "degraded", "worse",
        "regression", "bug", "doesn't work", "not working"],
}


def is_decision(subject):
    s = subject.strip()
    sl = s.lower()
    if not s:
        return False
    if any(sl.startswith(p) for p in _NOISE_PREFIXES):
        return False
    if any(sl.startswith(p) for p in _CONV_PREFIXES):
        return True
    if _VERSION_RE.match(s):
        return True
    return any(kw.lower() in sl for kw in _DECISION_KEYWORDS)


def get_files_for_commit(project_dir, commit_hash):
    try:
        r = subprocess.run(
            ["git", "show", "--name-only", "--format=", commit_hash],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        files = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
        return [f for f in files if not f.startswith(("docs/", ".omc/", "benchmarks/results/"))]
    except Exception:
        return []


def file_exists_in_head(project_dir, filepath):
    """Check if file still exists in current HEAD (ALIGNED proxy)."""
    r = subprocess.run(
        ["git", "show", f"HEAD:{filepath}"],
        cwd=project_dir, capture_output=True, timeout=5
    )
    return r.returncode == 0


def get_spiral_depth_layer(subject):
    """Classify commit message into SpiralDepth Layer 0-3."""
    sl = subject.lower()
    for layer in [3, 2, 1]:
        if any(kw in sl for kw in LAYER_KEYWORDS[layer]):
            return layer
    return 0  # Layer 0: introduction / neutral


def extract_topic_key(subject, files):
    """
    Build a topic key from a decision commit.
    Clusters decisions that touch the same primary file(s).
    Returns a frozenset of the top-2 code files as topic key.
    """
    code_files = [f for f in files if f.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs"))
                  and not f.startswith(("docs/", "tests/", "test_"))]
    if code_files:
        return frozenset(sorted(code_files)[:2])  # top-2 files as cluster key
    # Fallback: use first 3 significant words of subject
    words = [w for w in subject.lower().split() if len(w) > 3 and w not in
             ("feat", "fix:", "refactor", "update", "change", "the", "and", "for", "with")]
    return frozenset(words[:3]) if words else frozenset([subject[:30]])


def analyze_project(project_dir, project_name):
    """Run G1 spiral eval metrics on a single project."""

    # Step 1: Get last N_LOG commits
    try:
        r = subprocess.run(
            ["git", "log", f"-{N_LOG}", "--format=%H\x1f%s\x1f%ai"],
            cwd=project_dir, capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return None
    except Exception:
        return None

    all_commits = []
    seen_subjects = set()
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 2)
        if len(parts) != 3:
            continue
        commit_hash, subject, commit_date = parts
        if len(subject) > 120:
            cut = subject[:120].rfind(" ")
            subject = subject[:cut] if cut > 80 else subject[:120]
        subject_key = subject[:60]
        if subject_key in seen_subjects:
            continue
        seen_subjects.add(subject_key)
        all_commits.append({
            "hash": commit_hash,
            "subject": subject,
            "date": commit_date,
            "is_decision": is_decision(subject),
        })

    # Step 2: Separate decisions (n=20 window) into injected (top-7) vs tail (8-20)
    decisions_in_window = [c for c in all_commits if c["is_decision"]]
    injected = decisions_in_window[:DECISION_CAP]   # top-7 (newest first)
    tail = decisions_in_window[DECISION_CAP:]        # beyond cap (older decisions)

    if not injected:
        return {
            "project": project_name,
            "total_commits_scanned": len(all_commits),
            "decisions_in_window": 0,
            "injected_count": 0,
            "skip_reason": "no decision commits found"
        }

    # Step 3: Get files for each decision commit
    for c in decisions_in_window:
        c["files"] = get_files_for_commit(project_dir, c["hash"])
        c["topic_key"] = extract_topic_key(c["subject"], c["files"])
        c["spiral_layer"] = get_spiral_depth_layer(c["subject"])

    # Step 4: Build topic clusters across ALL decisions in window
    # Group by topic_key
    topic_clusters = defaultdict(list)
    for c in decisions_in_window:
        tk = c["topic_key"]
        # Only cluster if topic_key is non-trivial (has actual files)
        if len(tk) > 0:
            topic_clusters[str(sorted(tk))].append(c)

    spiral_clusters = {k: v for k, v in topic_clusters.items() if len(v) > 1}

    # Step 5: IP@7 — for each spiral cluster, is the newest in injected top-7?
    ip_results = []
    for cluster_key, cluster_commits in spiral_clusters.items():
        # newest first (already ordered by git log)
        newest = cluster_commits[0]
        in_injected = newest in injected
        ip_results.append({
            "cluster_key": cluster_key,          # full key for lookup
            "cluster_key_display": cluster_key[:60],
            "cluster_size": len(cluster_commits),
            "newest_subject": newest["subject"][:80],
            "newest_in_injected": in_injected,
            "all_in_injected": all(c in injected for c in cluster_commits),
        })

    ip_at_7 = (sum(1 for r in ip_results if r["newest_in_injected"]) / len(ip_results)
               if ip_results else None)

    # SpiralNoise: clusters where ALL iterations injected (redundant context)
    spiral_noise_count = sum(1 for r in ip_results if r["all_in_injected"] and r["cluster_size"] > 1)

    # SpiralMiss: newest iteration is in n=20 window (tail) but NOT in injected top-7
    spiral_miss_count = 0
    for r in ip_results:
        if not r["newest_in_injected"]:
            commits = spiral_clusters.get(r["cluster_key"], [])
            if commits and commits[0] in tail:
                spiral_miss_count += 1

    # Step 6: DA@7 — git-oracle proxy for each injected decision
    da_results = []
    for c in injected:
        if not c["files"]:
            da_results.append({"subject": c["subject"][:60], "alignment": "NO_FILES", "files": []})
            continue
        code_files = [f for f in c["files"] if not f.startswith(("docs/", ".omc/"))]
        if not code_files:
            da_results.append({"subject": c["subject"][:60], "alignment": "DOCS_ONLY", "files": c["files"]})
            continue
        # Check if any code file still exists in HEAD
        active = [f for f in code_files if file_exists_in_head(project_dir, f)]
        deleted = [f for f in code_files if not file_exists_in_head(project_dir, f)]
        if active:
            alignment = "ALIGNED"
        elif deleted:
            alignment = "OBSOLETE"
        else:
            alignment = "UNKNOWN"
        da_results.append({
            "subject": c["subject"][:60],
            "alignment": alignment,
            "active_files": active[:3],
            "deleted_files": deleted[:3],
        })

    da_at_7 = (sum(1 for r in da_results if r["alignment"] == "ALIGNED") / len(da_results)
               if da_results else None)

    # Step 7: SpiralDepth distribution for injected decisions
    layer_dist = defaultdict(int)
    for c in injected:
        layer_dist[c["spiral_layer"]] += 1

    sd_score = (sum(c["spiral_layer"] for c in injected) / len(injected) if injected else 0)

    return {
        "project": project_name,
        "total_commits_scanned": len(all_commits),
        "decisions_in_window": len(decisions_in_window),
        "injected_count": len(injected),
        "tail_count": len(tail),

        # Core metrics
        "IP@7": round(ip_at_7, 3) if ip_at_7 is not None else "N/A (no spiral clusters)",
        "DA@7": round(da_at_7, 3) if da_at_7 is not None else None,
        "SD_mean": round(sd_score, 2),

        # Spiral structure
        "spiral_clusters_found": len(spiral_clusters),
        "spiral_noise_count": spiral_noise_count,
        "spiral_miss_count": spiral_miss_count,

        # Detail
        "layer_distribution": dict(layer_dist),
        "ip_detail": ip_results,
        "da_detail": da_results,
    }


def main():
    projects = {
        "CTX": "/home/jayone/Project/CTX",
        "PaintPoint": "/home/jayone/Project/PaintPoint",
        "Entity": "/home/jayone/Project/Entity",
        "FromScratch": "/home/jayone/Project/FromScratch",
    }

    all_results = []
    print("=" * 70)
    print("G1 Spiral Memory Evaluation Benchmark")
    print(f"Params: n={N_LOG} log window, top-{DECISION_CAP} inject cap")
    print("=" * 70)

    for name, path in projects.items():
        if not os.path.isdir(path):
            print(f"\n[SKIP] {name}: directory not found at {path}")
            continue
        print(f"\n[{name}] Analyzing {path}...")
        result = analyze_project(path, name)
        if result is None:
            print(f"  ERROR: could not run git log")
            continue
        all_results.append(result)

        # Print summary
        if "skip_reason" in result:
            print(f"  SKIP: {result['skip_reason']}")
            continue

        print(f"  Commits scanned: {result['total_commits_scanned']}")
        print(f"  Decisions in window: {result['decisions_in_window']} ({result['injected_count']} injected + {result['tail_count']} tail)")
        print(f"  Spiral clusters: {result['spiral_clusters_found']}")
        print(f"  IP@7 : {result['IP@7']}")
        print(f"  DA@7 : {result['DA@7']}  (ALIGNED / total injected)")
        print(f"  SD   : {result['SD_mean']}  (mean spiral depth layer, 0-3)")
        print(f"  Noise: {result['spiral_noise_count']} clusters fully injected (all iterations)")
        print(f"  Miss : {result['spiral_miss_count']} spiral misses (newest in tail, oldest injected)")

        if result["ip_detail"]:
            print(f"  --- Spiral Clusters ---")
            for ip in result["ip_detail"]:
                status = "✓" if ip["newest_in_injected"] else "✗"
                noise = " [NOISE: all injected]" if ip["all_in_injected"] else ""
                print(f"    [{status}] size={ip['cluster_size']} {ip['newest_subject'][:60]}{noise}"
                      if "cluster_key_display" not in ip else
                      f"    [{status}] size={ip['cluster_size']} {ip['newest_subject'][:60]}{noise}")

        print(f"  --- Direction Alignment ---")
        for da in result["da_detail"]:
            print(f"    [{da['alignment']:10}] {da['subject'][:55]}")

    # Aggregate stats
    valid = [r for r in all_results if "skip_reason" not in r and r["IP@7"] != "N/A (no spiral clusters)"]

    print("\n" + "=" * 70)
    print("AGGREGATE (across all projects with spiral clusters)")
    print("=" * 70)

    if valid:
        ip_scores = [r["IP@7"] for r in valid if isinstance(r["IP@7"], float)]
        da_scores = [r["DA@7"] for r in valid if r["DA@7"] is not None]
        sd_scores = [r["SD_mean"] for r in valid]
        total_clusters = sum(r["spiral_clusters_found"] for r in all_results if "skip_reason" not in r)
        total_noise = sum(r["spiral_noise_count"] for r in all_results if "skip_reason" not in r)
        total_miss = sum(r["spiral_miss_count"] for r in all_results if "skip_reason" not in r)

        print(f"  IP@7 mean : {sum(ip_scores)/len(ip_scores):.3f}" if ip_scores else "  IP@7: no clusters")
        print(f"  DA@7 mean : {sum(da_scores)/len(da_scores):.3f}" if da_scores else "  DA@7: N/A")
        print(f"  SD mean   : {sum(sd_scores)/len(sd_scores):.2f}")
        print(f"  Total spiral clusters : {total_clusters}")
        print(f"  Spiral Noise Rate     : {total_noise}/{total_clusters} ({total_noise/total_clusters:.1%})" if total_clusters else "  Spiral Noise: 0")
        print(f"  Spiral Miss Rate      : {total_miss}/{total_clusters} ({total_miss/total_clusters:.1%})" if total_clusters else "  Spiral Miss: 0")
    else:
        print("  No projects with spiral clusters found.")

    # Save results
    output = {
        "benchmark": "G1 Spiral Long-Term Memory Evaluation",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "params": {"n_log": N_LOG, "decision_cap": DECISION_CAP},
        "projects": all_results,
        "aggregate": {
            "ip7_mean": round(sum(r["IP@7"] for r in valid if isinstance(r["IP@7"], float)) / len(valid), 3) if valid else None,
            "da7_mean": round(sum(r["DA@7"] for r in valid if r["DA@7"] is not None) / len([r for r in valid if r["DA@7"] is not None]), 3) if any(r["DA@7"] for r in valid) else None,
            "sd_mean": round(sum(r["SD_mean"] for r in valid) / len(valid), 2) if valid else None,
        }
    }
    os.makedirs("/home/jayone/Project/CTX/benchmarks/results", exist_ok=True)
    out_path = "/home/jayone/Project/CTX/benchmarks/results/g1_spiral_eval.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n[SAVED] {out_path}")

    return output


if __name__ == "__main__":
    main()
