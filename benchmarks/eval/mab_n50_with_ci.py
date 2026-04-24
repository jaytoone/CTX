"""Run MAB N=50 × 4 retrievers, compute Wilson 95% CI, save comparison."""
import json, sys, math
from pathlib import Path
sys.path.insert(0, "/home/jayone/Project/CTX/benchmarks/eval")
import tier1_memoryagentbench as t
from downstream_llm_eval import get_llm_client

ROOT = Path("/home/jayone/Project/CTX")
DATASET = ROOT / "benchmarks/datasets/mab_n50.json"
OUT = ROOT / "benchmarks/results/mab_n50_with_ci.json"


def wilson_ci(successes, n, z=1.96):
    """Wilson score interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    half = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n) / denom
    return (max(0, center - half), min(1, center + half))


def run_one(retriever_name, cases, client, model=""):
    from tier1_memoryagentbench import answer, judge_reversal_correct
    from tier1_longmemeval import RETRIEVERS, retrieve_oracle
    retriever = RETRIEVERS[retriever_name]
    correct = 0
    per_case = []
    for i, c in enumerate(cases, 1):
        q = c["question"]
        if retriever_name == "oracle":
            mems = retrieve_oracle(q, c.get("oracle_memories", []))
        elif retriever_name == "none":
            mems = []
        else:
            mems = retriever(q, c.get("haystack_sessions", []), top_k=5)
        candidate = answer(client, q, mems, model=model)
        is_correct = judge_reversal_correct(candidate, c["answer"], client=client, model=model)
        correct += is_correct
        per_case.append({"id": c["question_id"], "correct": is_correct,
                         "n_memories": len(mems)})
        if i % 5 == 0:
            print(f"    [{retriever_name}] {i}/{len(cases)}  running accuracy={correct/i:.3f}", flush=True)
    return correct, per_case


def main():
    cases = json.loads(DATASET.read_text())
    print(f"[N=50] loaded {len(cases)} cases from {DATASET}")
    client = get_llm_client()

    results = {}
    for retr in ["none", "ctx", "ctx_v2", "chroma", "oracle"]:
        print(f"\n=== retriever: {retr} ===")
        correct, per_case = run_one(retr, cases, client)
        ci_lo, ci_hi = wilson_ci(correct, len(cases))
        results[retr] = {
            "n": len(cases),
            "correct": correct,
            "accuracy": correct / len(cases),
            "wilson_ci_95": [round(ci_lo, 3), round(ci_hi, 3)],
            "ci_halfwidth": round((ci_hi - ci_lo) / 2, 3),
            "per_case": per_case,
        }
        print(f"  → accuracy={correct}/{len(cases)} = {correct/len(cases):.3f}")
        print(f"  → Wilson 95% CI: [{ci_lo:.3f}, {ci_hi:.3f}]  (halfwidth={(ci_hi-ci_lo)/2:.3f})")

    OUT.write_text(json.dumps(results, indent=2))
    print(f"\n[wrote] {OUT}")
    return results


if __name__ == "__main__":
    import os
    main()
