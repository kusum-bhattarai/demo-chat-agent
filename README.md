# Chat agent — Promptetheus demo (refund overpayment)

A support-chat agent that **fails silently** for the Promptetheus hackathon demo
(one of three failing agents: chat, voice, browser). It comes with a small **web
chat UI** so the failure is visible on a projector.

**Scenario:** a customer asks for a refund on order #4471. The agent retrieves
the correct order (**$20**, refundable $20), then issues a **$200** refund — a
10× overpayment — and confirms as if it helped. The trace ends in a failed
`goal_check`, which the Promptetheus engine detects as an incident.

The conversation is **scripted** (deterministic) so it can't flake on stage, but
the events it emits are real Promptetheus SDK events. The engine can't tell a
scripted agent from a live one — all it ever sees is the trace.

## How it fits the demo

```
[chat agent runs] --(Promptetheus SDK)--> trace of events --(HTTP)--> Promptetheus engine --> incident
```

There are no separate "fake logs": the agent running **is** the logging. As the
scripted conversation plays, the SDK emits the typed events. The browser and
voice agents do the same with their own traces.

## Run the web UI

```bash
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8000
# open http://127.0.0.1:8000  →  click "Start refund chat"
```

The Promptetheus SDK is **optional** for this local demo — if it isn't installed,
the agent falls back to a local in-memory recorder (`promptetheus_compat.py`) and
the UI badge shows "local fallback". Install the SDK and point the server at a
live API to post real traces:

```bash
pip install "git+https://github.com/obro79/promptetheus-hackathon.git@main#subdirectory=packages/promptetheus"

PROMPTETHEUS_ENDPOINT=http://127.0.0.1:4318 PROMPTETHEUS_API_KEY=pt_dev_key \
  python -m uvicorn server:app --port 8000
```

## Run headless (just the trace)

```bash
python chat_agent.py                                  # prints transcript + event sequence
python chat_agent.py --endpoint <URL> --api-key <KEY> # posts the trace (needs the real SDK)
```

Expected event sequence:
`user_message → agent_message → retrieval → tool_call → tool_result → agent_message → goal_check(passed=False) → session_end`

## Files

| File | Role |
| --- | --- |
| `chat_agent.py` | The scripted agent: the conversation + the trace it emits. CLI runnable. |
| `server.py` | FastAPI web UI; `/api/run` plays the conversation and emits the trace. |
| `static/index.html` | The chat page. |
| `promptetheus_compat.py` | Uses the real SDK if installed, else a local fallback recorder. |

See `CLAUDE.md` for the full build brief and SDK contract.
