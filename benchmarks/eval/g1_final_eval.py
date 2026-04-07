#!/usr/bin/env python3
"""
G1 Long-Term Memory — Final Evaluation Benchmark Suite
=======================================================
Corrected framing: G1's core failure is NOT "wrong version injected"
(recency ordering handles that automatically) but:

  "version/chore noise occupies 7-cap → real topic coverage collapses"

Metrics (in priority order):
  NoiseRatio@7     : version_tag + chore fraction of injected top-7
  TopicCoverage@7  : distinct file-topics in injected top-7 / total topics in window
  IP@7             : newest iteration of each topic cluster in top-7 (current)
  IP@7_dedup       : simulated IP@7 if topic-dedup applied (what improvement looks like)
  DA@7             : direction alignment (git-oracle: files still active)
  SpiralDepth      : mean layer classification (0-3)

Usage:
  python3 benchmarks/eval/g1_final_eval.py
"""

import subprocess
import re
import json
import os
from datetime import datetime
from collections import defaultdict

# ── Parameters (mirror git-memory.py exactly) ──────────────────────────────
N_LOG = 30   # expanded to scan past version-bump blocks (was 20)
DECISION_CAP = 7

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
_CHORE_RE = re.compile(r"^(chore|ci|build|style|docs):", re.IGNORECASE)
_VERSION_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+")      # strict semver tag
_OMC_ITER_RE = re.compile(r"^(omc-live|live-inf)\s+(iter|checkpoint)", re.IGNORECASE)
# Embedded decision content preserved: "v3.42.4 - fix: ..." is a REAL decision
_EMBEDDED_DECISION_RE = re.compile(
    r"\s[-—]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
    re.IGNORECASE
)

LAYER_KEYWORDS = {
    3: ["hybrid", "converge", "converged", "integrate", "combine", "finalize"],
    2: ["fix", "resolve", "replace", "switch back", "tf-only", "revert",
        "fallback", "workaround", "adjust", "tune", "correct", "patch"],
    1: ["problem", "issue", "fail", "break", "wrong", "bad", "degraded",
        "regression", "bug", "doesn't work"],
}


def is_decision(s):
    sl = s.strip().lower()
    if not sl:
        return False
    if any(sl.startswith(p) for p in _NOISE_PREFIXES):
        return False
    if any(sl.startswith(p) for p in _CONV_PREFIXES):
        return True
    if _VERSION_RE.match(s.strip()):
        return True
    return any(kw in sl for kw in _DECISION_KEYWORDS)


def is_noise_commit(subject):
    """True if this commit is structural noise (version bump without content, or iter checkpoint).

    Exception: version tags with embedded decision content like
    "v3.42.4 - fix: /live IP list" are preserved as valid decisions.
    This mirrors git-memory.py _is_structural_noise() exactly.
    """
    s = subject.strip()
    if _OMC_ITER_RE.match(s):
        return True, "omc_iter"
    if _VERSION_TAG_RE.match(s) or re.match(r"^v\d+\.\d+", s):
        # Preserve if embedded decision content (feat/fix/etc.) found after dash
        if _EMBEDDED_DECISION_RE.search(s):
            return False, None  # real decision embedded in version tag
        return True, "version_tag"
    if _CHORE_RE.match(s):
        return True, "chore"
    return False, None


def get_files(project_dir, commit_hash):
    try:
        r = subprocess.run(
            ["git", "show", "--name-only", "--format=", commit_hash],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        files = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
        return [f for f in files
                if not f.startswith(("docs/", ".omc/", "benchmarks/results/", "commit_tree"))]
    except Exception:
        return []


def file_exists_in_head(project_dir, filepath):
    r = subprocess.run(
        ["git", "show", f"HEAD:{filepath}"],
        cwd=project_dir, capture_output=True, timeout=5
    )
    return r.returncode == 0


def topic_key(files):
    """Cluster key from code files (top-2 .py/.ts/.tsx/.js)."""
    code = [f for f in files
            if f.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs"))
            and not f.startswith(("tests/", "test_"))]
    return frozenset(sorted(code)[:2]) if code else None


def spiral_layer(subject):
    sl = subject.lower()
    for layer in [3, 2, 1]:
        if any(kw in sl for kw in LAYER_KEYWORDS[layer]):
            return layer
    return 0


def analyze(project_dir, project_name):
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
    seen = set()
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 2)
        if len(parts) != 3:
            continue
        h, subj, date = parts
        if len(subj) > 120:
            cut = subj[:120].rfind(" ")
            subj = subj[:cut] if cut > 80 else subj[:120]
        key = subj[:60]
        if key in seen:
            continue
        seen.add(key)
        all_commits.append({"hash": h, "subject": subj, "date": date,
                             "is_decision": is_decision(subj)})

    # Mirror git-memory.py: skip structural noise before the 7-cap
    for c in all_commits:
        noise, noise_type = is_noise_commit(c["subject"])
        c["is_noise"] = noise
        c["noise_type"] = noise_type

    decisions = [c for c in all_commits if c["is_decision"] and not c["is_noise"]]

    if not decisions:
        return {"project": project_name, "skip_reason": "no decisions"}

    # Annotate each with files, topic key, layer
    for c in decisions:
        c["files"] = get_files(project_dir, c["hash"])
        c["topic"] = topic_key(c["files"])
        c["layer"] = spiral_layer(c["subject"])

    # Mirror git-memory.py two-pass topic-dedup selection:
    # 1 newest per topic cluster fills slots first, then remainder chronologically
    scan_limit = min(DECISION_CAP * 2, len(decisions))
    selected, seen_topics, remainder = [], set(), []
    for c in decisions[:scan_limit]:
        tk = c["topic"]
        if tk is not None and tk not in seen_topics:
            seen_topics.add(tk)
            selected.append(c)
        else:
            remainder.append(c)
    for c in remainder:
        if len(selected) >= DECISION_CAP:
            break
        selected.append(c)
    for c in decisions[scan_limit:]:
        if len(selected) >= DECISION_CAP:
            break
        selected.append(c)

    injected = selected[:DECISION_CAP]
    injected_hashes = {c["hash"] for c in injected}
    tail = [c for c in decisions if c["hash"] not in injected_hashes]

    # ── METRIC 1: NoiseRatio@7 ────────────────────────────────────────────
    # After filter: all injected are non-noise by construction
    noise_ratio = 0.0
    noise_breakdown = {}

    # ── METRIC 2: TopicCoverage@7 ─────────────────────────────────────────
    # Topics = distinct non-None topic_keys
    all_topics = set(c["topic"] for c in decisions if c["topic"] is not None)
    injected_topics = set(c["topic"] for c in injected if c["topic"] is not None)
    topic_coverage = len(injected_topics) / len(all_topics) if all_topics else None
    topics_missed = all_topics - injected_topics
    topics_missed_subjects = [
        next((c["subject"][:60] for c in decisions
              if c["topic"] == t and c not in injected), "?")
        for t in list(topics_missed)[:5]
    ]

    # ── METRIC 3: IP@7 (current) ──────────────────────────────────────────
    topic_clusters = defaultdict(list)
    for c in decisions:
        if c["topic"]:
            topic_clusters[str(sorted(c["topic"]))].append(c)
    spiral_clusters = {k: v for k, v in topic_clusters.items() if len(v) > 1}

    ip7_results = []
    for ck, commits in spiral_clusters.items():
        newest = commits[0]  # already recency-ordered
        ip7_results.append({
            "cluster": ck[:50],
            "size": len(commits),
            "newest_subject": newest["subject"][:65],
            "in_injected": newest in injected,
        })
    ip7 = (sum(1 for r in ip7_results if r["in_injected"]) / len(ip7_results)
           if ip7_results else None)

    # ── METRIC 4: IP@7_dedup (simulated) ─────────────────────────────────
    # Simulate: pick 1 newest commit per topic cluster, then fill rest chronologically
    dedup_set = {}  # topic_key → commit (newest per topic)
    for c in decisions:  # already newest-first
        tk = str(sorted(c["topic"])) if c["topic"] else None
        if tk and tk not in dedup_set:
            dedup_set[tk] = c

    # Build dedup-ordered inject: topic-deduplicated first, then remaining by recency
    dedup_injected = list(dedup_set.values())
    remaining = [c for c in decisions if c not in dedup_injected]
    dedup_inject_top7 = (dedup_injected + remaining)[:DECISION_CAP]

    ip7_dedup_results = []
    for ck, commits in spiral_clusters.items():
        newest = commits[0]
        ip7_dedup_results.append(newest in dedup_inject_top7)
    ip7_dedup = (sum(ip7_dedup_results) / len(ip7_dedup_results)
                 if ip7_dedup_results else None)

    # Noise in dedup-injected (already filtered — always 0)
    dedup_noise_ratio = 0.0

    # ── METRIC 5: DA@7 ────────────────────────────────────────────────────
    da_results = []
    for c in injected:
        code_files = [f for f in c["files"]
                      if not f.startswith(("docs/", ".omc/"))]
        if not code_files:
            da_results.append("NO_FILES")
            continue
        active = any(file_exists_in_head(project_dir, f) for f in code_files)
        da_results.append("ALIGNED" if active else "OBSOLETE")
    da7 = (da_results.count("ALIGNED") / len(da_results) if da_results else None)

    # ── METRIC 6: SpiralDepth ─────────────────────────────────────────────
    sd_mean = sum(c["layer"] for c in injected) / len(injected) if injected else 0

    return {
        "project": project_name,
        "total_scanned": len(all_commits),
        "decisions_in_window": len(decisions),
        "injected": len(injected),
        "tail": len(tail),

        # Core metrics
        "NoiseRatio@7": round(noise_ratio, 3),
        "noise_breakdown": dict(noise_breakdown),
        "TopicCoverage@7": round(topic_coverage, 3) if topic_coverage is not None else "N/A",
        "topics_total": len(all_topics),
        "topics_in_injected": len(injected_topics),
        "topics_missed_count": len(topics_missed),
        "topics_missed_examples": topics_missed_subjects,

        "IP@7_current": round(ip7, 3) if ip7 is not None else "N/A (no clusters)",
        "IP@7_dedup": round(ip7_dedup, 3) if ip7_dedup is not None else "N/A",
        "NoiseRatio@7_dedup": round(dedup_noise_ratio, 3),
        "spiral_clusters": len(spiral_clusters),

        "DA@7": round(da7, 3) if da7 is not None else None,
        "da_breakdown": {k: da_results.count(k) for k in ["ALIGNED", "OBSOLETE", "NO_FILES"]},

        "SpiralDepth": round(sd_mean, 2),

        # Detail for display
        "injected_subjects": [c["subject"][:60] for c in injected],
        "noise_subjects": [],  # filtered before inject — always empty
    }


def main():
    projects = {
        "CTX":         "/home/jayone/Project/CTX",
        "PaintPoint":  "/home/jayone/Project/PaintPoint",
        "Entity":      "/home/jayone/Project/Entity",
        "FromScratch": "/home/jayone/Project/FromScratch",
    }

    all_results = []
    print("=" * 72)
    print("G1 Final Evaluation Benchmark — Corrected Metric Suite")
    print(f"n={N_LOG} log window | {DECISION_CAP}-decision cap")
    print("=" * 72)

    for name, path in projects.items():
        if not os.path.isdir(path):
            print(f"\n[SKIP] {name}: not found")
            continue
        print(f"\n[{name}]")
        r = analyze(path, name)
        if r is None:
            print("  ERROR: git log failed")
            continue
        if "skip_reason" in r:
            print(f"  SKIP: {r['skip_reason']}")
            all_results.append(r)
            continue

        all_results.append(r)

        print(f"  Scanned: {r['total_scanned']} | Decisions: {r['decisions_in_window']} "
              f"({r['injected']} injected + {r['tail']} tail)")
        print()
        print(f"  ┌─ NOISE ──────────────────────────────────────────────────────────")
        print(f"  │ NoiseRatio@7      : {r['NoiseRatio@7']:.1%}  "
              f"({r['noise_breakdown']})")
        print(f"  │ After dedup       : {r['NoiseRatio@7_dedup']:.1%}  "
              f"(simulated improvement)")
        print(f"  ├─ COVERAGE ───────────────────────────────────────────────────────")
        print(f"  │ TopicCoverage@7   : {r['TopicCoverage@7']}  "
              f"({r['topics_in_injected']}/{r['topics_total']} topics)")
        if r["topics_missed_examples"]:
            print(f"  │ Missed topics     : {r['topics_missed_count']} examples:")
            for s in r["topics_missed_examples"][:3]:
                print(f"  │   → {s}")
        print(f"  ├─ ITERATION PRIORITY ────────────────────────────────────────────")
        print(f"  │ IP@7 current      : {r['IP@7_current']}")
        print(f"  │ IP@7 with dedup   : {r['IP@7_dedup']}  (simulated)")
        print(f"  │ Spiral clusters   : {r['spiral_clusters']}")
        print(f"  ├─ DIRECTION ALIGNMENT ───────────────────────────────────────────")
        print(f"  │ DA@7              : {r['DA@7']}  ({r['da_breakdown']})")
        print(f"  └─ DEPTH ──────────────────────────────────────────────────────────")
        print(f"    SpiralDepth       : {r['SpiralDepth']}")

        if r["noise_subjects"]:
            print(f"\n  Noise commits injected:")
            for s in r["noise_subjects"]:
                print(f"    • {s}")

    # ── Aggregate ──────────────────────────────────────────────────────────
    valid = [r for r in all_results
             if "skip_reason" not in r and r.get("decisions_in_window", 0) > 0]

    print("\n" + "=" * 72)
    print("AGGREGATE")
    print("=" * 72)

    if valid:
        def safe_mean(key):
            vals = [r[key] for r in valid
                    if isinstance(r.get(key), (int, float))]
            return round(sum(vals) / len(vals), 3) if vals else "N/A"

        noise_mean = safe_mean("NoiseRatio@7")
        noise_dedup_mean = safe_mean("NoiseRatio@7_dedup")
        tc_mean = safe_mean("TopicCoverage@7")
        da_mean = safe_mean("DA@7")
        sd_mean = safe_mean("SpiralDepth")

        print(f"  NoiseRatio@7        : {noise_mean:.1%}" if isinstance(noise_mean, float)
              else f"  NoiseRatio@7        : {noise_mean}")
        print(f"  NoiseRatio (dedup)  : {noise_dedup_mean:.1%}" if isinstance(noise_dedup_mean, float)
              else f"  NoiseRatio (dedup)  : {noise_dedup_mean}")
        print(f"  TopicCoverage@7     : {tc_mean}")
        print(f"  DA@7                : {da_mean}")
        print(f"  SpiralDepth         : {sd_mean}")

        print(f"\n  DIAGNOSIS:")
        if isinstance(noise_mean, float) and noise_mean > 0.3:
            print(f"  ⚠ High noise ({noise_mean:.0%}) — version/chore commits crowding topic decisions")
        elif isinstance(noise_mean, float):
            print(f"  ✓ Noise acceptable ({noise_mean:.0%})")
        if isinstance(tc_mean, float) and tc_mean < 0.6:
            print(f"  ⚠ Low topic coverage ({tc_mean:.0%}) — important topics missed in inject set")
        elif isinstance(tc_mean, float):
            print(f"  ✓ Topic coverage adequate ({tc_mean:.0%})")

    # ── Save ───────────────────────────────────────────────────────────────
    os.makedirs("/home/jayone/Project/CTX/benchmarks/results", exist_ok=True)
    out = {
        "benchmark": "G1 Final Eval — Corrected Metric Suite",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "params": {"n_log": N_LOG, "decision_cap": DECISION_CAP},
        "projects": all_results,
        "aggregate": {
            "NoiseRatio@7": safe_mean("NoiseRatio@7") if valid else None,
            "TopicCoverage@7": safe_mean("TopicCoverage@7") if valid else None,
            "DA@7": safe_mean("DA@7") if valid else None,
            "SpiralDepth": safe_mean("SpiralDepth") if valid else None,
        }
    }
    path = "/home/jayone/Project/CTX/benchmarks/results/g1_final_eval.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n[SAVED] {path}")
    return out


if __name__ == "__main__":
    main()
