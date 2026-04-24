"""
bench_endpoint.py — Dashboard extension for non-PUAC bench results.

Endpoints:
  GET /api/bench/mab-n50   — MAB N=50 Wilson 95% CI all retrievers
  GET /api/bench/mcnemar   — McNemar paired significance table
  GET /api/bench/longmemeval — LongMemEval real N=10 by retriever
  GET /api/bench/homograph — Homograph surface-match audit
  GET /api/bench/g1-regression — G1 Recall@7 ctx vs ctx_v2
  GET /api/bench/summary   — all-in-one headline view
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

RESULTS = Path(__file__).parent.parent / "benchmarks" / "results"


def _load(name: str) -> Dict[str, Any]:
    p = RESULTS / name
    if not p.exists():
        return {"error": f"{name} not found"}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"error": str(e)}


def _mab_n50_shaped() -> Dict[str, Any]:
    data = _load("mab_n50_with_ci.json")
    if "error" in data:
        return data
    ordered = sorted(data.items(), key=lambda kv: kv[1].get("accuracy", 0))
    rows = [{
        "retriever": r,
        "accuracy": v.get("accuracy"),
        "n": v.get("n"),
        "correct": v.get("correct"),
        "ci_95": v.get("wilson_ci_95"),
        "halfwidth": v.get("ci_halfwidth"),
    } for r, v in ordered]
    return {
        "benchmark": "MemoryAgentBench Competency-4 (Conflict Resolution)",
        "n_cases": 50,
        "retrievers": len(rows),
        "rows": rows,
    }


def _longmemeval_shaped() -> Dict[str, Any]:
    data = _load("tier1_longmemeval_n10.json")
    if "error" in data:
        return data
    by = data.get("by_retriever", {})
    rows = sorted(
        [{"retriever": r, "accuracy": v["accuracy"], "correct": v["correct"], "n": v["n"]}
         for r, v in by.items()],
        key=lambda x: x["accuracy"]
    )
    return {
        "benchmark": "LongMemEval-S (ICLR 2025, real data)",
        "n_cases": data.get("n", 10),
        "sample_types": data.get("sample_question_types", []),
        "rows": rows,
    }


def _homograph_shaped() -> Dict[str, Any]:
    data = _load("homograph_audit.json")
    if "error" in data:
        return data
    return {
        "benchmark": "Homograph surface-match audit",
        "n_prompts": data.get("n_prompts"),
        "aggregate_rate": data.get("aggregate_surface_match_only_rate"),
        "threshold": data.get("threshold"),
        "verdict": data.get("verdict"),
        "per_prompt_top": sorted(
            data.get("per_prompt", []),
            key=lambda p: -p.get("surface_rate", 0)
        )[:10],
    }


def _g1_shaped() -> Dict[str, Any]:
    data = _load("g1_regression_ctx_v2.json")
    if "error" in data:
        return data
    return {
        "benchmark": "G1 Recall@7 regression (ctx_v2 Porter stemmer)",
        "n": data.get("n"),
        "ctx_recall_at_7": data.get("ctx_recall_at_7"),
        "ctx_v2_recall_at_7": data.get("ctx_v2_recall_at_7"),
        "delta": data.get("delta_absolute"),
        "per_age_bucket": data.get("per_age_bucket"),
        "overlap": data.get("overlap"),
    }


def _mcnemar_shaped() -> Dict[str, Any]:
    data = _load("mcnemar_n50.json")
    if "error" in data:
        return data
    rows = []
    for key, v in data.items():
        rows.append({
            "comparison": key.replace("_vs_", " vs "),
            "discordant": v.get("n_discordant"),
            "exact_p": v.get("exact_p_two_sided"),
            "chi2_cc": v.get("mcnemar_chi2_cc"),
            "verdict": "SIG" if v.get("exact_p_two_sided", 1.0) < 0.05 else
                       "MARGINAL" if v.get("exact_p_two_sided", 1.0) < 0.10 else
                       "NS",
        })
    return {
        "benchmark": "McNemar paired tests (MAB N=50)",
        "alpha": 0.05,
        "rows": rows,
    }


def register(app):
    @app.get("/api/bench/mab-n50")
    def mab_n50():
        return _mab_n50_shaped()

    @app.get("/api/bench/longmemeval")
    def longmemeval():
        return _longmemeval_shaped()

    @app.get("/api/bench/homograph")
    def homograph():
        return _homograph_shaped()

    @app.get("/api/bench/g1-regression")
    def g1():
        return _g1_shaped()

    @app.get("/api/bench/mcnemar")
    def mcnemar():
        return _mcnemar_shaped()

    @app.get("/api/bench/summary")
    def summary():
        return {
            "mab_n50": _mab_n50_shaped(),
            "longmemeval": _longmemeval_shaped(),
            "mcnemar": _mcnemar_shaped(),
            "homograph": _homograph_shaped(),
            "g1": _g1_shaped(),
        }


if __name__ == "__main__":
    # CLI smoke
    print(json.dumps(_mab_n50_shaped(), indent=2)[:800])
