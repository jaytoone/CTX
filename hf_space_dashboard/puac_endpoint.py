"""
puac_endpoint.py — Dashboard extension exposing PUAC results.

Registers /api/puac-compare on the existing FastAPI app. Reads
benchmarks/results/puac_eval.json and serves per-prompt comparison:

  GET /api/puac-compare           -> summary + list of all prompts
  GET /api/puac-compare/{pid}     -> side-by-side FULL vs EMPTY for one prompt

Usage: import this module from hf_space_dashboard/app.py and call
       register(app). Zero-frontend — testable via curl. Frontend pane
       (split-diff view) is a separate iteration.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import HTTPException
except ImportError:
    HTTPException = None

# puac_eval.py writes here
RESULTS = Path(__file__).parent.parent / "benchmarks" / "results" / "puac_eval.json"


def _load() -> Dict[str, Any]:
    if not RESULTS.exists():
        return {"n": 0, "aggregate": {}, "per_prompt": []}
    try:
        return json.loads(RESULTS.read_text())
    except Exception as e:
        return {"error": str(e), "n": 0, "per_prompt": []}


def _summary(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "timestamp": data.get("timestamp"),
        "n": data.get("n", 0),
        "conditions": data.get("conditions", []),
        "aggregate": data.get("aggregate", {}),
        "prompts": [
            {"prompt_id": p["prompt_id"],
             "prompt_text": p["prompt_text"][:80],
             "CL": p["CL"], "AR": p["AR"], "PRR": p["PRR"], "PUAC": p["PUAC"]}
            for p in data.get("per_prompt", [])
        ],
    }


def _detail(data: Dict[str, Any], pid: str) -> Optional[Dict[str, Any]]:
    for p in data.get("per_prompt", []):
        if p["prompt_id"] == pid:
            # Shape the response for a side-by-side compare pane
            conds = p.get("conditions", {})
            return {
                "prompt_id": p["prompt_id"],
                "prompt_text": p["prompt_text"],
                "metrics": {
                    "CL": p["CL"], "AR": p["AR"], "PRR": p["PRR"],
                    "NHR": p["NHR"], "OAR": p["OAR"],
                    "PUAC": p["PUAC"],
                    "latency_sec": p["latency_sec"],
                },
                "conditions": {
                    name: {
                        "response": c["response"],
                        "judge_score": c["judge_score"],
                        "n_injected": c["n_injected"],
                        "n_referenced": c["n_referenced"],
                    } for name, c in conds.items()
                },
                "interpretation": _interpret(p),
            }
    return None


def _interpret(p: Dict[str, Any]) -> str:
    """One-line human-readable summary."""
    cl, ar, prr = p["CL"], p["AR"], p["PRR"]
    if prr == 1:
        return (f"POST-RATIONALIZATION: AR={ar:.0%} but CL={cl:+.2f} — "
                "items were referenced but did not causally improve the answer")
    if cl >= 0.15:
        return f"STRONG CAUSAL LIFT (+{cl:.2f}): memory measurably improved the answer"
    if cl <= -0.15:
        return f"NEGATIVE LIFT ({cl:+.2f}): memory made the answer WORSE — likely over-anchoring"
    if ar < 0.20:
        return f"LOW ATTRIBUTION ({ar:.0%}): memory was surfaced but ignored"
    return f"NEUTRAL: CL={cl:+.2f} AR={ar:.0%} — memory neither helped nor hurt"


def register(app):
    """Register PUAC endpoints on an existing FastAPI app."""

    @app.get("/api/puac-compare")
    def puac_summary():
        data = _load()
        return _summary(data)

    @app.get("/api/puac-compare/{pid}")
    def puac_detail(pid: str):
        data = _load()
        result = _detail(data, pid)
        if result is None:
            if HTTPException:
                raise HTTPException(status_code=404, detail=f"prompt_id {pid!r} not found")
            return {"error": f"prompt_id {pid!r} not found"}
        return result


# CLI smoke: python3 puac_endpoint.py
if __name__ == "__main__":
    import sys
    data = _load()
    print(f"[puac-endpoint] loaded n={data.get('n', 0)} prompts")
    print(f"aggregate: {data.get('aggregate')}")
    if data.get("per_prompt"):
        p = data["per_prompt"][0]
        print(f"\nsample detail for {p['prompt_id']}:")
        print(json.dumps(_detail(data, p["prompt_id"]), indent=2)[:800])
