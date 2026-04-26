"""
mcnemar_bonferroni.py — Proper pairwise McNemar tests with Bonferroni correction
on MAB N=50 results.

Addresses the critical evaluation finding that:
  - 4 simultaneous McNemar tests were run without multiple comparison correction
  - Bonferroni threshold = 0.05 / 4 = 0.0125
  - p=0.049 (ctx_v2 vs ctx) does NOT survive Bonferroni
"""
import json, math, itertools
from pathlib import Path


def exact_mcnemar(b: int, c: int) -> float:
    """Exact McNemar test p-value (mid-p corrected).

    b = cases where A is correct but B is not (A wins)
    c = cases where B is correct but A is not (B wins)
    Returns 2-sided p-value.
    """
    n = b + c
    if n == 0:
        return 1.0
    # Exact binomial two-sided p-value (mid-p form)
    # Under H0: b ~ Binomial(n, 0.5)
    k = min(b, c)
    # P(X <= k) under Binomial(n, 0.5)
    from math import comb, log
    # Use exact computation for small n; log-space for larger
    total = 2 ** n
    p_le_k = sum(comb(n, i) for i in range(k + 1)) / total
    # Mid-p: subtract half of the point probability at k
    p_at_k = comb(n, k) / total
    p_two_sided = 2 * (p_le_k - 0.5 * p_at_k)
    return min(1.0, p_two_sided)


def wilson_ci(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0, center - half), min(1, center + half))


def load_results(path: Path) -> dict:
    data = json.loads(path.read_text())
    # Normalize: per_case is a list of {id, correct, n_memories}
    return data


def analyze(results_path: Path):
    data = load_results(results_path)
    retrievers = [r for r in data if r != "meta"]

    print("=" * 70)
    print("MAB Evaluation Results — Wilson 95% CI")
    print("=" * 70)
    per_case_by_retr = {}
    for retr in retrievers:
        r = data[retr]
        n = r["n"]
        correct = r["correct"]
        acc = r["accuracy"]
        ci = r.get("wilson_ci_95", wilson_ci(correct, n))
        ci_hw = (ci[1] - ci[0]) / 2
        per_case_by_retr[retr] = {c["id"]: c["correct"] for c in r.get("per_case", [])}
        print(f"  {retr:<22}: {correct:>3}/{n} = {acc:.3f}  "
              f"Wilson95% [{ci[0]:.3f}, {ci[1]:.3f}]  (±{ci_hw:.3f})")

    print()
    print("=" * 70)
    print("Pairwise McNemar Tests — Bonferroni corrected")
    print("=" * 70)

    # Identify pairs to test
    retr_list = [r for r in retrievers if r not in ("none", "oracle")]
    pairs = list(itertools.combinations(retr_list, 2))
    n_tests = len(pairs)
    bonferroni_threshold = 0.05 / n_tests

    print(f"  n_tests = {n_tests}  →  Bonferroni threshold α = 0.05 / {n_tests} = {bonferroni_threshold:.4f}")
    print()
    print(f"  {'Pair':<35} {'b':>4} {'c':>4} {'p-value':>10} {'Bonf-SIG?':>12}")
    print("  " + "-" * 68)

    sig_pairs = []
    for (a, b) in pairs:
        ids_a = per_case_by_retr.get(a, {})
        ids_b = per_case_by_retr.get(b, {})
        common_ids = set(ids_a.keys()) & set(ids_b.keys())
        if not common_ids:
            print(f"  {a} vs {b}: no common cases")
            continue
        # b = a correct, b wrong; c = b correct, a wrong
        b_wins = sum(1 for i in common_ids if ids_a[i] and not ids_b[i])
        c_wins = sum(1 for i in common_ids if ids_b[i] and not ids_a[i])
        pval = exact_mcnemar(b_wins, c_wins)
        sig = "SIG ***" if pval < bonferroni_threshold else (
              "marginal" if pval < 0.05 else "NS")
        direction = f"{a}>{b}" if b_wins > c_wins else (
                    f"{b}>{a}" if c_wins > b_wins else "tie")
        pair_label = f"{a} vs {b}"
        print(f"  {pair_label:<35} {b_wins:>4} {c_wins:>4} {pval:>10.4f} {sig:>12}  ({direction})")
        if pval < bonferroni_threshold:
            sig_pairs.append((a, b, pval, direction))

    print()
    print("=" * 70)
    print("Verdict")
    print("=" * 70)
    if sig_pairs:
        for (a, b, pval, dir) in sig_pairs:
            print(f"  CONFIRMED: {dir}  (p={pval:.4f} < {bonferroni_threshold:.4f})")
    else:
        print("  No pairs survive Bonferroni correction.")
        print("  The MAB N=50 data does NOT support any statistically significant")
        print("  pairwise superiority claims after proper multiple comparison correction.")
    print()
    print("Interpretation:")
    print("  Claims like 'BEATS X' require Bonferroni-corrected significance.")
    print("  'Directionally better' (p<0.05 uncorrected) is NOT a valid claim.")
    print(f"  To make a valid claim at N=50, need p < {bonferroni_threshold:.4f}.")
    print("  Recommended: expand to N=200 to achieve 15.6pp → 7.8pp CI halfwidth.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = Path("/home/jayone/Project/CTX/benchmarks/results/mab_n50_with_ci.json")
    if not path.exists():
        print(f"[waiting] {path} not found yet — run mab_n50_with_ci.py first")
        sys.exit(1)
    analyze(path)
