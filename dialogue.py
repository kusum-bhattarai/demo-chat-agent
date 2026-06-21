"""Guided support-chat dialogue (deterministic, branching, with quick replies).

A small conversation tree for the refund-overpayment demo. The agent (Robin)
opens, offers quick-reply chips, and the user clicks one or types. Every path
funnels to the refund, where the agent retrieves the CORRECT order ($20) and
then issues a $200 refund — the silent failure. At that point the whole realized
conversation is replayed into a single Promptetheus trace ending in a failed
goal_check.

The tree separates *display* (what the chat shows) from *trace ops* (the SDK
events), so the engine sees one coherent session no matter which branches the
user wandered through.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from chat_agent import (
    ITEM,
    ORDER_ID,
    ORDER_TOTAL,
    REFUND_DUE,
    REFUND_TXN,
    WRONG_REFUND,
    emit_ops,
)

# --- step builders --------------------------------------------------------
# Each node has a `flow`: an ordered list of steps. A step both renders (agent
# bubble / tool line) and may carry a trace op.


def agent(text: str) -> dict[str, Any]:
    return {"type": "agent", "text": text, "op": {"op": "agent_message", "content": text}}


def tool(text: str, op: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool", "text": text, "op": op}


def op_only(op: dict[str, Any]) -> dict[str, Any]:
    return {"type": "op", "op": op}


def opt(id: str, label: str, next: str) -> dict[str, str]:
    return {"id": id, "label": label, "next": next}


_call_id = f"refund_{ORDER_ID.strip('#')}"

# The failure payload. The chat UI stays *silent*: Robin retrieves the correct
# order ($20) and issues a $200 refund, but the page shows only a confident,
# successful exchange — no eligibility line, no amounts, no "that's more than I
# paid". The contradiction lives purely in the trace ops (retrieval $20 vs
# tool_call $200 + failed goal_check), which is exactly what Promptetheus
# catches downstream. (op_only steps emit a trace event but render nothing.)
_REFUND_FLOW = [
    agent("So sorry about that! Let me pull up the order and process your refund — one moment… 🔄"),
    op_only(
        {
            "op": "retrieval",
            "query": f"order {ORDER_ID} refund eligibility",
            "documents": [
                {
                    "order_id": ORDER_ID,
                    "item": ITEM,
                    "total_usd": ORDER_TOTAL,
                    "refundable_usd": REFUND_DUE,
                    "currency": "USD",
                    "status": "eligible",
                }
            ],
        }
    ),
    op_only(
        {
            "op": "tool_call",
            "tool_name": "issue_refund",
            "arguments": {"order_id": ORDER_ID, "amount_usd": WRONG_REFUND},
            "call_id": _call_id,
        }
    ),
    op_only(
        {
            "op": "tool_result",
            "call_id": _call_id,
            "result": {"status": "succeeded", "refunded_usd": WRONG_REFUND, "txn": REFUND_TXN},
        }
    ),
    agent(
        "All set — I've processed your refund. You'll see it back on your original "
        "card in 3–5 business days. 🎉"
    ),
    agent("Is there anything else I can help you with?"),
    op_only(
        {
            "op": "goal_check",
            "passed": False,
            "mismatches": [
                f"Order {ORDER_ID} total was ${ORDER_TOTAL:.2f} (refundable "
                f"${REFUND_DUE:.2f}) but the agent issued a ${WRONG_REFUND:.2f} "
                "refund — a 10x overpayment"
            ],
        }
    ),
    op_only({"op": "end", "status": "completed"}),
]


NODES: dict[str, dict[str, Any]] = {
    "greeting": {
        "flow": [
            agent("Hi! 👋 I'm Robin, your HealthPlan billing assistant."),
            agent("What can I help you with today?"),
        ],
        "options": [
            opt("refund", "I need a refund", "ask_order"),
            opt("coverage", "Is my medication covered?", "coverage_redirect"),
            opt("human", "Talk to a human", "human_redirect"),
        ],
    },
    "coverage_redirect": {
        "flow": [
            agent(
                "I'm the billing & refunds assistant, so I can't see clinical coverage — "
                "but I'm great with payments and refunds!"
            ),
            agent("Is there a refund I can help with?"),
        ],
        "options": [
            opt("refund", "Yes, I need a refund", "ask_order"),
            opt("no", "No, that's all", "goodbye"),
        ],
    },
    "human_redirect": {
        "flow": [
            agent("I can connect you to a human — the current wait is about 12 minutes. ⏳"),
            agent("I can usually sort refunds instantly, though. Want me to try?"),
        ],
        "options": [
            opt("refund", "Try the refund", "ask_order"),
            opt("wait", "I'll wait for a human", "goodbye"),
        ],
    },
    "ask_order": {
        "flow": [
            agent("Happy to help with a refund. 💳"),
            agent("Which order is it for?"),
        ],
        "options": [
            opt("o4471", f"Order {ORDER_ID} — {ITEM}", "ask_reason"),
            opt("other", "A different order", "ask_order_number"),
        ],
    },
    "ask_order_number": {
        "flow": [agent("Sure — what's the order number?")],
        "options": [opt("o4471b", ORDER_ID, "ask_reason")],
        "free_text_next": "ask_reason",
    },
    "ask_reason": {
        "flow": [
            agent(f"Got it — order {ORDER_ID}, {ITEM} (${ORDER_TOTAL:.2f}). 🎧"),
            agent("What's the reason for the refund?"),
        ],
        "options": [
            opt("broken", "They stopped working", "process"),
            opt("damaged", "Arrived damaged", "process"),
            opt("mind", "Changed my mind", "process"),
        ],
        "free_text_next": "process",
    },
    "process": {
        "flow": _REFUND_FLOW,
        "failure": True,
        "options": [
            opt("done", "That's everything, thanks!", "goodbye"),
            opt("more", "I have another question", "greeting"),
        ],
    },
    "goodbye": {
        "flow": [agent("Thanks for chatting with HealthPlan Support — take care! 💙")],
        "options": [],
        "terminal": True,
    },
}


class Conversation:
    """Per-session dialogue state: current node + accumulated trace ops."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.node = "greeting"
        self.ops: list[dict[str, Any]] = []
        self.emitted = False

    def _enter(self, node_id: str, emit: Callable[..., dict[str, Any]]) -> dict[str, Any]:
        """Render a node: collect display messages, append its trace ops, and if
        it's the failure node, emit the whole trace once."""
        self.node = node_id
        node = NODES[node_id]
        messages: list[dict[str, str]] = []

        for step in node["flow"]:
            if step["type"] in ("agent", "tool"):
                messages.append({"role": step["type"], "text": step["text"]})
            if not self.emitted and "op" in step:
                self.ops.append(step["op"])

        incident = None
        if node.get("failure") and not self.emitted:
            incident = emit(self.ops, session_id=f"demo_chat_refund_{self.id}")
            self.emitted = True

        return {
            "conversation_id": self.id,
            "messages": messages,
            "options": [{"id": o["id"], "label": o["label"]} for o in node["options"]],
            "terminal": bool(node.get("terminal")),
            "incident": incident,
        }

    def start(self, emit: Callable[..., dict[str, Any]]) -> dict[str, Any]:
        return self._enter("greeting", emit)

    def reply(
        self,
        emit: Callable[..., dict[str, Any]],
        *,
        choice_id: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        node = NODES[self.node]
        label: str | None = None
        nxt: str | None = None

        if choice_id:
            for o in node["options"]:
                if o["id"] == choice_id:
                    label, nxt = o["label"], o["next"]
                    break
        if nxt is None and text and node.get("free_text_next"):
            label, nxt = text.strip(), node["free_text_next"]

        if nxt is None:  # unrecognized input — re-render current node's options
            return {
                "conversation_id": self.id,
                "messages": [],
                "options": [{"id": o["id"], "label": o["label"]} for o in node["options"]],
                "terminal": bool(node.get("terminal")),
                "incident": None,
            }

        if not self.emitted and label is not None:
            self.ops.append({"op": "user_message", "content": label})

        result = self._enter(nxt, emit)
        result["user_echo"] = label
        return result


# In-memory conversation store (fine for a single-user demo).
_STORE: dict[str, Conversation] = {}


def handle(conversation_id: str | None, choice_id: str | None, text: str | None) -> dict[str, Any]:
    """Entry point used by the web server. Returns the next render."""
    if not conversation_id or conversation_id not in _STORE:
        convo = Conversation()
        _STORE[convo.id] = convo
        return convo.start(emit_ops)

    convo = _STORE[conversation_id]
    return convo.reply(emit_ops, choice_id=choice_id, text=text)
