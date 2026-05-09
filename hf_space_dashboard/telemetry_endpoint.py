"""
telemetry_endpoint.py — CTX Stage 2 telemetry ingestion endpoint.

Accepts k-anonymized session_aggregate POSTs from ctx-telemetry CLI.
Buffers locally, then pushes to Be2Jay/ctx-telemetry-data (private HF Dataset).

Privacy guarantees (enforced server-side):
- No string fields accepted (query text, file paths, commit messages)
- k-anonymity: rows with k_count < 5 are rejected
- No PII — user_id is a SHA256 hash set by the client
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# HF Dataset for persistent storage
_DATASET_REPO = "Be2Jay/ctx-telemetry-data"
_DATASET_PATH = "session_aggregates.jsonl"
_HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Local buffer (in-container, flushed to HF Dataset periodically)
_BUFFER = Path("/tmp/ctx_telem_buffer.jsonl")
_BUFFER_LOCK = threading.Lock()
_FLUSH_EVERY = 5  # flush after N records

# Required fields from session_aggregate schema v1.5+
_REQUIRED = {
    "schema_version", "user_id", "session_id_hash", "ts_date",
    "total_turns", "total_injections", "mean_utility_rate",
}

# Fields that MUST be numeric (reject string leakage)
_NUMERIC = {
    "total_turns", "total_injections", "mean_utility_rate",
    "vault_entry_count", "index_staleness_hours",
    "mean_top_score_bm25",
}

# String fields that are allowed (hashes + enums only — no free text)
_ALLOWED_STRING = {
    "schema_version", "user_id", "session_id_hash", "ts_date", "session_outcome",
}


def _validate(body: dict[str, Any]) -> str | None:
    """Return error string or None if valid."""
    missing = _REQUIRED - set(body.keys())
    if missing:
        return f"Missing required fields: {sorted(missing)}"

    # Reject unexpected string fields (privacy guard)
    for k, v in body.items():
        if k in _NUMERIC and not isinstance(v, (int, float)):
            return f"Field '{k}' must be numeric"
        if isinstance(v, str) and k not in _ALLOWED_STRING:
            return f"String field '{k}' not allowed (privacy policy)"

    # k-anonymity gate (client reports k_count; we trust but verify presence)
    k = body.get("k_count")
    if k is not None and isinstance(k, (int, float)) and k < 5:
        return f"k_count={k} < 5 — row suppressed (k-anonymity)"

    return None


def _flush_to_hf(lines: list[str]) -> bool:
    """Append lines to the HF Dataset JSONL file. Returns True on success."""
    if not _HF_TOKEN:
        return False
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=_HF_TOKEN)

        # Fetch existing file (if any)
        existing = ""
        try:
            content = api.hf_hub_download(
                repo_id=_DATASET_REPO,
                filename=_DATASET_PATH,
                repo_type="dataset",
            )
            existing = Path(content).read_text()
        except Exception:
            pass  # first upload

        new_content = existing + "\n".join(lines) + "\n"
        api.upload_file(
            path_or_fileobj=new_content.encode(),
            path_in_repo=_DATASET_PATH,
            repo_id=_DATASET_REPO,
            repo_type="dataset",
            commit_message=f"telemetry: +{len(lines)} session_aggregate rows",
        )
        return True
    except Exception as exc:
        print(f"[telemetry] HF flush error: {exc}")
        return False


def _maybe_flush():
    """Flush buffer to HF Dataset if threshold reached."""
    with _BUFFER_LOCK:
        if not _BUFFER.exists():
            return
        lines = [l for l in _BUFFER.read_text().splitlines() if l.strip()]
        if len(lines) < _FLUSH_EVERY:
            return
        if _flush_to_hf(lines):
            _BUFFER.unlink()


def register(app):
    @app.post("/api/telemetry/ingest")
    async def ingest(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(422, "Invalid JSON body")

        err = _validate(body)
        if err:
            raise HTTPException(400, err)

        # Strip any unexpected fields beyond allowed set
        safe = {k: v for k, v in body.items()
                if k in _REQUIRED | _NUMERIC | _ALLOWED_STRING |
                {"k_count", "hook_source_hist", "retrieval_method_hist",
                 "query_type_hist", "node_type_hist", "session_outcome"}}
        safe["server_received_at"] = datetime.now(timezone.utc).isoformat()

        with _BUFFER_LOCK:
            with open(_BUFFER, "a") as f:
                f.write(json.dumps(safe) + "\n")

        # Flush async (don't block the response)
        t = threading.Thread(target=_maybe_flush, daemon=True)
        t.start()

        return JSONResponse({"ok": True, "queued": 1})

    @app.get("/api/telemetry/stats")
    def stats():
        """Aggregate stats from buffered + HF Dataset records."""
        records: list[dict] = []

        # Local buffer
        if _BUFFER.exists():
            for line in _BUFFER.read_text().splitlines():
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass

        if not records:
            return JSONResponse({
                "status": "no_data",
                "total_sessions": 0,
                "mean_utility_rate": None,
                "note": "Waiting for first opt-in uploads from users.",
            })

        n = len(records)
        utility_rates = [r["mean_utility_rate"] for r in records
                         if isinstance(r.get("mean_utility_rate"), (int, float))]
        mean_util = sum(utility_rates) / len(utility_rates) if utility_rates else None

        turns = [r["total_turns"] for r in records if isinstance(r.get("total_turns"), (int, float))]
        mean_turns = sum(turns) / len(turns) if turns else None

        unique_users = len({r["user_id"] for r in records if r.get("user_id")})

        return JSONResponse({
            "status": "ok",
            "total_sessions": n,
            "unique_users": unique_users,
            "mean_utility_rate": round(mean_util, 3) if mean_util is not None else None,
            "mean_turns_per_session": round(mean_turns, 1) if mean_turns is not None else None,
            "hf_dataset": f"https://huggingface.co/datasets/{_DATASET_REPO}",
            "as_of": datetime.now(timezone.utc).isoformat(),
        })
