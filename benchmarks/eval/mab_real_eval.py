"""
mab_real_eval.py — CTX evaluation on real MemoryAgentBench (ai-hyz/MemoryAgentBench).

Tests all 4 competencies:
  1. Accurate_Retrieval     — direct fact lookup
  2. Test_Time_Learning     — update beliefs from new info
  3. Long_Range_Understanding — reason across distant sessions
  4. Conflict_Resolution    — selective forgetting / fact consolidation (multi-hop)

Adapter design:
  - Each numbered fact in the context → one "session" entry
  - CTX retrievers (BM25, dense) retrieve relevant sessions for each question
  - LLM answers using retrieved context
  - Ground-truth answer matching via substring / exact match

Usage:
  export MINIMAX_API_KEY=...
  export MINIMAX_BASE_URL=...
  export MINIMAX_MODEL=MiniMax-M2.5
  python3 benchmarks/eval/mab_real_eval.py [--n_per_competency 25]
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import sys
import random
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from downstream_llm_eval import get_llm_client, call_llm

# ── Constants ──────────────────────────────────────────────────────
COMPETENCIES = [
    "Accurate_Retrieval",
    "Test_Time_Learning",
    "Long_Range_Understanding",
    "Conflict_Resolution",
]
ROOT = Path(__file__).parent.parent.parent
OUT_PATH = ROOT / "benchmarks/results/mab_real_eval.json"

# ── Data loading ───────────────────────────────────────────────────

def load_competency(name: str, max_samples_per_context: int = 10, seed: int = 42) -> List[Dict]:
    """Load up to max_samples_per_context Q/A pairs from each context entry."""
    from datasets import load_dataset
    rng = random.Random(seed)
    ds = load_dataset("ai-hyz/MemoryAgentBench", split=name, revision="main")
    cases = []
    for entry in ds:
        ctx = entry["context"]
        qs = entry["questions"]
        ans = entry["answers"]
        src = entry.get("metadata", {}).get("source", name)
        facts = _parse_facts(ctx)
        # Pair questions with answers, sample if needed
        pairs = list(zip(qs, ans))
        if len(pairs) > max_samples_per_context:
            pairs = rng.sample(pairs, max_samples_per_context)
        for q, a in pairs:
            cases.append({
                "competency": name,
                "source": src,
                "facts": facts,          # list of str
                "question": q,
                "answers": a if isinstance(a, list) else [a],
            })
    return cases


def _parse_facts(context: str) -> List[str]:
    """Extract numbered facts from 'Here is a list of facts: 0. ... 1. ...' format."""
    # Match lines like "0. Some fact text."
    facts = re.findall(r'^\d+\.\s+(.+?)$', context, re.MULTILINE)
    if facts:
        return facts
    # Fallback: split by sentence
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', context) if len(s.strip()) > 20]
    return sentences[:200]


# ── Retrieval adapters ─────────────────────────────────────────────

def facts_to_haystack(facts: List[str]) -> List[Dict]:
    """Convert list of fact strings to CTX haystack_sessions format."""
    return [
        {"turns": [{"role": "assistant", "content": fact}]}
        for fact in facts
    ]


def retrieve_none(question: str, facts: List[str], top_k: int = 7) -> List[str]:
    return []


def retrieve_bm25(question: str, facts: List[str], top_k: int = 7) -> List[str]:
    """BM25 over individual facts (CTX-style)."""
    try:
        from retrieve_ctx_v2 import retrieve_ctx_v2
        haystack = facts_to_haystack(facts)
        results = retrieve_ctx_v2(question, haystack, top_k=top_k)
        return results
    except Exception as e:
        # Fallback: rank_bm25 directly
        try:
            from rank_bm25 import BM25Okapi
            import re as _re
            def tok(t):
                return _re.findall(r'[a-z]{2,}', t.lower())
            corpus = [tok(f) for f in facts]
            bm25 = BM25Okapi(corpus)
            scores = bm25.get_scores(tok(question))
            ranked = sorted(range(len(facts)), key=lambda i: scores[i], reverse=True)
            return [facts[i] for i in ranked[:top_k] if scores[i] > 0]
        except Exception:
            return []


def retrieve_dense(question: str, facts: List[str], top_k: int = 7) -> List[str]:
    """Dense embedding retrieval via Chroma (all-MiniLM-L6-v2)."""
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.Client()
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        coll_name = "mab_real_tmp"
        try:
            client.delete_collection(coll_name)
        except Exception:
            pass
        coll = client.create_collection(coll_name, embedding_function=ef)
        coll.add(
            documents=facts,
            ids=[f"f{i}" for i in range(len(facts))],
        )
        results = coll.query(query_texts=[question], n_results=min(top_k, len(facts)))
        return results["documents"][0] if results["documents"] else []
    except Exception as e:
        return []


RETRIEVERS = {
    "none": retrieve_none,
    "bm25": retrieve_bm25,
    "dense": retrieve_dense,
}

# ── Evaluation ─────────────────────────────────────────────────────

ANSWER_PROMPT = """You are answering a question based on retrieved memory facts.

Retrieved facts:
{facts_str}

Question: {question}

Answer with ONLY the answer text (no explanation). If multiple facts conflict, use the most specific/recent one."""

NO_CONTEXT_PROMPT = """You are answering a factual question.

Question: {question}

Answer with ONLY the answer text (no explanation)."""


def answer_question(client, question: str, retrieved: List[str], model: str = "") -> str:
    if not model:
        model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    if retrieved:
        facts_str = "\n".join(f"- {f}" for f in retrieved[:10])
        prompt = ANSWER_PROMPT.format(facts_str=facts_str, question=question)
    else:
        prompt = NO_CONTEXT_PROMPT.format(question=question)
    # max_tokens=1024: MiniMax M2.5 uses extended thinking which consumes tokens
    # before text output; 64 was too small and returned [NO-TEXT-BLOCK]
    return call_llm(client, "You are a factual QA assistant.", prompt, model=model, max_tokens=1024)


def is_correct(prediction: str, gold_answers: List[str]) -> bool:
    """Check if prediction matches any gold answer (case-insensitive substring)."""
    pred_lower = prediction.lower().strip()
    for ans in gold_answers:
        ans_lower = ans.lower().strip()
        if ans_lower in pred_lower or pred_lower in ans_lower:
            return True
        # Also try exact word-boundary match
        if re.search(r'\b' + re.escape(ans_lower) + r'\b', pred_lower):
            return True
    return False


def wilson_ci(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, center - half), min(1.0, center + half))


# ── Main ────────────────────────────────────────────────────────────

def run_competency(name: str, cases: List[Dict], client, retrievers: List[str],
                   model: str = "") -> Dict:
    print(f"\n{'='*60}")
    print(f"  Competency: {name}  (N={len(cases)})")
    print(f"{'='*60}")
    results = {r: {"correct": 0, "total": len(cases), "per_case": []} for r in retrievers}
    for i, case in enumerate(cases, 1):
        q = case["question"]
        gold = case["answers"]
        facts = case["facts"]
        for retr_name in retrievers:
            retrieved = RETRIEVERS[retr_name](q, facts, top_k=7)
            pred = answer_question(client, q, retrieved, model=model)
            ok = is_correct(pred, gold)
            results[retr_name]["correct"] += ok
            results[retr_name]["per_case"].append({
                "q": q[:80], "gold": gold[0], "pred": pred[:80],
                "correct": ok, "n_retrieved": len(retrieved),
            })
        if i % 5 == 0 or i == len(cases):
            for r in retrievers:
                acc = results[r]["correct"] / i
                print(f"  [{r}] {i}/{len(cases)}  acc={acc:.3f}")
    # Add Wilson CI
    for r in retrievers:
        n = results[r]["total"]
        c = results[r]["correct"]
        ci = wilson_ci(c, n)
        results[r]["accuracy"] = c / n if n > 0 else 0.0
        results[r]["wilson_ci_95"] = [round(ci[0], 3), round(ci[1], 3)]
        print(f"  {r:<12}: {c}/{n} = {c/n:.3f}  CI [{ci[0]:.3f}, {ci[1]:.3f}]")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_per_competency", type=int, default=25,
                    help="Max Q/A pairs per competency (default: 25)")
    ap.add_argument("--max_per_context", type=int, default=8,
                    help="Max Q/A pairs per context entry (default: 8)")
    ap.add_argument("--retrievers", nargs="+", default=["none", "bm25", "dense"],
                    help="Retrievers to evaluate")
    ap.add_argument("--competencies", nargs="+", default=COMPETENCIES)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    client = get_llm_client()
    if client is None:
        print("[ERROR] No LLM client available. Set MINIMAX_API_KEY + MINIMAX_BASE_URL.")
        sys.exit(1)
    print(f"LLM: {model}")
    print(f"Retrievers: {args.retrievers}")
    print(f"N per competency: {args.n_per_competency}")

    all_results = {}
    for comp in args.competencies:
        try:
            cases = load_competency(comp, max_samples_per_context=args.max_per_context,
                                    seed=args.seed)
            # Cap total per competency
            rng = random.Random(args.seed)
            if len(cases) > args.n_per_competency:
                cases = rng.sample(cases, args.n_per_competency)
            comp_results = run_competency(comp, cases, client, args.retrievers, model=model)
            all_results[comp] = comp_results
        except Exception as e:
            print(f"[SKIP] {comp}: {e}")
            all_results[comp] = {"error": str(e)}

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY — All 4 MAB Competencies")
    print(f"{'='*60}")
    for comp, res in all_results.items():
        if "error" in res:
            print(f"  {comp}: ERROR — {res['error']}")
            continue
        print(f"\n  {comp}:")
        for r, v in res.items():
            if isinstance(v, dict) and "accuracy" in v:
                ci = v.get("wilson_ci_95", [0, 0])
                print(f"    {r:<12}: {v['correct']}/{v['total']} = {v['accuracy']:.3f}  "
                      f"CI [{ci[0]:.3f}, {ci[1]:.3f}]")

    OUT_PATH.write_text(json.dumps({"model": model, "results": all_results}, indent=2))
    print(f"\n[wrote] {OUT_PATH}")


if __name__ == "__main__":
    main()
