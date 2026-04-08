#!/usr/bin/env python3
"""
G1 Format Ablation Evaluation
==============================
Research question: "어떤 방식의 기억 주입이 LLM 장기기억에 가장 도움이 되는가?"
                  (Which memory injection format helps LLM long-term memory most?)

Tests 5 G1 context formats against the same set of coding decision Q&A tasks
derived from real git history. Measures downstream LLM response quality (δ).

Formats:
  no_ctx         — empty baseline (no context at all)
  random_noise   — 7 raw recent commits including version bumps (OLD G1 failure mode)
  g1_raw         — raw git log n=20, no noise filter (old behavior)
  g1_filtered    — noise-filtered + topic-dedup n=30 (current G1)
  g1_g2_hybrid   — G1 decisions + relevant file names (G1+G2 combined)

Scoring: keyword recall against ground-truth answer keywords
         (same hybrid LLM+keyword method as downstream_llm_eval.py)

Usage:
  python3 benchmarks/eval/g1_format_ablation_eval.py             # real API
  python3 benchmarks/eval/g1_format_ablation_eval.py --dry-run   # simulated
  python3 benchmarks/eval/g1_format_ablation_eval.py --project /path/to/repo
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# ── Optional deps ──────────────────────────────────────────────────────────────
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

ROOT = Path(__file__).parent.parent.parent


# ── Task definitions ──────────────────────────────────────────────────────────

@dataclass
class AblationTask:
    """A single Q&A task grounded in real project git history."""
    task_id: str
    question: str                    # asked to LLM
    answer_keywords: List[str]       # at least one must appear in correct answer
    answer_required: List[str]       # ALL must appear for full credit
    context_hint: str                # which commit range this tests
    difficulty: str = "medium"       # easy / medium / hard


@dataclass
class AblationResult:
    task_id: str
    format_name: str
    question: str
    response: str
    score: float                     # 0.0 – 1.0
    hit_keywords: List[str]
    miss_keywords: List[str]


# ── Git format builders ────────────────────────────────────────────────────────

_STRICT_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+")
_OMC_ITER_RE = re.compile(r"^(omc-live|live-inf)\s+iter", re.IGNORECASE)
_EMBEDDED_DECISION_RE = re.compile(
    r"\s[-—]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
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
    "benchmark", "eval", "decision", "iter",
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


def _get_raw_log(project_dir: str, n: int) -> List[str]:
    """Return list of commit subjects (raw, no filtering)."""
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


def _get_files_for_commit(project_dir: str, commit_hash: str) -> List[str]:
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


def build_format_no_ctx() -> str:
    return ""


def build_format_random_noise(project_dir: str) -> str:
    """7 raw recent commit subjects — includes version bumps and noise (old failure mode)."""
    subjects = _get_raw_log(project_dir, 7)
    if not subjects:
        return "No recent commits found."
    lines = [f"> {s}" for s in subjects[:7]]
    return "[RECENT COMMITS (unfiltered)]\n" + "\n".join(lines)


def build_format_g1_raw(project_dir: str, n: int = 20) -> str:
    """Old G1: n=20, no noise filter — just decision detection, no dedup."""
    subjects = _get_raw_log(project_dir, n)
    decisions = [s for s in subjects if _is_decision(s)][:7]
    if not decisions:
        return "No decisions found in git history."
    lines = [f"> {s}" for s in decisions]
    return "[RECENT DECISIONS (unfiltered, n=20)]\n" + "\n".join(lines)


def build_format_g1_filtered(project_dir: str, n: int = 30) -> str:
    """Current G1: n=30, noise filter + topic-dedup (mirrors git-memory.py)."""
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
        commit_hash, subject = parts
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
            candidates.append({"hash": commit_hash, "subject": subject})

    if not candidates:
        return "No topic decisions found in git history."

    DECISION_CAP = 7
    scan_limit = min(DECISION_CAP * 2, len(candidates))
    for c in candidates[:scan_limit]:
        c["files"] = _get_files_for_commit(project_dir, c["hash"])
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
        if len(selected) >= DECISION_CAP:
            break
        selected.append(c)
    for c in candidates[scan_limit:]:
        if len(selected) >= DECISION_CAP:
            break
        c.setdefault("files", [])
        c.setdefault("topic", None)
        selected.append(c)

    lines = [f"> {c['subject']}" for c in selected[:DECISION_CAP]]
    return "[RECENT DECISIONS (filtered + topic-dedup, n=30)]\n" + "\n".join(lines)


def build_format_g1_g2_hybrid(project_dir: str) -> str:
    """G1 filtered decisions + G2 key file names from recent git activity."""
    g1_ctx = build_format_g1_filtered(project_dir)

    # G2: extract unique files from last 20 commits
    try:
        r = subprocess.run(
            ["git", "log", "-20", "--format=%H"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        hashes = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()][:10]
    except Exception:
        hashes = []

    all_files = []
    seen_files = set()
    for h in hashes:
        for f in _get_files_for_commit(project_dir, h):
            if f not in seen_files and not f.startswith(("docs/", ".omc/")):
                seen_files.add(f)
                all_files.append(f)
        if len(all_files) >= 10:
            break

    g2_ctx = ""
    if all_files:
        file_lines = [f"  - {f}" for f in all_files[:10]]
        g2_ctx = "\n\n[RECENTLY MODIFIED FILES (G2)]\n" + "\n".join(file_lines)

    return g1_ctx + g2_ctx


FORMAT_BUILDERS = {
    "no_ctx":       lambda project_dir: build_format_no_ctx(),
    "random_noise": lambda project_dir: build_format_random_noise(project_dir),
    "g1_raw":       lambda project_dir: build_format_g1_raw(project_dir),
    "g1_filtered":  lambda project_dir: build_format_g1_filtered(project_dir),
    "g1_g2_hybrid": lambda project_dir: build_format_g1_g2_hybrid(project_dir),
}


# ── Task definitions for CTX project ─────────────────────────────────────────

CTX_TASKS = [
    AblationTask(
        task_id="t01",
        question=(
            "The project recently fixed a problem where G1 was injecting useless commits "
            "into the context window. What was the root cause, and which metric measured the "
            "severity of the problem?"
        ),
        answer_keywords=["version", "noise", "omc-iter", "NoiseRatio", "tag", "bump"],
        answer_required=["NoiseRatio", "version"],
        context_hint="G1 noise filter commit (20260407)",
        difficulty="medium",
    ),
    AblationTask(
        task_id="t02",
        question=(
            "After fixing the noise problem, what did the NoiseRatio@7 metric change to, "
            "and what algorithm was used to improve topic diversity in the injected decisions?"
        ),
        answer_keywords=["0%", "zero", "topic", "dedup", "two-pass", "cluster"],
        answer_required=["0%", "dedup"],
        context_hint="G1 noise filter + topic-dedup results",
        difficulty="medium",
    ),
    AblationTask(
        task_id="t03",
        question=(
            "The CTX system was recently redesigned. What are the three hooks that form the "
            "new CTX architecture, and what is the role of each?"
        ),
        answer_keywords=["git-memory", "g2-augment", "auto-index", "G1", "G2", "codebase"],
        answer_required=["git-memory", "g2-augment"],
        context_hint="New CTX architecture commit (20260405)",
        difficulty="hard",
    ),
    AblationTask(
        task_id="t04",
        question=(
            "A benchmark comparing G1 git-log retrieval was performed across 3 projects. "
            "What was the overall recall result before fixes?"
        ),
        answer_keywords=["95%", "recall", "3", "projects", "git-log"],
        answer_required=["recall"],
        context_hint="G1 git-log hook test (20260404)",
        difficulty="easy",
    ),
    AblationTask(
        task_id="t05",
        question=(
            "What is the difference between G1 and G2 in this project? "
            "Specifically, what axis does each cover?"
        ),
        answer_keywords=["time", "space", "temporal", "spatial", "decision", "file", "cross-session"],
        answer_required=["time", "space"],
        context_hint="G1/G2 definition in CLAUDE.md / CTX architecture",
        difficulty="medium",
    ),
    AblationTask(
        task_id="t06",
        question=(
            "The project switched from inject_decisions.py to git-memory.py. "
            "What was the key change in the new approach?"
        ),
        answer_keywords=["git-only", "world-model", "inject", "hook", "dependency"],
        answer_required=["git"],
        context_hint="inject_decisions.py git-only mode + New CTX commit",
        difficulty="medium",
    ),
    AblationTask(
        task_id="t07",
        question=(
            "A G2 prefetch benchmark was run. What was the improvement achieved, "
            "and what were the two enhancements that caused it?"
        ),
        answer_keywords=["65%", "30%", "ko-en", "mapping", "filepath", "prefetch"],
        answer_required=["65%"],
        context_hint="G2 prefetch benchmark (20260405)",
        difficulty="hard",
    ),
    AblationTask(
        task_id="t08",
        question=(
            "The G1 evaluation showed that the project PaintPoint had a 100% NoiseRatio. "
            "What type of commits caused this, and what was the underlying structural reason?"
        ),
        answer_keywords=["PaintPoint", "version", "tag", "versioning", "cap", "recent", "all"],
        answer_required=["PaintPoint", "version"],
        context_hint="G1 final eval benchmark (20260407)",
        difficulty="hard",
    ),
    AblationTask(
        task_id="t09",
        question=(
            "What was the purpose of expanding the git log scan window from n=20 to n=30 "
            "in the G1 implementation?"
        ),
        answer_keywords=["version", "bump", "block", "scan", "window", "reach", "past", "beyond"],
        answer_required=["version", "n=30"],
        context_hint="G1 noise filter commit (scan window expansion)",
        difficulty="medium",
    ),
    AblationTask(
        task_id="t10",
        question=(
            "The project ran a COIR benchmark. What was the BM25 Hit@5 result on the "
            "full corpus, and how many documents were in it?"
        ),
        answer_keywords=["0.640", "280K", "280,000", "BM25", "COIR", "Hit@5"],
        answer_required=["0.640"],
        context_hint="COIR full corpus benchmark (20260403)",
        difficulty="easy",
    ),
]


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
            max_tokens=400,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        # Skip ThinkingBlock — find first text block
        for block in resp.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                return block.text.strip()
        # Fallback: any block with text attr
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

def score_response(response: str, task: AblationTask) -> tuple:
    resp_lower = response.lower()
    hit_required = [kw for kw in task.answer_required if kw.lower() in resp_lower]
    hit_optional = [kw for kw in task.answer_keywords if kw.lower() in resp_lower
                    and kw not in task.answer_required]
    miss_required = [kw for kw in task.answer_required if kw.lower() not in resp_lower]

    # Score: required keywords (weight 0.7) + optional (weight 0.3)
    req_score = len(hit_required) / max(len(task.answer_required), 1)
    opt_score = len(hit_optional) / max(len(task.answer_keywords) - len(task.answer_required), 1) \
        if len(task.answer_keywords) > len(task.answer_required) else 0.0

    score = req_score * 0.7 + opt_score * 0.3
    all_hits = hit_required + hit_optional
    return round(score, 4), all_hits, miss_required


# ── Dry-run simulator ─────────────────────────────────────────────────────────

def simulate_response(task: AblationTask, format_name: str, context: str) -> str:
    """Deterministic simulation for dry-run testing."""
    if not context:
        return "I don't have information about this without context."

    # Simulate: if context contains relevant keywords, return perfect answer
    ctx_lower = context.lower()
    hints = []
    for kw in task.answer_keywords:
        if kw.lower() in ctx_lower:
            hints.append(kw)

    if hints:
        return (f"Based on the context: {'. '.join(hints)}. "
                f"The {task.task_id} answer involves {', '.join(task.answer_required)}.")
    return "The context doesn't contain enough information to answer this question."


# ── Runner ────────────────────────────────────────────────────────────────────

def run_ablation(
    client,
    tasks: List[AblationTask],
    project_dir: str,
    formats: List[str],
    dry_run: bool,
) -> List[AblationResult]:
    # Pre-build all format contexts (once per format, not per task)
    print("\nBuilding format contexts...")
    format_contexts: Dict[str, str] = {}
    for fmt in formats:
        builder = FORMAT_BUILDERS[fmt]
        ctx = builder(project_dir)
        format_contexts[fmt] = ctx
        lines = ctx.count("\n") + 1 if ctx else 0
        print(f"  [{fmt:15s}] {lines} lines | {len(ctx):5d} chars")

    results = []
    total = len(tasks) * len(formats)
    done = 0

    for task in tasks:
        for fmt in formats:
            context = format_contexts[fmt]
            if dry_run:
                resp = simulate_response(task, fmt, context)
            else:
                user_msg = (
                    f"{context}\n\n---\n\nQuestion: {task.question}"
                    if context
                    else f"Question: {task.question}"
                )
                resp = call_llm(client, SYS_PROMPT, user_msg)
                time.sleep(0.25)

            score, hits, misses = score_response(resp, task)
            results.append(AblationResult(
                task_id=task.task_id,
                format_name=fmt,
                question=task.question,
                response=resp[:300],
                score=score,
                hit_keywords=hits,
                miss_keywords=misses,
            ))
            done += 1
            bar = "#" * (done * 20 // total) + "." * (20 - done * 20 // total)
            print(f"\r  [{bar}] {done}/{total}  {task.task_id} × {fmt}", end="", flush=True)

    print()
    return results


# ── Aggregation + report ──────────────────────────────────────────────────────

def aggregate(results: List[AblationResult], formats: List[str]) -> Dict:
    by_format: Dict[str, List[float]] = {f: [] for f in formats}
    by_task: Dict[str, Dict[str, float]] = {}

    for r in results:
        by_format[r.format_name].append(r.score)
        if r.task_id not in by_task:
            by_task[r.task_id] = {}
        by_task[r.task_id][r.format_name] = r.score

    summary = {}
    for fmt in formats:
        scores = by_format[fmt]
        if scores:
            mean = sum(scores) / len(scores)
            summary[fmt] = {
                "mean_score": round(mean, 4),
                "n": len(scores),
                "scores": [round(s, 4) for s in scores],
            }

    baseline = summary.get("no_ctx", {}).get("mean_score", 0.0)
    for fmt in formats:
        if fmt in summary:
            summary[fmt]["delta_vs_baseline"] = round(
                summary[fmt]["mean_score"] - baseline, 4
            )

    return {"per_format": summary, "per_task": by_task, "baseline": baseline}


def print_report(agg: Dict, formats: List[str]) -> None:
    sep = "=" * 70
    print(f"\n{sep}")
    print("  G1 FORMAT ABLATION — DOWNSTREAM LLM δ MEASUREMENT")
    print("  Research: Which memory injection format helps LLM recall most?")
    print(sep)

    per_fmt = agg["per_format"]
    baseline = agg["baseline"]

    print(f"\n  {'Format':<20} {'Mean Score':>12} {'δ vs baseline':>14} {'Verdict'}")
    print(f"  {'-'*65}")
    for fmt in formats:
        d = per_fmt.get(fmt, {})
        mean = d.get("mean_score", 0.0)
        delta = d.get("delta_vs_baseline", 0.0)
        if fmt == "no_ctx":
            verdict = "(baseline)"
        elif delta > 0.25:
            verdict = "STRONG GAIN"
        elif delta > 0.10:
            verdict = "MODERATE GAIN"
        elif delta > 0.02:
            verdict = "MARGINAL GAIN"
        elif delta > -0.02:
            verdict = "NO EFFECT"
        else:
            verdict = "DEGRADATION"
        print(f"  {fmt:<20} {mean:>12.3f} {delta:>+14.3f}  {verdict}")

    print(f"\n  {'─'*65}")
    best_fmt = max(formats, key=lambda f: per_fmt.get(f, {}).get("mean_score", 0))
    best_delta = per_fmt.get(best_fmt, {}).get("delta_vs_baseline", 0)
    print(f"  Best format: {best_fmt}  (mean={per_fmt[best_fmt]['mean_score']:.3f}, δ={best_delta:+.3f})")

    print(f"\n  Per-task breakdown:")
    print(f"  {'Task':<8}", end="")
    for fmt in formats:
        print(f"  {fmt[:12]:>12}", end="")
    print()
    print(f"  {'─'*65}")
    for tid, fmt_scores in sorted(agg["per_task"].items()):
        print(f"  {tid:<8}", end="")
        for fmt in formats:
            score = fmt_scores.get(fmt, 0.0)
            print(f"  {score:>12.3f}", end="")
        print()

    print(f"\n  Research answer:")
    if best_delta > 0.10:
        print(f"  '{best_fmt}' format provides the strongest downstream LLM benefit")
        print(f"  ({best_delta:+.3f} improvement over no-context baseline)")
    elif best_delta > 0:
        print(f"  '{best_fmt}' format shows marginal benefit ({best_delta:+.3f})")
        print(f"  Context injection effect may be task-dependent or dataset-limited.")
    else:
        print(f"  No format shows clear benefit over baseline — context may be misaligned.")
    print(sep)


def save_results(agg: Dict, results: List[AblationResult], formats: List[str]) -> Path:
    out_dir = ROOT / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"g1_format_ablation_{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "formats_tested": formats,
        "n_tasks": len(set(r.task_id for r in results)),
        "summary": agg,
        "results": [asdict(r) for r in results],
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="G1 format ablation downstream δ measurement"
    )
    parser.add_argument(
        "--project", default=str(ROOT),
        help="Git project directory to extract context from (default: CTX repo)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use simulated responses (no API calls)"
    )
    parser.add_argument(
        "--formats", nargs="+",
        default=["no_ctx", "random_noise", "g1_raw", "g1_filtered", "g1_g2_hybrid"],
        help="Formats to test"
    )
    parser.add_argument(
        "--tasks", nargs="+", default=None,
        help="Specific task IDs to run (default: all)"
    )
    args = parser.parse_args()

    # Load env for API keys
    env_file = Path.home() / ".claude" / "env" / "shared.env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    client = get_llm_client()
    if client is None and not args.dry_run:
        print("[WARN] No API key found — switching to dry-run mode")
        args.dry_run = True
    elif client is not None:
        backend = "MiniMax" if os.environ.get("MINIMAX_API_KEY") else "Anthropic"
        model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
        print(f"Backend: {backend} | Model: {model}")
    else:
        print("[DRY-RUN] Simulated LLM responses")

    tasks = CTX_TASKS
    if args.tasks:
        tasks = [t for t in tasks if t.task_id in args.tasks]
    print(f"Tasks: {len(tasks)} | Formats: {args.formats}")
    print(f"Project: {args.project}")

    if args.dry_run:
        print("[DRY-RUN] No API calls will be made")

    results = run_ablation(
        client=client,
        tasks=tasks,
        project_dir=args.project,
        formats=args.formats,
        dry_run=args.dry_run,
    )

    agg = aggregate(results, args.formats)
    print_report(agg, args.formats)
    out_path = save_results(agg, results, args.formats)
    print(f"\nResults saved: {out_path.name}")


if __name__ == "__main__":
    main()
