"""Web chat UI for the refund-overpayment demo agent.

Serves a small chat page and a /api/run endpoint that plays the scripted refund
conversation, emits the Promptetheus trace, and returns the transcript so the UI
can render it bubble-by-bubble. The page shows the agent silently overpaying a
refund, then the trace status (failed goal_check → incident).

Run:
    python -m uvicorn server:app --reload --port 8000
    # then open http://127.0.0.1:8000

Point it at a live Promptetheus API for the demo (needs the real SDK):
    PROMPTETHEUS_ENDPOINT=http://127.0.0.1:4318 PROMPTETHEUS_API_KEY=pt_dev_key \
        python -m uvicorn server:app --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from chat_agent import run_demo

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Promptetheus demo — support chat agent")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/run")
def run() -> JSONResponse:
    """Play the scripted refund conversation and emit the trace."""
    endpoint = os.environ.get("PROMPTETHEUS_ENDPOINT")
    api_key = os.environ.get("PROMPTETHEUS_API_KEY")
    summary = run_demo(endpoint=endpoint or None, api_key=api_key or None)
    summary["target"] = endpoint or "in-memory (local)"
    return JSONResponse(summary)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
