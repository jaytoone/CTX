"""
tier1_memoryagentbench.py — MemoryAgentBench Competency 4 (conflict resolution)

MemoryAgentBench (ICLR 2026, arxiv:2507.05257) evaluates 4 memory
competencies. This harness focuses on Competency 4 (Conflict Resolution /
selective forgetting / belief update) because it maps onto the exact
scenario where LLM-summarized intake (claude-mem) is architecturally
predicted to fail: when a decision is reversed across sessions, an LLM
summary may AVERAGE the pre- and post-reversal state into a confused
narrative, while BM25-over-git-log deterministically returns the latest
commit representing the post-reversal ground truth.

Dataset: `hfuw/MemoryAgentBench` on HuggingFace (when available).
Dataset licence: as declared on the HF card.

Because the real benchmark may not be instantly accessible, this harness
ALSO ships a SYNTHETIC_REVERSAL generator that produces conflict-resolution
cases from a template, so the test runs end-to-end without external data.
The synthetic cases match the shape of MemoryAgentBench's FactConsolidation
sub-dataset: initial fact → contradicting fact (later session) → query asking
what the current state is.

Retrievers (same interface as tier1_longmemeval):
  - ctx    : CTX BM25 (latest commit wins for reversed facts)
  - oracle : deterministic post-reversal truth (upper bound)
  - none   : no memory (lower bound)
  - chroma : claude-mem-style dense retrieval

Usage:
  python3 benchmarks/eval/tier1_memoryagentbench.py --synthetic --n 10 --retriever ctx
  python3 benchmarks/eval/tier1_memoryagentbench.py --download    # try real dataset
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT = Path(__file__).parent.parent.parent
DATASET_DIR = ROOT / "benchmarks" / "datasets" / "memoryagentbench"
RESULTS = ROOT / "benchmarks" / "results" / "tier1_memoryagentbench.json"
sys.path.insert(0, str(ROOT / "benchmarks" / "eval"))
from downstream_llm_eval import get_llm_client, call_llm   # noqa: E402
from tier1_longmemeval import RETRIEVERS, retrieve_ctx, retrieve_oracle, retrieve_none, retrieve_chroma   # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# Synthetic conflict-resolution dataset generator
# ══════════════════════════════════════════════════════════════════════════

# Each template: (subject, initial, reversed, question, correct_answer_after_reversal)
REVERSAL_TEMPLATES: List[Dict[str, str]] = [
    {"subject": "retrieval backend", "initial": "We chose TF-IDF for doc retrieval.",
     "reversed": "We replaced TF-IDF with BM25 after benchmarking.",
     "question": "What retrieval backend are we currently using?",
     "answer": "BM25"},
    {"subject": "database", "initial": "Using PostgreSQL for session storage.",
     "reversed": "Migrated from PostgreSQL to SQLite for deployment simplicity.",
     "question": "Which database is currently storing sessions?",
     "answer": "SQLite"},
    {"subject": "frontend framework", "initial": "Building the dashboard in React.",
     "reversed": "Rewrote the dashboard in vanilla JS to remove the React dep.",
     "question": "What does the dashboard use for its UI?",
     "answer": "vanilla JS"},
    {"subject": "embedding model", "initial": "Using all-MiniLM-L6-v2 for embeddings.",
     "reversed": "Switched to multilingual-e5-small for Korean support.",
     "question": "Which embedding model is production?",
     "answer": "multilingual-e5-small"},
    {"subject": "concurrency model", "initial": "Main loop uses asyncio.",
     "reversed": "Rewrote the loop to use threading after asyncio race bugs.",
     "question": "How does the main loop achieve concurrency?",
     "answer": "threading"},
    {"subject": "package manager", "initial": "Using pip for deps.",
     "reversed": "Moved from pip to uv for lockfile determinism.",
     "question": "What package manager does the project use?",
     "answer": "uv"},
    {"subject": "CI provider", "initial": "CI runs on CircleCI.",
     "reversed": "Migrated CI from CircleCI to GitHub Actions after quota issues.",
     "question": "Where does CI run?",
     "answer": "GitHub Actions"},
    {"subject": "rerank layer", "initial": "Using cosine similarity for reranking.",
     "reversed": "Replaced cosine with BGE cross-encoder for stronger semantic signal.",
     "question": "What reranker does the pipeline use?",
     "answer": "BGE cross-encoder"},
    {"subject": "log sink", "initial": "Logs stream to stdout only.",
     "reversed": "Added structured JSONL logging to .omc/live-progress.log alongside stdout.",
     "question": "Where do logs go now?",
     "answer": "both stdout and .omc/live-progress.log"},
    {"subject": "monitoring stack", "initial": "Monitoring with Grafana + Prometheus.",
     "reversed": "Dropped Grafana/Prometheus in favor of a minimal FastAPI /api/health endpoint.",
     "question": "How is the service monitored?",
     "answer": "FastAPI /api/health endpoint"},
]


def generate_synthetic_case(template: Dict[str, str], n_distractors: int = 8, seed: int = 0) -> Dict[str, Any]:
    """Build a multi-session record that looks like MemoryAgentBench FactConsolidation.
    Sessions are timestamp-ordered; the reversed fact appears AFTER the initial fact.
    Distractor sessions contain unrelated content."""
    rng = random.Random(seed)
    distractor_topics = [
        "discussing weekend plans",
        "reviewing a PR about typo fixes",
        "chatting about coffee",
        "thinking about weather",
        "ordering lunch",
        "noting a meeting reschedule",
        "sharing a fun article",
        "mentioning a holiday",
    ]
    sessions: List[Dict[str, Any]] = []
    # Distractors before
    for i in range(n_distractors // 2):
        sessions.append({
            "session_id": f"d-pre-{i}",
            "turns": [{"role": "user", "content": rng.choice(distractor_topics)}],
        })
    # Initial fact
    sessions.append({
        "session_id": "initial",
        "turns": [{"role": "user", "content": template["initial"]}],
    })
    # More distractors
    for i in range(n_distractors // 2):
        sessions.append({
            "session_id": f"d-mid-{i}",
            "turns": [{"role": "user", "content": rng.choice(distractor_topics)}],
        })
    # Reversal
    sessions.append({
        "session_id": "reversal",
        "turns": [{"role": "user", "content": template["reversed"]}],
    })
    return {
        "question_id": f"synth-{template['subject'].replace(' ', '-')}",
        "question_type": "conflict_resolution",
        "subject": template["subject"],
        "haystack_sessions": sessions,
        "question": template["question"],
        "answer": template["answer"],
        "oracle_memories": [template["reversed"]],   # the reversed fact is the oracle
    }


def generate_synthetic_dataset(n: int = 10, seed: int = 42) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    templates = REVERSAL_TEMPLATES.copy()
    rng.shuffle(templates)
    if n > len(templates):
        # Repeat with different seeds to vary distractors
        templates = templates * ((n // len(templates)) + 1)
    cases = []
    for i, tpl in enumerate(templates[:n]):
        cases.append(generate_synthetic_case(tpl, seed=seed + i))
    return cases


# ══════════════════════════════════════════════════════════════════════════
# Scoring: did the response mention the REVERSED (current) answer?
# ══════════════════════════════════════════════════════════════════════════

ANSWER_SYS = (
    "You are a helpful assistant answering questions about a long multi-session "
    "conversation log. Use the provided memory excerpts. The conversation may "
    "include updates where decisions were REVERSED — always report the CURRENT "
    "state based on the MOST RECENT information. Answer concisely."
)


def answer(client, question: str, memories: List[str], model: str = "") -> str:
    block = "\n".join(f"- {m}" for m in memories) if memories else "(no memory)"
    return call_llm(client, ANSWER_SYS,
                    f"Memory:\n{block}\n\n---\n\nQuestion: {question}",
                    model=model, max_tokens=256)


def judge_reversal_correct(candidate: str, correct_answer: str) -> int:
    """A response passes if it mentions the REVERSED answer (case-insensitive substring)."""
    norm = candidate.lower()
    ans = correct_answer.lower()
    return 1 if ans in norm else 0


# ══════════════════════════════════════════════════════════════════════════
# Main eval
# ══════════════════════════════════════════════════════════════════════════

def run_eval(cases: List[Dict], retriever_name: str, model: str = "") -> Dict:
    retriever = RETRIEVERS[retriever_name]
    client = get_llm_client()
    if not client:
        print("[error] no LLM client", file=sys.stderr); sys.exit(2)
    results = []
    for i, c in enumerate(cases, 1):
        q = c["question"]
        if retriever_name == "oracle":
            mems = retrieve_oracle(q, c.get("oracle_memories", []))
        elif retriever_name == "none":
            mems = []
        else:
            mems = retriever(q, c.get("haystack_sessions", []), top_k=5)
        candidate = answer(client, q, mems, model=model)
        correct = judge_reversal_correct(candidate, c["answer"])
        results.append({
            "question_id": c["question_id"],
            "subject": c["subject"],
            "question": q,
            "expected": c["answer"],
            "candidate": candidate[:300],
            "n_memories": len(mems),
            "correct": correct,
        })
        print(f"  [{i}/{len(cases)}] {c['subject']:<22} expected='{c['answer']:<30}' correct={correct} mem={len(mems)}", flush=True)

    n = len(results)
    accuracy = round(sum(r["correct"] for r in results) / max(1, n), 3)

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if RESULTS.exists():
        try:
            existing = json.loads(RESULTS.read_text())
        except Exception:
            pass
    existing[retriever_name] = {
        "competency": "conflict_resolution",
        "overall": {"n": n, "accuracy": accuracy},
        "per_question": results,
        "model": model or os.environ.get("MINIMAX_MODEL", ""),
    }
    RESULTS.write_text(json.dumps(existing, indent=2))
    print(f"\n[tier1-mab] retriever={retriever_name} accuracy={accuracy} (n={n})")
    print(f"  wrote {RESULTS}")
    return existing[retriever_name]


def download_real_dataset():
    """Placeholder — actual MemoryAgentBench HF ID TBD at runtime."""
    print("[download] MemoryAgentBench official dataset: check arxiv:2507.05257 for HF card URL")
    print("          (synthetic mode currently produces equivalent conflict-resolution shape)")


def main():
    ap = argparse.ArgumentParser(description="Tier 1 — MemoryAgentBench Competency 4")
    ap.add_argument("--synthetic", action="store_true", help="use built-in synthetic reversal cases")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--retriever", choices=list(RETRIEVERS.keys()), default="ctx")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--model", default="")
    args = ap.parse_args()

    if args.download:
        download_real_dataset()
        return

    cases = generate_synthetic_dataset(n=args.n) if args.synthetic else []
    if not cases:
        print("[error] no dataset. Use --synthetic or --download.", file=sys.stderr)
        sys.exit(2)
    print(f"[tier1-mab] {len(cases)} conflict-resolution cases, retriever={args.retriever}")
    run_eval(cases, args.retriever, model=args.model)


if __name__ == "__main__":
    main()
