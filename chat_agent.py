"""Deterministic chat-agent demo — refund overpayment (silent failure).

A support-chat fixture for the Promptetheus hackathon demo (one of three failing
agents: chat, voice, browser). A customer asks for a refund. The agent retrieves
the CORRECT order (total $20, refundable $20), then issues a $200 refund — a 10x
overpayment — and confirms as if it helped. The tool call "succeeded"; the agent
still did real damage. It ends with a failed goal_check, the analyzer's reliable
incident trigger.

The conversation is scripted (deterministic) so it can't flake on stage. The
events it emits are real Promptetheus SDK events — the engine can't tell the
difference between a scripted and a live agent; all it sees is the trace.

Local, no backend (captures events in memory and prints them):
    python chat_agent.py

Post to a running Promptetheus API (for the demo, needs the real SDK):
    python chat_agent.py --endpoint http://127.0.0.1:4318 --api-key pt_dev_key
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from promptetheus_compat import USING_REAL_SDK, InMemoryTransport, trace

DEFAULT_SESSION_ID = "demo_chat_refund_overpayment"
DEFAULT_GOAL = "Refund the customer the correct amount for their order"

# --- Scenario facts -------------------------------------------------------
ORDER_ID = "#4471"
ITEM = "Wireless Earbuds"
ORDER_TOTAL = 20.00      # what the order actually cost
REFUND_DUE = 20.00       # the correct refund
WRONG_REFUND = 200.00    # what the agent actually issues (10x overpayment)
REFUND_TXN = "rf_88213"


def play(session: Any) -> list[dict[str, str]]:
    """Run the scripted refund conversation.

    Emits the trace through ``session`` AND returns the display messages (role +
    text) so a UI can render the transcript. Failure shape:
      user_message -> agent_message -> retrieval (CORRECT $20) ->
      tool_call/tool_result (issues $200) -> agent_message (confirms $200) ->
      goal_check(passed=False) -> session_end.
    """
    transcript: list[dict[str, str]] = []

    def show(role: str, text: str) -> None:
        transcript.append({"role": role, "text": text})

    user_text = f"Hi, I'd like a refund for order {ORDER_ID} — the earbuds stopped working."
    session.user_message(user_text)
    show("user", user_text)

    ack = f"I'm sorry to hear that! Let me pull up order {ORDER_ID} for you."
    session.agent_message(ack)
    show("agent", ack)

    # The evidence: the lookup returns the CORRECT order — $20, refundable $20.
    session.retrieval(
        query=f"order {ORDER_ID} refund eligibility",
        documents=[
            {
                "order_id": ORDER_ID,
                "item": ITEM,
                "total_usd": ORDER_TOTAL,
                "refundable_usd": REFUND_DUE,
                "currency": "USD",
                "status": "eligible",
            }
        ],
    )
    show(
        "tool",
        f"🔎 Order {ORDER_ID} — {ITEM} · total ${ORDER_TOTAL:.2f} · "
        f"refundable ${REFUND_DUE:.2f} (eligible)",
    )

    # The silent failure: the agent issues 10x what it just retrieved.
    call_id = f"refund_{ORDER_ID.strip('#')}"
    session.tool_call(
        "issue_refund",
        {"order_id": ORDER_ID, "amount_usd": WRONG_REFUND},
        call_id=call_id,
    )
    show("tool", f"⚙️ issue_refund(order={ORDER_ID}, amount=${WRONG_REFUND:.2f})")

    session.tool_result(
        call_id,
        result={"status": "succeeded", "refunded_usd": WRONG_REFUND, "txn": REFUND_TXN},
    )
    show("tool", f"✅ refund processed · txn {REFUND_TXN}")

    confirm = (
        f"All set! I've refunded ${WRONG_REFUND:.2f} back to your original card. "
        "Sorry again for the trouble! 🎉"
    )
    session.agent_message(confirm)
    show("agent", confirm)

    session.goal_check(
        False,
        [
            f"Order {ORDER_ID} total was ${ORDER_TOTAL:.2f} (refundable "
            f"${REFUND_DUE:.2f}) but the agent issued a ${WRONG_REFUND:.2f} "
            "refund — a 10x overpayment"
        ],
    )
    session.end("completed")
    return transcript


def run_demo(
    *,
    transport: Any | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    session_id: str = DEFAULT_SESSION_ID,
) -> dict[str, Any]:
    """Emit the deterministic failing refund trace; return a summary + transcript."""
    if transport is None:
        transport = "http" if endpoint else InMemoryTransport()

    with trace.start(
        agent="support-chat-agent",
        user_goal=DEFAULT_GOAL,
        session_id=session_id,
        transport=transport,
        endpoint=endpoint,
        api_key=api_key,
        environment="demo",
        metadata={"surface": "chat", "demo": "refund_overpayment"},
        tags=["demo", "chat-agent", "refund-overpayment"],
    ) as session:
        transcript = play(session)

    events = list(getattr(transport, "events", []) or [])
    return {
        "session_id": session_id,
        "using_real_sdk": USING_REAL_SDK,
        "events_emitted": len(events),
        "event_types": [str(event.get("type")) for event in events],
        "goal_failed": True,
        "transcript": transcript,
    }


def emit_ops(
    ops: list[dict[str, Any]],
    *,
    transport: Any | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    session_id: str = DEFAULT_SESSION_ID,
) -> dict[str, Any]:
    """Replay a list of trace ops (built by the interactive dialogue) into one
    SDK session. Each op is a dict like ``{"op": "user_message", "content": ...}``.
    Lets the live, branching conversation produce a single coherent trace.
    """
    if transport is None:
        transport = "http" if endpoint else InMemoryTransport()

    with trace.start(
        agent="support-chat-agent",
        user_goal=DEFAULT_GOAL,
        session_id=session_id,
        transport=transport,
        endpoint=endpoint,
        api_key=api_key,
        environment="demo",
        metadata={"surface": "chat", "demo": "refund_overpayment"},
        tags=["demo", "chat-agent", "refund-overpayment"],
    ) as session:
        for op in ops:
            kind = op["op"]
            if kind == "user_message":
                session.user_message(op["content"])
            elif kind == "agent_message":
                session.agent_message(op["content"])
            elif kind == "retrieval":
                session.retrieval(op["query"], documents=op["documents"])
            elif kind == "tool_call":
                session.tool_call(op["tool_name"], op["arguments"], call_id=op["call_id"])
            elif kind == "tool_result":
                session.tool_result(op["call_id"], result=op.get("result"))
            elif kind == "goal_check":
                session.goal_check(op["passed"], op.get("mismatches"))
            elif kind == "end":
                session.end(op.get("status", "completed"))

    events = list(getattr(transport, "events", []) or [])
    return {
        "session_id": session_id,
        "using_real_sdk": USING_REAL_SDK,
        "events_emitted": len(events),
        "event_types": [str(event.get("type")) for event in events],
        "goal_failed": any(o["op"] == "goal_check" and not o["passed"] for o in ops),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", help="Promptetheus API URL (needs the real SDK)")
    parser.add_argument("--api-key", help="Promptetheus project API key")
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID)
    args = parser.parse_args(argv)

    if args.endpoint and not USING_REAL_SDK:
        print(
            "⚠️  --endpoint set but the real SDK isn't installed; "
            "events will be captured locally only.\n"
            '    Install: pip install "git+https://github.com/obro79/'
            'promptetheus-hackathon.git@main#subdirectory=packages/promptetheus"\n'
        )

    summary = run_demo(
        endpoint=args.endpoint,
        api_key=args.api_key,
        session_id=args.session_id,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
