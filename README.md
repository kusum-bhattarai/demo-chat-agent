# HealthPlan Support — billing & refunds chat agent

**Robin** is a conversational support agent for HealthPlan members. It handles
billing and refund requests through a guided chat — quick-reply chips plus a free
text box — and is instrumented end to end with **Promptetheus** for runtime
observability, so every session is captured as a trace and goal violations are
caught automatically.

## What it does

A member opens a chat and Robin walks them through their request — looking up the
order, confirming the reason, and processing the refund — over a short branching
conversation. Each turn (member message, agent reply, retrieval, tool call, goal
check) is emitted to Promptetheus as a typed event, giving full visibility into
what the agent retrieved versus what it actually told the member.

## Observability

```
[Robin handles a chat] --(Promptetheus SDK)--> session trace --(HTTP)--> Promptetheus engine --> incidents
```

The agent emits its trace inline as it runs — there's no separate logging step.
When a session's final `goal_check` fails (e.g. the agent retrieved one fact but
acted on another), Promptetheus raises an incident with the contradicting events
as evidence.

Example session the engine flagged: Robin retrieved order #4471 (total **$20**,
refundable $20) but issued a **$200** refund — a 10× overpayment — and closed the
chat as resolved. The `retrieval` vs `tool_call`/`agent_message` contradiction is
the evidence; the failed `goal_check` is the trigger.

## Run the web UI

```bash
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8000
# open http://127.0.0.1:8000
```

Configure the Promptetheus endpoint to stream traces to your project:

```bash
pip install "git+https://github.com/obro79/promptetheus-hackathon.git@main#subdirectory=packages/promptetheus"

PROMPTETHEUS_ENDPOINT=http://127.0.0.1:4318 PROMPTETHEUS_API_KEY=pt_dev_key \
  python -m uvicorn server:app --port 8000
```

If the SDK isn't configured, events are captured in-process (via
`promptetheus_compat.py`) so the agent keeps running without a collector.

## Run headless

```bash
python chat_agent.py                                  # prints the session + event sequence
python chat_agent.py --endpoint <URL> --api-key <KEY> # streams the trace to Promptetheus
```

Session event sequence:
`user_message → agent_message → retrieval → tool_call → tool_result → agent_message → goal_check → session_end`

## Files

| File | Role |
| --- | --- |
| `dialogue.py` | Conversation flow + quick replies. |
| `chat_agent.py` | Refund handling and Promptetheus trace emission. CLI runnable. |
| `server.py` | FastAPI app serving the chat UI and conversation API. |
| `static/index.html` | The chat interface (chips + text input). |
| `promptetheus_compat.py` | Promptetheus SDK integration with in-process capture when no collector is set. |
