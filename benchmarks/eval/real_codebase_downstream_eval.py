"""
real_codebase_downstream_eval.py — CTX G2 Downstream Eval on Real CTX Codebase

Runs G2 (instruction-grounded coding) evaluation using:
- Real CTX codebase files as context
- MiniMax M2.5 (or Anthropic) as LLM
- 5 instruction-based scenarios mapped to actual CTX source files

Measures: WITH CTX context vs WITHOUT CTX context
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ── LLM client (same as downstream_llm_eval.py) ───────────────────────────────

def get_llm_client():
    try:
        import anthropic
        minimax_key = os.environ.get("MINIMAX_API_KEY", "")
        minimax_url = os.environ.get("MINIMAX_BASE_URL", "")
        if minimax_key and minimax_url:
            return anthropic.Anthropic(api_key=minimax_key, base_url=minimax_url)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return anthropic.Anthropic(api_key=key)
        return None
    except ImportError:
        return None


def call_llm(client, system: str, user: str, model: str = "", max_tokens: int = 512) -> str:
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
        for block in resp.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                return block.text.strip()
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[NO-TEXT-BLOCK]"
    except Exception as exc:
        return f"[LLM-ERROR] {exc}"


# ── Real CTX codebase scenarios ───────────────────────────────────────────────

@dataclass
class RealG2Scenario:
    scenario_id: str
    instruction: str
    target_file: str          # ground truth file to modify
    target_functions: List[str]  # ground truth functions
    ctx_context_file: str     # file to show as context (WITH CTX)


SCENARIOS = [
    RealG2Scenario(
        scenario_id="real_g2_01",
        instruction="Replace TF-IDF scoring with BM25 in the adaptive retriever",
        target_file="src/retrieval/adaptive_trigger.py",
        target_functions=["rank_bm25", "_rank_files", "AdaptiveTriggerRetriever"],
        ctx_context_file="src/retrieval/adaptive_trigger.py",
    ),
    RealG2Scenario(
        scenario_id="real_g2_02",
        instruction="Add query_type-aware routing so keyword queries bypass heading match",
        target_file="src/retrieval/adaptive_trigger.py",
        target_functions=["rank_ctx_doc", "query_type", "_route_keyword"],
        ctx_context_file="src/retrieval/adaptive_trigger.py",
    ),
    RealG2Scenario(
        scenario_id="real_g2_03",
        instruction="Add R@5 recall metric to the document retrieval evaluation script",
        target_file="benchmarks/eval/doc_retrieval_eval_v2.py",
        target_functions=["evaluate_strategy", "recall_at_k", "main"],
        ctx_context_file="benchmarks/eval/doc_retrieval_eval_v2.py",
    ),
    RealG2Scenario(
        scenario_id="real_g2_04",
        instruction="Implement a hybrid retriever that combines dense embeddings with CTX adaptive trigger",
        target_file="src/retrieval/hybrid_dense_ctx.py",
        target_functions=["HybridDenseCTX", "retrieve", "_merge_results"],
        ctx_context_file="src/retrieval/hybrid_dense_ctx.py",
    ),
    RealG2Scenario(
        scenario_id="real_g2_05",
        instruction="Fix the BM25Okapi IDF penalty issue on small domain corpus — switch to TF-only scoring",
        target_file="src/retrieval/bm25_retriever.py",
        target_functions=["BM25Retriever", "rank", "get_scores"],
        ctx_context_file="src/retrieval/bm25_retriever.py",
    ),
]


def load_file_snippet(filepath: str, max_lines: int = 60) -> str:
    """Load first max_lines of a source file as context."""
    full_path = ROOT / filepath
    if not full_path.exists():
        return f"[FILE NOT FOUND: {filepath}]"
    lines = full_path.read_text(encoding="utf-8").splitlines()
    snippet = "\n".join(lines[:max_lines])
    return f"# File: {filepath}\n```python\n{snippet}\n```"


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_response(response: str, scenario: RealG2Scenario):
    """Score LLM response for file/function mentions."""
    resp_lower = response.lower()
    target_file_stem = Path(scenario.target_file).stem.lower()

    correct = []
    hallucinated = []

    # Check if target file is mentioned
    if target_file_stem in resp_lower or scenario.target_file.lower() in resp_lower:
        correct.append(scenario.target_file)

    # Check function mentions
    for fn in scenario.target_functions:
        if fn.lower() in resp_lower:
            correct.append(fn)

    # Hallucination: non-existent .py files
    import re
    mentioned_py = re.findall(r'\b(\w+)\.py\b', response)
    real_stems = {Path(s).stem for s in [
        "adaptive_trigger.py", "bm25_retriever.py", "doc_retrieval_eval_v2.py",
        "hybrid_dense_ctx.py", "downstream_llm_eval.py", "dense_retriever.py",
        "llamaindex_retriever.py", "full_context.py", "graph_rag.py",
        "ranger_approx.py", "chroma_retriever.py", "ablation_variants.py",
    ]}
    for stem in mentioned_py:
        if stem.lower() not in real_stems:
            hallucinated.append(stem + ".py")

    total_expected = 1 + len(scenario.target_functions)  # file + functions
    score = len(correct) / total_expected if total_expected > 0 else 0.0
    return min(score, 1.0), correct, hallucinated


# ── Runner ────────────────────────────────────────────────────────────────────

SYS_G2 = (
    "You are a software engineer implementing features in a real Python codebase. "
    "Based on the provided file context, state EXACTLY which file to modify "
    "and which specific functions/classes to change or create. Use exact names."
)


@dataclass
class RealEvalResult:
    scenario_id: str
    condition: str
    instruction: str
    response: str
    score: float
    correct_mentions: List[str]
    hallucinated_mentions: List[str]
    target_file: str


def run_scenarios(client) -> List[RealEvalResult]:
    results = []
    for s in SCENARIOS:
        for condition in ("with_ctx", "without_ctx"):
            if condition == "with_ctx":
                ctx = load_file_snippet(s.ctx_context_file)
                user_msg = (
                    f"Here is the relevant file from the codebase:\n\n{ctx}\n\n"
                    f"Task: {s.instruction}\n\n"
                    "Which file to modify? Which functions/classes to use or create? Be specific."
                )
            else:
                user_msg = (
                    f"Task: {s.instruction}\n\n"
                    "Which file to modify? Which functions/classes to use or create? Be specific."
                )

            print(f"  {s.scenario_id} [{condition}]...", end=" ", flush=True)
            resp = call_llm(client, SYS_G2, user_msg)
            time.sleep(0.5)

            if resp.startswith("[LLM-ERROR]") or resp == "[NO-CLIENT]":
                print(f"ERROR: {resp[:60]}")
            else:
                print("OK")

            score, correct, hallucinated = score_response(resp, s)
            results.append(RealEvalResult(
                scenario_id=s.scenario_id,
                condition=condition,
                instruction=s.instruction,
                response=resp[:400],
                score=score,
                correct_mentions=correct,
                hallucinated_mentions=hallucinated,
                target_file=s.target_file,
            ))
    return results


def aggregate(results: List[RealEvalResult]) -> dict:
    buckets = {"with_ctx": [], "without_ctx": []}
    hallu = {"with_ctx": [], "without_ctx": []}
    for r in results:
        buckets[r.condition].append(r.score)
        hallu[r.condition].append(len(r.hallucinated_mentions))
    return {
        "with_ctx": {
            "mean_score": round(sum(buckets["with_ctx"]) / len(buckets["with_ctx"]), 4),
            "n": len(buckets["with_ctx"]),
            "mean_hallu": round(sum(hallu["with_ctx"]) / len(hallu["with_ctx"]), 3),
        },
        "without_ctx": {
            "mean_score": round(sum(buckets["without_ctx"]) / len(buckets["without_ctx"]), 4),
            "n": len(buckets["without_ctx"]),
            "mean_hallu": round(sum(hallu["without_ctx"]) / len(hallu["without_ctx"]), 3),
        },
    }


def main():
    client = get_llm_client()
    backend = "MiniMax" if os.environ.get("MINIMAX_API_KEY") else "Anthropic"
    model = os.environ.get("MINIMAX_MODEL") or "claude-haiku-4-5-20251001"

    if client is None:
        print("[ERROR] No LLM client available. Set MINIMAX_API_KEY or ANTHROPIC_API_KEY.")
        sys.exit(1)

    print(f"Backend: {backend} | Model: {model}")
    print(f"Scenarios: {len(SCENARIOS)} real CTX codebase tasks")
    print()

    results = run_scenarios(client)
    summary = aggregate(results)

    w = summary["with_ctx"]
    wo = summary["without_ctx"]
    delta = w["mean_score"] - wo["mean_score"]

    print()
    print("=" * 60)
    print("  REAL CODEBASE G2 DOWNSTREAM EVAL — CTX CODEBASE")
    print("=" * 60)
    print(f"  WITH CTX:    {w['mean_score']:.3f}  (n={w['n']}, hallu={w['mean_hallu']:.2f})")
    print(f"  WITHOUT CTX: {wo['mean_score']:.3f}  (n={wo['n']}, hallu={wo['mean_hallu']:.2f})")
    print(f"  Delta:       {delta:+.3f}")
    print()

    # Per-scenario breakdown
    print("  Per-scenario:")
    for r in results:
        if r.condition == "with_ctx":
            r2 = next((x for x in results if x.scenario_id == r.scenario_id and x.condition == "without_ctx"), None)
            d = r.score - (r2.score if r2 else 0)
            wo_score = f"{r2.score:.3f}" if r2 else "N/A"
            print(f"    {r.scenario_id}: WITH={r.score:.3f}  WITHOUT={wo_score}  Δ={d:+.3f}  hallu={len(r.hallucinated_mentions)}")
    print("=" * 60)

    # Save
    out_dir = ROOT / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"real_codebase_downstream_{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "backend": backend,
        "model": model,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out_path.name}")
    return summary


if __name__ == "__main__":
    main()
