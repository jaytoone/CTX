"""CTX Dashboard — static snapshot Space for 모두의 창업 2026 submission.

Serves pre-baked API snapshots (captured from the live dashboard with demo mode)
so judges can access the UI 24/7 without any backend state or WSL2 dependency.

Entry point for HF Spaces Docker SDK. Runs on port 7860 by default.
"""
import json
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).parent
SNAPSHOTS = HERE / "snapshots"
STATIC = HERE / "static"

app = FastAPI(title="CTX Dashboard (Demo)")

# Register PUAC + Tier 3 pairwise endpoints (iter 3, 6)
try:
    import puac_endpoint
    puac_endpoint.register(app)
except Exception:
    pass
try:
    import tier3_pairwise
    tier3_pairwise.register(app)
except Exception:
    pass


def _load(name: str) -> dict:
    p = SNAPSHOTS / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception as e:
            return {"error": f"failed to parse {name}: {e}"}
    return {"error": f"snapshot {name} not found"}


@app.get("/api/snapshot")
def snapshot():
    return JSONResponse(_load("snapshot.json"))


@app.get("/api/graph")
def graph():
    return JSONResponse(_load("graph.json"))


@app.get("/api/wow")
def wow():
    return JSONResponse(_load("wow.json"))


@app.get("/api/prompt-contributors")
def prompt_contributors(prompt_id: str, max_items: int = 12):
    return JSONResponse(_load(f"contributors-{prompt_id}.json"))


@app.get("/api/node-explain")
def node_explain(node_id: str, prompt_id: str):
    """Node-explain uses the _detail field embedded in the contributors snapshot
    so single-node click still works without a separate snapshot per node."""
    contribs = _load(f"contributors-{prompt_id}.json")
    for c in contribs.get("contributors", []):
        if c.get("node_id") == node_id and "_detail" in c:
            return JSONResponse(c["_detail"])
    return JSONResponse({"error": "node not found in snapshot", "node_id": node_id})


@app.get("/api/samples")
def samples(offset: int = 0, limit: int = 10):
    return JSONResponse(_load("samples.json"))


@app.post("/api/samples/refresh")
def samples_refresh():
    return JSONResponse({"ok": True, "note": "demo snapshot — refresh is a no-op"})


@app.post("/api/graph/refresh")
def graph_refresh():
    return JSONResponse({"ok": True, "note": "demo snapshot — refresh is a no-op"})


@app.get("/stream")
def stream():
    # SSE stream disabled in static mode — client handles absence gracefully
    return Response(status_code=404, content="SSE disabled in demo snapshot")


# Static files for the dashboard
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def root():
    return FileResponse(STATIC / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
