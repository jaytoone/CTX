"""
downstream_llm_eval.py — CTX Downstream LLM Quality Evaluation

Measures ACTUAL LLM performance improvement when CTX provides context.
This is the true evaluation of CTX value: not "did retrieval find the right file?"
but "did the LLM answer better when given CTX-retrieved context?"

G1 (Cross-session recall):
  WITH CTX:    persistent_memory injected → LLM recalls past files correctly
  WITHOUT CTX: No memory injection → LLM cannot recall
  Metric: Answer Accuracy (AA) = fraction of expected keywords mentioned

G2 (Instruction-grounded coding):
  WITH CTX:    CTX-retrieved relevant files shown as context
  WITHOUT CTX: No file context
  Metrics:
    File Reference Accuracy (FRA): fraction of correct files/functions mentioned
    Hallucination Rate (HR):       non-existent .py files mentioned per response

Usage:
  python3 benchmarks/eval/downstream_llm_eval.py [--dry-run] [--n-scenarios 10]
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
DATASET_DIR = ROOT / "benchmarks" / "datasets"


# ── LLM client ───────────────────────────────────────────────────────────────

def get_llm_client():
    try:
        import anthropic
        # MiniMax (Anthropic-compatible endpoint) — preferred when available
        minimax_key = os.environ.get("MINIMAX_API_KEY", "")
        minimax_url = os.environ.get("MINIMAX_BASE_URL", "")
        if minimax_key and minimax_url:
            return anthropic.Anthropic(api_key=minimax_key, base_url=minimax_url)
        # Native Anthropic fallback
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            return None
        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None


def call_llm(client, system: str, user: str,
             model: str = "",
             max_tokens: int = 512) -> str:
    if not model:
        model = os.environ.get("MINIMAX_MODEL") or "claude-haiku-4-5-20251001"
    if client is None:
        return "[NO-CLIENT]"
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
            system=system,
        )
        # Skip ThinkingBlock — find first text block
        for block in resp.content:
            block_type = getattr(block, "type", "")
            if block_type == "text" and hasattr(block, "text"):
                return block.text.strip()
        # Fallback: any block with text attr
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[NO-TEXT-BLOCK]"
    except Exception as exc:
        return f"[LLM-ERROR] {exc}"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class G1Scenario:
    scenario_id: str
    past_files: List[str]
    question: str
    expected_keywords: List[str]


@dataclass
class G2Task:
    task_id: str
    instruction: str
    relevant_files: List[str]
    relevant_functions: List[str]
    all_known_files: List[str]


@dataclass
class EvalResult:
    scenario_id: str
    goal: str
    condition: str           # "with_ctx" or "without_ctx"
    response: str
    score: float
    correct_mentions: List[str]
    hallucinated_mentions: List[str]


# ── Dataset loading ───────────────────────────────────────────────────────────

def load_dataset(name: str = "small") -> dict:
    path = DATASET_DIR / name / "metadata.json"
    with open(path) as fh:
        return json.load(fh)


# ── Scenario builders ─────────────────────────────────────────────────────────

def build_g1_scenarios(files_meta: List[dict], n: int = 10, seed: int = 42) -> List[G1Scenario]:
    import random
    rng = random.Random(seed)

    concept_groups: Dict[str, List[dict]] = {}
    for fm in files_meta:
        for c in fm.get("concepts", []):
            concept_groups.setdefault(c, []).append(fm)

    q_templates = [
        "Which files did we work on related to {concept}?",
        "What module handles {concept} in this project?",
        "In our last session, which files were involved in {concept} operations?",
        "Can you recall the files we accessed for {concept} implementation?",
        "What was the main file for the {concept} feature?",
    ]

    concepts = [c for c, flist in concept_groups.items() if len(flist) >= 2]
    rng.shuffle(concepts)
    scenarios = []
    for i, concept in enumerate(concepts[:n]):
        group = concept_groups[concept]
        past_files = [fm["path"] for fm in rng.sample(group, min(3, len(group)))]
        q = rng.choice(q_templates).format(concept=concept)
        scenarios.append(G1Scenario(
            scenario_id=f"g1_{i:02d}",
            past_files=past_files,
            question=q,
            expected_keywords=past_files + [concept],
        ))
    return scenarios


def build_g2_tasks(files_meta: List[dict], n: int = 10) -> List[G2Task]:
    INSTRUCTIONS = [
        ("Implement user authentication with JWT tokens", ["auth", "session", "jwt"]),
        ("Add database connection pooling", ["database", "db", "connection"]),
        ("Implement Redis caching layer", ["cache", "caching", "redis"]),
        ("Add API rate limiting middleware", ["api", "rate", "limit"]),
        ("Set up structured logging pipeline", ["logging", "log", "event"]),
        ("Build task scheduler with cron", ["schedule", "scheduler", "cron"]),
        ("Implement email notification service", ["email", "notification", "message"]),
        ("Add user analytics event tracking", ["analytics", "metrics", "tracking"]),
        ("Implement full-text search functionality", ["search", "index", "query"]),
        ("Build webhook event handler", ["webhook", "event", "handler"]),
    ]

    all_paths = [fm["path"] for fm in files_meta]
    tasks = []
    for i, (instruction, keywords) in enumerate(INSTRUCTIONS[:n]):
        relevant = []
        for fm in files_meta:
            file_concepts = [c.lower() for c in fm.get("concepts", [])]
            module = fm.get("module_name", "").lower()
            path = fm.get("path", "").lower()
            if any(k in file_concepts or k in module or k in path for k in keywords):
                relevant.append(fm)
        if not relevant:
            continue
        rel_files = [fm["path"] for fm in relevant[:3]]
        rel_funcs: List[str] = []
        for fm in relevant[:3]:
            rel_funcs.extend(fm.get("functions", []))
            rel_funcs.extend(fm.get("classes", []))
        tasks.append(G2Task(
            task_id=f"g2_{i:02d}",
            instruction=instruction,
            relevant_files=rel_files,
            relevant_functions=rel_funcs[:6],
            all_known_files=all_paths,
        ))
    return tasks[:n]


# ── Context builders ──────────────────────────────────────────────────────────

def ctx_g1_with(scenario: G1Scenario) -> str:
    memory = {
        "cwd": "/project",
        "files": {
            fpath: {"access_count": 4, "last_tool": "Edit",
                    "summary": f"Actively modified: {fpath}"}
            for fpath in scenario.past_files
        },
    }
    return (
        "== CTX Memory (previous session) ==\n"
        + json.dumps(memory, indent=2)
        + "\n== End CTX Memory =="
    )


def ctx_g2_with(task: G2Task, dataset_name: str = "small") -> str:
    codebase_dir = DATASET_DIR / dataset_name / "codebase"
    parts = ["== CTX Retrieved Files =="]
    for rel in task.relevant_files[:3]:
        full = codebase_dir / rel
        if full.exists():
            with open(full) as fh:
                snippet = fh.read()[:800]
        else:
            snippet = "# (content unavailable in dataset)"
        parts.append(f"\n--- {rel} ---\n{snippet}\n")
    parts.append("== End CTX Retrieved Files ==")
    return "\n".join(parts)


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_g1(response: str, scenario: G1Scenario) -> Tuple[float, List[str], List[str]]:
    resp_lower = response.lower()
    correct = []
    for kw in scenario.expected_keywords:
        base = Path(kw).stem.lower()
        if base in resp_lower or kw.lower() in resp_lower:
            correct.append(kw)
    score = len(correct) / max(len(scenario.expected_keywords), 1)
    return score, correct, []


def score_g2(response: str, task: G2Task) -> Tuple[float, List[str], List[str]]:
    resp_lower = response.lower()
    correct = []
    for fpath in task.relevant_files:
        base = Path(fpath).stem.lower()
        if base in resp_lower or fpath.lower() in resp_lower:
            correct.append(fpath)
    for fn in task.relevant_functions:
        if fn.lower() in resp_lower:
            correct.append(fn)

    hallucinated = []
    mentioned_py = re.findall(r'\b[\w/]+\.py\b', response)
    known_bases = {Path(f).stem.lower() for f in task.all_known_files}
    for mp in mentioned_py:
        base = Path(mp).stem.lower()
        if base not in known_bases and len(base) > 4:
            hallucinated.append(mp)

    n_expected = len(task.relevant_files) + len(task.relevant_functions)
    score = len(correct) / max(n_expected, 1)
    return score, correct, hallucinated


# ── Dry-run simulators ────────────────────────────────────────────────────────

def simulate_g1_with(scenario: G1Scenario) -> str:
    return (
        f"Based on the CTX session memory, the files we worked on were: "
        f"{', '.join(scenario.past_files)}. "
        f"These files were actively modified in the previous session."
    )


def simulate_g1_without(_scenario: G1Scenario) -> str:
    return (
        "I don't have access to previous session information. "
        "I cannot recall which specific files were worked on without memory context."
    )


def simulate_g2_with(task: G2Task) -> str:
    files_str = ", ".join(task.relevant_files[:2])
    funcs_str = ", ".join(task.relevant_functions[:3])
    return (
        f"Based on the retrieved files, you should modify {files_str}. "
        f"Key functions to use: {funcs_str}. "
        f"The context shows the relevant implementation details."
    )


def simulate_g2_without(_task: G2Task) -> str:
    return (
        "Without codebase context, I'd suggest creating a new service file. "
        "You might need to modify config/settings.py and create a handler.py module. "
        "Check if there's an existing BaseService class to extend."
    )


# ── Runners ───────────────────────────────────────────────────────────────────

SYS_G1 = (
    "You are a code assistant helping a developer recall their previous work. "
    "Answer based ONLY on the context provided. If context is empty, state clearly "
    "that you have no information about previous session files."
)

SYS_G2 = (
    "You are a software engineer implementing features in an existing codebase. "
    "Based on any provided file context, state exactly which files to modify "
    "and which functions/classes to use. Be concrete with exact names."
)


def run_g1(client, scenarios: List[G1Scenario], dry_run: bool) -> List[EvalResult]:
    results = []
    for s in scenarios:
        for condition in ("with_ctx", "without_ctx"):
            if dry_run:
                resp = simulate_g1_with(s) if condition == "with_ctx" else simulate_g1_without(s)
            else:
                ctx = ctx_g1_with(s) if condition == "with_ctx" else ""
                user_msg = f"{ctx}\n\nQuestion: {s.question}" if ctx else f"Question: {s.question}"
                resp = call_llm(client, SYS_G1, user_msg)
                time.sleep(0.3)

            score, correct, hallucinated = score_g1(resp, s)
            results.append(EvalResult(
                scenario_id=s.scenario_id, goal="G1", condition=condition,
                response=resp[:300], score=score,
                correct_mentions=correct, hallucinated_mentions=hallucinated,
            ))
    return results


def run_g2(client, tasks: List[G2Task], dataset_name: str,
           dry_run: bool) -> List[EvalResult]:
    results = []
    for t in tasks:
        for condition in ("with_ctx", "without_ctx"):
            if dry_run:
                resp = simulate_g2_with(t) if condition == "with_ctx" else simulate_g2_without(t)
            else:
                ctx = ctx_g2_with(t, dataset_name) if condition == "with_ctx" else ""
                user_msg = (
                    f"{ctx}\n\nTask: {t.instruction}\n\n"
                    "Which file(s) to modify? Which functions/classes to use?"
                ) if ctx else (
                    f"Task: {t.instruction}\n\n"
                    "Which file(s) to modify? Which functions/classes to use?"
                )
                resp = call_llm(client, SYS_G2, user_msg)
                time.sleep(0.3)

            score, correct, hallucinated = score_g2(resp, t)
            results.append(EvalResult(
                scenario_id=t.task_id, goal="G2", condition=condition,
                response=resp[:300], score=score,
                correct_mentions=correct, hallucinated_mentions=hallucinated,
            ))
    return results


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate(results: List[EvalResult]) -> dict:
    buckets: Dict[str, Dict] = {}
    for r in results:
        key = f"{r.goal}_{r.condition}"
        if key not in buckets:
            buckets[key] = {"scores": [], "hallucinations": []}
        buckets[key]["scores"].append(r.score)
        buckets[key]["hallucinations"].append(len(r.hallucinated_mentions))

    summary = {}
    for key, vals in buckets.items():
        summary[key] = {
            "mean_score":          round(float(np.mean(vals["scores"])), 4),
            "std_score":           round(float(np.std(vals["scores"])), 4),
            "n":                   len(vals["scores"]),
            "mean_hallucinations": round(float(np.mean(vals["hallucinations"])), 3),
        }
    return summary


def print_report(summary: dict) -> None:
    sep = "=" * 65
    print(f"\n{sep}")
    print("  CTX DOWNSTREAM LLM EVALUATION")
    print(sep)

    for goal in ("G1", "G2"):
        w  = summary.get(f"{goal}_with_ctx", {})
        wo = summary.get(f"{goal}_without_ctx", {})
        if not w or not wo:
            continue
        delta = w["mean_score"] - wo["mean_score"]
        ratio = w["mean_score"] / max(wo["mean_score"], 1e-4)
        label = "Cross-Session Memory Recall" if goal == "G1" else "Instruction-Grounded Coding"
        print(f"\n  {goal}: {label}  (n={w['n']})")
        print(f"  {'─'*60}")
        print(f"  WITH CTX:    {w['mean_score']:.3f}  ± {w['std_score']:.3f}")
        print(f"  WITHOUT CTX: {wo['mean_score']:.3f}  ± {wo['std_score']:.3f}")
        print(f"  Delta:       {delta:+.3f}  (utility ratio: {ratio:.2f}x)")
        if goal == "G2":
            print(f"  Hallucination/response — WITH: {w['mean_hallucinations']:.2f}  "
                  f"WITHOUT: {wo['mean_hallucinations']:.2f}")

    # Overall
    g1w  = summary.get("G1_with_ctx",    {}).get("mean_score", 0.0)
    g1wo = summary.get("G1_without_ctx", {}).get("mean_score", 0.0)
    g2w  = summary.get("G2_with_ctx",    {}).get("mean_score", 0.0)
    g2wo = summary.get("G2_without_ctx", {}).get("mean_score", 0.0)
    ow   = (g1w  + g2w)  / 2
    owo  = (g1wo + g2wo) / 2
    delta_overall = ow - owo

    print(f"\n  {'─'*60}")
    print(f"  OVERALL WITH CTX:    {ow:.3f}")
    print(f"  OVERALL WITHOUT CTX: {owo:.3f}")
    print(f"  OVERALL DELTA:       {delta_overall:+.3f}")

    if delta_overall > 0.3:
        verdict = "CTX STRONGLY IMPROVES LLM QUALITY"
    elif delta_overall > 0.1:
        verdict = "CTX MODERATELY IMPROVES LLM QUALITY"
    elif delta_overall > 0.0:
        verdict = "CTX MARGINALLY IMPROVES LLM QUALITY"
    else:
        verdict = "CTX NO SIGNIFICANT IMPACT"
    print(f"\n  Verdict: {verdict}")
    print(sep)


def save_results(summary: dict, results: List[EvalResult]) -> Path:
    out_dir = ROOT / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"downstream_llm_eval_{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CTX downstream LLM evaluation")
    parser.add_argument("--dataset",     default="small")
    parser.add_argument("--n-scenarios", type=int, default=10)
    parser.add_argument("--dry-run",     action="store_true",
                        help="Use simulated responses (no API calls)")
    parser.add_argument("--model",       default="")
    args = parser.parse_args()

    # Auto-detect model from env if not specified
    if not args.model:
        if os.environ.get("MINIMAX_API_KEY"):
            args.model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
        else:
            args.model = "claude-haiku-4-5-20251001"

    client = get_llm_client()
    if client is None and not args.dry_run:
        print("[WARN] No API key found — switching to dry-run mode")
        args.dry_run = True
    elif client is not None:
        backend = "MiniMax" if os.environ.get("MINIMAX_API_KEY") else "Anthropic"
        print(f"Backend: {backend} | Model: {args.model}")

    data = load_dataset(args.dataset)
    files_meta = data["files"]
    print(f"Dataset: {args.dataset} ({len(files_meta)} files)")

    g1_scenarios = build_g1_scenarios(files_meta, n=args.n_scenarios)
    g2_tasks     = build_g2_tasks(files_meta, n=args.n_scenarios)
    print(f"Scenarios: G1={len(g1_scenarios)}, G2={len(g2_tasks)}")
    if args.dry_run:
        print("[DRY-RUN] Simulated LLM responses")

    print("\nRunning G1 (cross-session recall)...")
    g1_results = run_g1(client, g1_scenarios, dry_run=args.dry_run)

    print("Running G2 (instruction-grounded coding)...")
    g2_results = run_g2(client, g2_tasks, args.dataset, dry_run=args.dry_run)

    all_results = g1_results + g2_results
    summary = aggregate(all_results)
    print_report(summary)

    out_path = save_results(summary, all_results)
    print(f"\nResults saved: {out_path.name}")


if __name__ == "__main__":
    main()
