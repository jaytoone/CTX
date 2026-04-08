#!/usr/bin/env python3
"""
G1 Temporal Retention Evaluation
==================================
Research question: Which G1 context format best preserves recall of old decisions as time passes?

Design: Temporal hold-out
  For each age N in [3, 7, 15, 30] commits back from HEAD:
    1. Identify the commit at position N (target decision)
    2. Build each format's context from current HEAD (present-time view)
    3. Ask LLM to recall facts from that past decision
    4. Score keyword recall -> retention_curve[age][format]

Expected behavior:
  random_noise (window=7): recall collapses at age > 7
  g1_raw       (window=20): recall collapses at age > 20
  g1_filtered  (window=30, topic-dedup): maintains recall up to age ~30,
               but may skip some commits via topic-dedup

Hypothesis: g1_filtered degrades less over time because topic-dedup
distributes 7 slots across diverse topics, covering older decisions.

Usage:
  python3 benchmarks/eval/g1_temporal_retention_eval.py
  python3 benchmarks/eval/g1_temporal_retention_eval.py --dry-run
  python3 benchmarks/eval/g1_temporal_retention_eval.py --ages 3,7,15,30
  python3 benchmarks/eval/g1_temporal_retention_eval.py --project /path/to/repo
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

ROOT = Path(__file__).parent.parent.parent


# ── Keyword extraction ─────────────────────────────────────────────────────────

_RATIO_RE = re.compile(r"\d+\.\d{2,}")
_PCT_RE = re.compile(r"\d+%")
_ARROW_RE = re.compile(r"\d+[%]?\s*->\s*\d+[%]?")
_CAPS_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


def extract_keywords(subject: str) -> List[str]:
    """Extract factually testable keywords from a commit subject line."""
    kws = []
    for m in _ARROW_RE.finditer(subject):
        kws.append(m.group(0).strip())
    for m in _PCT_RE.finditer(subject):
        kws.append(m.group(0))
    for m in _RATIO_RE.finditer(subject):
        kws.append(m.group(0))
    for m in _CAPS_RE.finditer(subject):
        kws.append(m.group(0))
    seen = set()
    result = []
    for k in kws:
        if k not in seen:
            seen.add(k)
            result.append(k)
    if not result:
        tokens = re.split(r"[\s:+\-]", subject)
        for tok in tokens:
            if len(tok) > 3 and not tok.isdigit():
                result.append(tok)
                if len(result) >= 4:
                    break
    return result[:8]


def build_question(subject: str) -> str:
    hint = subject[:50].rsplit(" ", 1)[0] if len(subject) > 50 else subject
    return (
        f"The project made a change described as: '{hint}...'. "
        f"What were the specific details, metrics, or outcomes of this change? "
        f"Give exact numbers or values if you know them."
    )


# ── Git helpers ────────────────────────────────────────────────────────────────

@dataclass
class CommitInfo:
    age: int
    hash: str
    subject: str
    date: str
    keywords: List[str]
    question: str


def get_commits_at_ages(project_dir: str, ages: List[int]) -> List[CommitInfo]:
    max_age = max(ages) + 1
    try:
        r = subprocess.run(
            ["git", "log", f"-{max_age}", "--format=%H\x1f%ai\x1f%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return []
        lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
    except Exception:
        return []

    commits = []
    for age in sorted(ages):
        if age >= len(lines):
            continue
        parts = lines[age].split("\x1f", 2)
        if len(parts) < 3:
            continue
        chash, date, subject = parts
        kws = extract_keywords(subject)
        commits.append(CommitInfo(
            age=age,
            hash=chash[:8],
            subject=subject,
            date=date[:10],
            keywords=kws,
            question=build_question(subject),
        ))
    return commits


# ── Format builders ────────────────────────────────────────────────────────────

_STRICT_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+")
_OMC_ITER_RE = re.compile(r"^(omc-live|live-inf)\s+iter", re.IGNORECASE)
_EMBEDDED_DECISION_RE = re.compile(
    r"\s[-]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
    re.IGNORECASE
)
_CONV_PREFIXES = (
    "feat:", "fix:", "refactor:", "perf:", "security:", "design:", "test:",
    "feat(", "fix(", "refactor(", "perf(",
)
_VERSION_RE = re.compile(r"^v\d+\.\d+")
_DECISION_KEYWORDS = (
    "pivot", "revert", "dead-end", "rejected", "chose", "switched",
    "CONVERGED", "failed", "success", "fix", "improvement",
    "benchmark", "decision", "iter",
)
_NOISE_PREFIXES = ("# ", "wip:", "merge ", 'revert "')


def _is_structural_noise(subject: str) -> bool:
    s = subject.strip()
    if _OMC_ITER_RE.match(s):
        return True
    if _STRICT_VERSION_RE.match(s):
        return not bool(_EMBEDDED_DECISION_RE.search(s))
    return False


def _is_decision(subject: str) -> bool:
    s = subject.strip()
    if not s:
        return False
    sl = s.lower()
    if any(sl.startswith(p) for p in _NOISE_PREFIXES):
        return False
    if any(sl.startswith(p) for p in _CONV_PREFIXES):
        return True
    if _VERSION_RE.match(s):
        return True
    return any(kw.lower() in sl for kw in _DECISION_KEYWORDS)


def _raw_log(project_dir: str, n: int) -> List[str]:
    try:
        r = subprocess.run(
            ["git", "log", f"-{n}", "--format=%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return []
        return [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
    except Exception:
        return []


def _files_for_commit(project_dir: str, commit_hash: str) -> List[str]:
    try:
        r = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            cwd=project_dir, capture_output=True, text=True, timeout=3
        )
        return [l.strip() for l in r.stdout.strip().split("\n") if l.strip()] if r.returncode == 0 else []
    except Exception:
        return []


def _topic_key(files: List[str]):
    code = [f for f in files
            if f.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs"))
            and not f.startswith(("tests/", "test_", "docs/"))]
    return frozenset(sorted(code)[:2]) if code else None


def fmt_no_ctx(_: str) -> str:
    return ""


def fmt_random_noise(project_dir: str) -> str:
    subjects = _raw_log(project_dir, 7)
    if not subjects:
        return "No recent commits found."
    return "[RECENT COMMITS (unfiltered)]\n" + "\n".join(f"> {s}" for s in subjects[:7])


def fmt_g1_raw(project_dir: str) -> str:
    subjects = _raw_log(project_dir, 20)
    decisions = [s for s in subjects if _is_decision(s)][:7]
    if not decisions:
        return "No decisions found in git history."
    return "[RECENT DECISIONS (unfiltered, n=20)]\n" + "\n".join(f"> {s}" for s in decisions)


def fmt_g1_filtered(project_dir: str, n: int = 30) -> str:
    try:
        r = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H\x1f%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return "Git history unavailable."
    except Exception:
        return "Git history unavailable."

    candidates = []
    seen_subjects = set()
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 1)
        if len(parts) != 2:
            continue
        chash, subject = parts
        if len(subject) > 120:
            cut = subject[:120].rfind(" ")
            subject = subject[:cut] if cut > 80 else subject[:120]
        if _is_structural_noise(subject):
            continue
        key = subject[:60]
        if key in seen_subjects:
            continue
        seen_subjects.add(key)
        if _is_decision(subject):
            candidates.append({"hash": chash, "subject": subject})

    if not candidates:
        return "No topic decisions found in git history."

    CAP = 7
    scan_limit = min(CAP * 2, len(candidates))
    for c in candidates[:scan_limit]:
        c["files"] = _files_for_commit(project_dir, c["hash"])
        c["topic"] = _topic_key(c["files"])

    selected = []
    seen_topics = set()
    remainder = []
    for c in candidates[:scan_limit]:
        tk = c.get("topic")
        if tk is not None and tk not in seen_topics:
            seen_topics.add(tk)
            selected.append(c)
        else:
            remainder.append(c)
    for c in remainder:
        if len(selected) >= CAP:
            break
        selected.append(c)
    for c in candidates[scan_limit:]:
        if len(selected) >= CAP:
            break
        c.setdefault("files", [])
        c.setdefault("topic", None)
        selected.append(c)

    lines = [f"> {c['subject']}" for c in selected[:CAP]]
    return "[RECENT DECISIONS (filtered + topic-dedup, n=30)]\n" + "\n".join(lines)


def fmt_g1_g2_hybrid(project_dir: str) -> str:
    g1_ctx = fmt_g1_filtered(project_dir)
    try:
        r = subprocess.run(
            ["git", "log", "-20", "--format=%H"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        hashes = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()][:10]
    except Exception:
        hashes = []

    all_files: List[str] = []
    seen_files: set = set()
    for h in hashes:
        for f in _files_for_commit(project_dir, h):
            if f not in seen_files and not f.startswith(("docs/", ".omc/")):
                seen_files.add(f)
                all_files.append(f)
        if len(all_files) >= 10:
            break

    if all_files:
        g2_ctx = "\n\n[RECENTLY MODIFIED FILES (G2)]\n" + "\n".join(f"  - {f}" for f in all_files[:10])
        return g1_ctx + g2_ctx
    return g1_ctx


FORMAT_BUILDERS = {
    "no_ctx":       fmt_no_ctx,
    "random_noise": fmt_random_noise,
    "g1_raw":       fmt_g1_raw,
    "g1_filtered":  fmt_g1_filtered,
    "g1_g2_hybrid": fmt_g1_g2_hybrid,
}

FORMATS = list(FORMAT_BUILDERS.keys())


# ── LLM client ────────────────────────────────────────────────────────────────

def get_llm_client():
    if not HAS_ANTHROPIC:
        return None
    api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("MINIMAX_BASE_URL") or None
    if base_url:
        return anthropic.Anthropic(api_key=api_key, base_url=base_url)
    return anthropic.Anthropic(api_key=api_key)


def call_llm(client, system_prompt: str, user_msg: str) -> str:
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in resp.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                return block.text.strip()
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[NO-TEXT-BLOCK]"
    except Exception as e:
        return f"[LLM_ERROR: {e}]"


SYS_PROMPT = (
    "You are a software engineer recalling decisions made in a coding project. "
    "Use ONLY the context provided (if any) to answer. "
    "Be specific with exact values, names, and numbers from the context. "
    "If context is empty or doesn't contain the answer, say 'I don't have information about this.'"
)


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_keywords(response: str, keywords: List[str]) -> Tuple[float, List[str], List[str]]:
    resp_lower = response.lower()
    hits = [kw for kw in keywords if kw.lower() in resp_lower]
    misses = [kw for kw in keywords if kw.lower() not in resp_lower]
    score = len(hits) / max(len(keywords), 1)
    return round(score, 4), hits, misses


# ── Dry-run simulation ────────────────────────────────────────────────────────

def simulate_response(commit: CommitInfo, context: str) -> str:
    if not context:
        return "I don't have information about this without context."
    hits = [kw for kw in commit.keywords if kw.lower() in context.lower()]
    if len(hits) >= len(commit.keywords) // 2:
        return f"Based on context: {'. '.join(hits)}. Commit: {commit.subject[:60]}."
    return "The context doesn't contain the specific details for this change."


# ── Core runner ───────────────────────────────────────────────────────────────

@dataclass
class RetentionResult:
    age: int
    commit_hash: str
    commit_subject: str
    commit_date: str
    format_name: str
    question: str
    response: str
    keywords: List[str]
    hits: List[str]
    misses: List[str]
    score: float
    in_window: bool


def run_retention_study(
    client,
    project_dir: str,
    ages: List[int],
    dry_run: bool,
) -> Tuple[List[RetentionResult], List[CommitInfo]]:

    print(f"\nProject: {project_dir}")
    commits = get_commits_at_ages(project_dir, ages)
    if not commits:
        print("ERROR: Could not retrieve commits.")
        return [], []

    print(f"\nTarget commits (temporal hold-out):")
    print(f"  {'Age':>4}  {'Hash':>8}  {'Date':>10}  Subject")
    print(f"  {'----':>4}  {'--------':>8}  {'----------':>10}  -------")
    for c in commits:
        kw_str = ", ".join(c.keywords[:4]) + ("..." if len(c.keywords) > 4 else "")
        print(f"  {c.age:>4}  {c.hash:>8}  {c.date:>10}  {c.subject[:55]}")
        print(f"  {'':>4}  {'':>8}  {'':>10}    keywords: [{kw_str}]")

    print(f"\nBuilding present-time format contexts...")
    format_contexts: Dict[str, str] = {}
    for fmt in FORMATS:
        ctx = FORMAT_BUILDERS[fmt](project_dir)
        format_contexts[fmt] = ctx
        lines = ctx.count("\n") + 1 if ctx else 0
        print(f"  [{fmt:15s}] {lines} lines | {len(ctx):5d} chars")

    total = len(commits) * len(FORMATS)
    print(f"\nRunning recall queries ({len(commits)} ages x {len(FORMATS)} formats = {total} calls)...")

    results: List[RetentionResult] = []
    done = 0

    for commit in commits:
        for fmt in FORMATS:
            context = format_contexts[fmt]
            # Actual inclusion check: does target commit subject appear in context?
            in_window = commit.subject[:40].lower() in context.lower()

            if dry_run:
                resp = simulate_response(commit, context)
            else:
                user_msg = (
                    f"{context}\n\n---\n\nQuestion: {commit.question}"
                    if context else
                    f"Question: {commit.question}"
                )
                resp = call_llm(client, SYS_PROMPT, user_msg)
                time.sleep(0.3)

            score, hits, misses = score_keywords(resp, commit.keywords)
            results.append(RetentionResult(
                age=commit.age,
                commit_hash=commit.hash,
                commit_subject=commit.subject,
                commit_date=commit.date,
                format_name=fmt,
                question=commit.question,
                response=resp[:300],
                keywords=commit.keywords,
                hits=hits,
                misses=misses,
                score=score,
                in_window=in_window,
            ))
            done += 1
            bar = "#" * (done * 20 // total) + "." * (20 - done * 20 // total)
            print(f"\r  [{bar}] {done}/{total}  age={commit.age} x {fmt}", end="", flush=True)

    print()
    return results, commits


# ── Aggregation & display ─────────────────────────────────────────────────────

def build_retention_curve(results: List[RetentionResult]) -> Dict:
    from collections import defaultdict
    scores = defaultdict(lambda: defaultdict(float))
    windows = defaultdict(lambda: defaultdict(bool))

    for r in results:
        scores[r.age][r.format_name] = r.score
        windows[r.age][r.format_name] = r.in_window

    agg = {}
    for age in sorted(scores.keys()):
        agg[age] = {
            fmt: {"score": scores[age][fmt], "in_window": windows[age][fmt]}
            for fmt in FORMATS
        }
    return agg


def print_report(results: List[RetentionResult], commits: List[CommitInfo], curve: Dict):
    print("\n" + "=" * 74)
    print("  G1 TEMPORAL RETENTION — RECALL DECAY CURVE")
    print("  Research: Which format best preserves recall of old decisions?")
    print("=" * 74)

    # Per-commit info
    for c in commits:
        print(f"\n  Age={c.age} | {c.hash} | {c.date}")
        print(f"  Commit: {c.subject[:65]}")
        print(f"  Keywords: {c.keywords}")
        window_flags = " | ".join(
            f"{fmt}={'IN ' if curve[c.age][fmt]['in_window'] else 'OUT'}"
            for fmt in FORMATS
        )
        print(f"  Window:  [{window_flags}]")

    # Retention curve table
    print(f"\n  Retention Curve (score = keyword recall of past decision):")
    header = f"  {'Age':>4}  " + "  ".join(f"{f:>13}" for f in FORMATS)
    print(f"\n{header}")
    print("  " + "-" * (6 + 15 * len(FORMATS)))

    for age in sorted(curve.keys()):
        row = f"  {age:>4}  "
        for fmt in FORMATS:
            score = curve[age][fmt]["score"]
            in_win = curve[age][fmt]["in_window"]
            mark = " " if in_win else "*"
            row += f"  {score:>9.3f}{mark}  "
        print(row)

    print()
    print("  (* = commit NOT present in format's context window)")

    # Decay analysis: mean recall when in-window vs out-of-window
    print(f"\n  Decay Analysis (mean recall by window membership):")
    print(f"  {'Format':15s}  {'in_window':>10}  {'out_window':>10}  {'gap':>8}")
    print(f"  {'-'*15}  {'-'*10}  {'-'*10}  {'-'*8}")
    for fmt in FORMATS:
        in_scores = [curve[age][fmt]["score"] for age in sorted(curve) if curve[age][fmt]["in_window"]]
        out_scores = [curve[age][fmt]["score"] for age in sorted(curve) if not curve[age][fmt]["in_window"]]
        in_mean = sum(in_scores) / len(in_scores) if in_scores else 0.0
        out_mean = sum(out_scores) / len(out_scores) if out_scores else 0.0
        gap = in_mean - out_mean
        print(f"  {fmt:15s}  {in_mean:>10.3f}  {out_mean:>10.3f}  {gap:>+8.3f}")

    # Best format per age
    print(f"\n  Best format per age:")
    for age in sorted(curve.keys()):
        best_fmt = max(FORMATS, key=lambda f: curve[age][f]["score"])
        best_score = curve[age][best_fmt]["score"]
        print(f"  Age {age:>2}: {best_fmt:15s} (score={best_score:.3f})")

    # Hypothesis result
    print(f"\n  Hypothesis: g1_filtered degrades less than random_noise over time?")
    print(f"  {'Age':>4}  {'random_noise':>12}  {'g1_filtered':>12}  {'delta':>8}  verdict")
    print(f"  {'-'*4}  {'-'*12}  {'-'*12}  {'-'*8}  -------")
    for age in sorted(curve.keys()):
        rn = curve[age]["random_noise"]["score"]
        gf = curve[age]["g1_filtered"]["score"]
        delta = gf - rn
        if delta > 0.05:
            verdict = "g1_filtered BETTER"
        elif delta < -0.05:
            verdict = "random_noise BETTER"
        else:
            verdict = "TIED"
        print(f"  {age:>4}  {rn:>12.3f}  {gf:>12.3f}  {delta:>+8.3f}  {verdict}")

    print("=" * 74)


def save_results(
    results: List[RetentionResult],
    commits: List[CommitInfo],
    curve: Dict,
    project_dir: str,
) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(project_dir) / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"g1_temporal_retention_{ts}.json"
    data = {
        "timestamp": ts,
        "project": project_dir,
        "commits": [asdict(c) for c in commits],
        "retention_curve": {str(k): v for k, v in curve.items()},
        "raw_results": [asdict(r) for r in results],
    }
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved: {out_path.name}")
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="G1 Temporal Retention Study")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate LLM responses (no API calls)")
    parser.add_argument("--ages", default="3,7,15,30",
                        help="Comma-separated commit ages to test (default: 3,7,15,30)")
    parser.add_argument("--project", default=str(ROOT),
                        help="Path to target git repo")
    args = parser.parse_args()

    ages = [int(a.strip()) for a in args.ages.split(",")]
    project_dir = args.project

    if not args.dry_run:
        source_env = Path.home() / ".claude" / "env" / "shared.env"
        if source_env.exists():
            env_out = subprocess.run(
                ["bash", "-c", f"source {source_env} && env"],
                capture_output=True, text=True
            )
            for line in env_out.stdout.split("\n"):
                if "=" in line:
                    k, _, v = line.partition("=")
                    if k in ("MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_MODEL",
                             "ANTHROPIC_API_KEY"):
                        os.environ[k] = v

    client = None if args.dry_run else get_llm_client()
    if not args.dry_run and client is None:
        print("ERROR: No LLM client. Set MINIMAX_API_KEY or use --dry-run.")
        sys.exit(1)

    backend = "DRY-RUN" if args.dry_run else os.environ.get("MINIMAX_MODEL", "unknown")
    print(f"Backend: {backend} | Ages: {ages} | Project: {project_dir}")

    results, commits = run_retention_study(client, project_dir, ages, args.dry_run)
    if not results:
        sys.exit(1)

    curve = build_retention_curve(results)
    print_report(results, commits, curve)
    save_results(results, commits, curve, project_dir)


if __name__ == "__main__":
    main()
