"""
autotune.py — Auto-tune parameter reader for bm25-memory.

Reads ~/.claude/ctx-auto-tune.json (written by ctx-telemetry tune).
Exposes:
  AUTO_TUNE: dict       — raw recommendations (empty if file absent/invalid)
  AUTO_TUNE_ACTIVE: bool — True when recommendations are loaded and valid
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
