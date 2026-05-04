"""
autotune.py — Auto-tune parameter reader for bm25-memory.

Reads ~/.claude/ctx-auto-tune.json (written by ctx-telemetry tune).
Exposes:
  AUTO_TUNE: dict       — raw recommendations (empty if file absent/invalid)
  AUTO_TUNE_ACTIVE: bool — True when recommendations are loaded and valid
  get_g1_top_k(prompt, auto_tune) -> int
  get_g2d_top_k(prompt, auto_tune) -> int
"""
import json
from pathlib import Path

_AUTO_TUNE_PATH = Path.home() / ".claude" / "ctx-auto-tune.json"

AUTO_TUNE: dict = {}
AUTO_TUNE_ACTIVE: bool = False

try:
    if _AUTO_TUNE_PATH.exists():
        _raw = json.loads(_AUTO_TUNE_PATH.read_text())
        if isinstance(_raw, dict):
            AUTO_TUNE = _raw
            AUTO_TUNE_ACTIVE = True
except Exception:
    pass


def get_g1_top_k(prompt: str, auto_tune: dict) -> int:
    """Compute G1 top_k based on auto-tune recommendations and query type."""
    from .corpus import _classify_query_type
    top_k = 7
    if not auto_tune:
        return top_k
    qtype = _classify_query_type(prompt)
    temporal_gap = auto_tune.get("temporal_utility_gap", 0)
    if qtype == "TEMPORAL" and temporal_gap > 0.10:
        top_k = 5
    proj_type = auto_tune.get("project_type_hint", "")
    proj_conf = auto_tune.get("project_type_confidence", "LOW")
    if proj_conf in ("HIGH", "MEDIUM"):
        if proj_type == "python_ml":
            top_k = min(top_k + 1, 10)
        elif proj_type == "nextjs_react":
            top_k = max(top_k - 1, 4)
    return top_k


def get_g2d_top_k(prompt: str, auto_tune: dict) -> int:
    """Compute G2-DOCS top_k based on auto-tune recommendations and query type."""
    from .corpus import _classify_query_type
    top_k = 5
    if not auto_tune:
        return top_k
    qtype = _classify_query_type(prompt)
    temporal_gap = auto_tune.get("temporal_utility_gap", 0)
    if qtype == "TEMPORAL" and temporal_gap > 0.10:
        top_k = 3
    proj_type = auto_tune.get("project_type_hint", "")
    proj_conf = auto_tune.get("project_type_confidence", "LOW")
    if proj_conf in ("HIGH", "MEDIUM"):
        if proj_type == "nextjs_react":
            top_k = min(top_k + 1, 8)
        elif proj_type == "rust_systems":
            top_k = max(top_k - 1, 3)
    return top_k
