"""Web chat UI for the refund-overpayment demo agent.

Serves an interactive chat page with quick-reply chips and a text box. The agent
(Robin) guides the user through a refund and silently overpays it; at that moment
the realized conversation is replayed into a Promptetheus trace ending in a
failed goal_check.

Run:
    python -m uvicorn server:app --reload --port 8000
    # then open http://127.0.0.1:8000

Point it at a live Promptetheus API for the demo (needs the real SDK):
    PROMPTETHEUS_ENDPOINT=http://127.0.0.1:4318 PROMPTETHEUS_API_KEY=pt_dev_key \
        python -m uvicorn server:app --port 8000
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

import dialogue
from chat_agent import emit_ops

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Promptetheus demo — support chat agent")


def _trigger_analyze(endpoint: str, session_id: str) -> int | None:
    """Ask the engine to analyze the just-posted trace so the incident forms
    without a manual step. Best-effort: returns the HTTP status, or None on any
    failure (the trace is already ingested regardless)."""
    import json
    import urllib.request

    console_token = os.environ.get("PROMPTETHEUS_CONSOLE_TOKEN", "pt_console_token")
    url = f"{endpoint.rstrip('/')}/api/traces/{session_id}/analyze"
    req = urllib.request.Request(
        url,
        data=json.dumps({}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {console_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except Exception:
        return None


def _configured_emit():
    """Bind the HTTP endpoint/key (if set) onto the trace emitter."""
    endpoint = os.environ.get("PROMPTETHEUS_ENDPOINT") or None
    api_key = os.environ.get("PROMPTETHEUS_API_KEY") or None
    target = endpoint or "in-memory (local)"

    def emit(ops, *, session_id):
        summary = emit_ops(ops, endpoint=endpoint, api_key=api_key, session_id=session_id)
        summary["target"] = target
        # Once the failing trace is posted, kick analysis so the incident forms
        # automatically — running the agent end-to-end yields a real incident.
        if endpoint:
            summary["analyzed_status"] = _trigger_analyze(endpoint, session_id)
        return summary

    return emit


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.post("/api/chat")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    conversation_id = body.get("conversation_id")
    choice_id = body.get("choice_id")
    text = body.get("text")

    emit = _configured_emit()
    if not conversation_id or conversation_id not in dialogue._STORE:
        convo = dialogue.Conversation()
        dialogue._STORE[convo.id] = convo
        return JSONResponse(convo.start(emit))

    convo = dialogue._STORE[conversation_id]
    return JSONResponse(convo.reply(emit, choice_id=choice_id, text=text))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
