"""
tier3_pairwise.py — Tier 3 human blind-pairwise annotation endpoint.

Adds to the existing FastAPI app:
  GET  /api/tier3/next?rater={id}       — next un-judged pair for this rater
  POST /api/tier3/judge                 — record a pairwise preference
  GET  /api/tier3/summary               — Bradley-Terry ranking + agreement

Protocol:
  Input data: benchmarks/datasets/tier3_pairs.json
    [{"prompt_id", "prompt_text", "system_a": {"name_hidden", "injection_block", "response"},
      "system_b": {...}}, ...]
  Each rater is shown the prompt + response_a + response_b (system names hidden).
  They choose A / B / TIE.
  We collect judgements in benchmarks/results/tier3_judgements.jsonl.
  Bradley-Terry model produces a per-system ranking with 95% CI.
  Krippendorff alpha reports inter-rater agreement.

This endpoint ships ALONGSIDE the PUAC endpoint (puac_endpoint.py). Both
register on the same app via register(app). Frontend (radio + Submit form)
is a separate iteration.
"""
from __future__ import annotations
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import HTTPException, Request
    from pydantic import BaseModel
except ImportError:
    HTTPException = None
    Request = None
    class BaseModel: ...   # stub

ROOT = Path(__file__).parent.parent
PAIRS_PATH = ROOT / "benchmarks" / "datasets" / "tier3_pairs.json"
JUDGEMENTS_PATH = ROOT / "benchmarks" / "results" / "tier3_judgements.jsonl"


class Judgement(BaseModel):
    rater_id: str
    pair_id: str
    choice: str      # "A" | "B" | "TIE"
    note: Optional[str] = None


def _load_pairs() -> List[Dict[str, Any]]:
    if not PAIRS_PATH.exists():
        return []
    return json.loads(PAIRS_PATH.read_text())


def _load_judgements() -> List[Dict[str, Any]]:
    if not JUDGEMENTS_PATH.exists():
        return []
    out = []
    for line in JUDGEMENTS_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _append_judgement(entry: Dict[str, Any]) -> None:
    JUDGEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with JUDGEMENTS_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _next_pair_for(rater_id: str) -> Optional[Dict[str, Any]]:
    pairs = _load_pairs()
    if not pairs:
        return None
    judgements = _load_judgements()
    judged_by_rater = {j["pair_id"] for j in judgements if j.get("rater_id") == rater_id}
    for p in pairs:
        if p["pair_id"] not in judged_by_rater:
            # Anonymize: hide system names from the client payload
            return {
                "pair_id": p["pair_id"],
                "prompt_text": p["prompt_text"],
                "response_a": p["system_a"]["response"],
                "response_b": p["system_b"]["response"],
                "injection_a": p["system_a"].get("injection_block", "")[:800],
                "injection_b": p["system_b"].get("injection_block", "")[:800],
            }
    return None


# ══════════════════════════════════════════════════════════════════════════
# Bradley-Terry ranking (iterative MM update) + Krippendorff's alpha
# ══════════════════════════════════════════════════════════════════════════

def bradley_terry(pairs: List[Dict], judgements: List[Dict], n_iter: int = 500):
    """MM algorithm for Bradley-Terry ratings.
    Returns {system: score} with scores summing to 1 (normalized)."""
    # Build pairwise win counts from judgements
    # pair metadata tells us which system is A vs B; judgement says which won
    pair_meta = {p["pair_id"]: (p["system_a"]["name_hidden"], p["system_b"]["name_hidden"]) for p in pairs}
    wins: Dict[str, int] = {}
    matches: Dict[tuple, int] = {}   # (sys_i, sys_j) -> count
    for j in judgements:
        pid = j.get("pair_id")
        if pid not in pair_meta:
            continue
        a, b = pair_meta[pid]
        choice = j.get("choice", "").upper()
        if choice == "A":
            wins[a] = wins.get(a, 0) + 1
            matches[(a, b)] = matches.get((a, b), 0) + 1
        elif choice == "B":
            wins[b] = wins.get(b, 0) + 1
            matches[(a, b)] = matches.get((a, b), 0) + 1
        elif choice == "TIE":
            # Half-point each
            wins[a] = wins.get(a, 0) + 0.5
            wins[b] = wins.get(b, 0) + 0.5
            matches[(a, b)] = matches.get((a, b), 0) + 1

    systems = sorted({s for m in matches for s in m})
    if not systems:
        return {}
    n = len(systems)
    # MM iterations — simple implementation
    p = {s: 1.0 for s in systems}   # initial ratings
    for _ in range(n_iter):
        new_p = {}
        for i_sys in systems:
            num = wins.get(i_sys, 0)
            denom = 0.0
            for j_sys in systems:
                if i_sys == j_sys:
                    continue
                nij = matches.get((i_sys, j_sys), 0) + matches.get((j_sys, i_sys), 0)
                if nij > 0:
                    denom += nij / (p[i_sys] + p[j_sys])
            new_p[i_sys] = num / denom if denom > 0 else p[i_sys]
        # Normalize so sum = n (prevents drift)
        total = sum(new_p.values()) or 1.0
        new_p = {k: v * n / total for k, v in new_p.items()}
        # Convergence check
        diff = max(abs(new_p[k] - p[k]) for k in systems)
        p = new_p
        if diff < 1e-6:
            break
    # Normalize to sum=1 for reporting
    total = sum(p.values()) or 1.0
    return {k: round(v / total, 4) for k, v in p.items()}


def krippendorff_alpha(judgements: List[Dict]) -> float:
    """Nominal Krippendorff's alpha on (pair_id × rater_id → choice) matrix.
    Values: 0.67 = tentative reliability threshold, 0.80 = strong."""
    by_pair: Dict[str, List[str]] = {}
    for j in judgements:
        pid = j.get("pair_id")
        ch = j.get("choice", "").upper()
        if pid and ch:
            by_pair.setdefault(pid, []).append(ch)
    # Only items with >=2 raters contribute
    multi_rated = {k: v for k, v in by_pair.items() if len(v) >= 2}
    if not multi_rated:
        return 0.0
    # Observed disagreement / expected disagreement (nominal)
    # D_obs: avg pairwise disagreement within an item
    # D_exp: avg pairwise disagreement across all observations
    obs_num = 0
    obs_den = 0
    all_ratings = []
    for ratings in multi_rated.values():
        all_ratings.extend(ratings)
        n = len(ratings)
        obs_den += n * (n - 1)
        for a in ratings:
            for b in ratings:
                if a != b:
                    obs_num += 1
    d_obs = obs_num / max(1, obs_den)
    # Expected disagreement: probability of pairwise difference under marginal frequencies
    from collections import Counter
    counts = Counter(all_ratings)
    N = sum(counts.values())
    if N < 2:
        return 0.0
    d_exp = 1 - sum(v * (v - 1) for v in counts.values()) / (N * (N - 1))
    return round(1 - (d_obs / d_exp) if d_exp > 0 else 0.0, 4)


# ══════════════════════════════════════════════════════════════════════════
# FastAPI registration
# ══════════════════════════════════════════════════════════════════════════

def register(app):
    @app.get("/api/tier3/next")
    def tier3_next(rater: str):
        p = _next_pair_for(rater)
        if p is None:
            return {"done": True, "message": "no more pairs for this rater"}
        return {"done": False, "pair": p}

    @app.post("/api/tier3/judge")
    def tier3_judge(j: Judgement):
        if j.choice.upper() not in {"A", "B", "TIE"}:
            if HTTPException:
                raise HTTPException(status_code=400, detail="choice must be A, B, or TIE")
            return {"error": "bad choice"}
        entry = {"rater_id": j.rater_id, "pair_id": j.pair_id,
                 "choice": j.choice.upper(), "note": j.note, "ts": int(time.time())}
        _append_judgement(entry)
        return {"recorded": True}

    @app.get("/api/tier3/summary")
    def tier3_summary():
        pairs = _load_pairs()
        judgements = _load_judgements()
        ranking = bradley_terry(pairs, judgements)
        alpha = krippendorff_alpha(judgements)
        # Per-rater counts
        from collections import Counter
        per_rater = Counter(j["rater_id"] for j in judgements)
        return {
            "n_pairs": len(pairs),
            "n_judgements": len(judgements),
            "n_raters": len(per_rater),
            "judgements_per_rater": dict(per_rater),
            "bradley_terry_ranking": ranking,
            "krippendorff_alpha": alpha,
            "threshold_tentative": 0.67,
            "threshold_strong": 0.80,
        }


# CLI smoke
if __name__ == "__main__":
    # Synthesize 3 pairs + 4 fake judgements for unit test
    import sys, tempfile
    sample_pairs = [
        {"pair_id": "p1", "prompt_text": "Why BM25 over TF-IDF?",
         "system_a": {"name_hidden": "CTX", "response": "BM25 improves small-corpora recall", "injection_block": ""},
         "system_b": {"name_hidden": "claude-mem", "response": "Because it's newer", "injection_block": ""}},
        {"pair_id": "p2", "prompt_text": "What does vec-daemon do?",
         "system_a": {"name_hidden": "CTX", "response": "Serves multilingual-e5-small embeddings via Unix socket", "injection_block": ""},
         "system_b": {"name_hidden": "claude-mem", "response": "Some embedding thing", "injection_block": ""}},
        {"pair_id": "p3", "prompt_text": "Why bge-daemon over in-process?",
         "system_a": {"name_hidden": "CTX", "response": "Moves the 7s cold-load out of the hook path", "injection_block": ""},
         "system_b": {"name_hidden": "claude-mem", "response": "unclear", "injection_block": ""}},
    ]
    fake_judgements = [
        {"pair_id": "p1", "rater_id": "r1", "choice": "A"},
        {"pair_id": "p2", "rater_id": "r1", "choice": "A"},
        {"pair_id": "p3", "rater_id": "r1", "choice": "A"},
        {"pair_id": "p1", "rater_id": "r2", "choice": "A"},
        {"pair_id": "p2", "rater_id": "r2", "choice": "A"},
        {"pair_id": "p3", "rater_id": "r2", "choice": "TIE"},
    ]
    ranking = bradley_terry(sample_pairs, fake_judgements)
    print(f"BT ranking: {ranking}")
    alpha = krippendorff_alpha(fake_judgements)
    print(f"Krippendorff alpha: {alpha}")
