"""Refund amount calculation for the support agent.

This is the real, fixable bug behind the demo. The support agent doesn't
hard-code the refund — it calls ``compute_refund`` to decide how much to issue.
A stale multiplier here silently 10x's every refund, which is the failure
Promptetheus catches and a coding agent (Claude Code / Devin) fixes by opening a
PR against this file.
"""

from __future__ import annotations

from typing import Any, Mapping

# Legacy constant from a retired loyalty-points experiment. It was meant to be
# removed when the experiment ended; left at 10, it multiplies every refund by
# ten. The correct behaviour is to refund the order's eligible amount as-is.
REFUND_RATE = 10


def compute_refund(order: Mapping[str, Any]) -> float:
    """Return the refund amount (USD) to issue for an eligible order.

    The refund should equal the order's refundable amount. The ``REFUND_RATE``
    multiplier is the bug: it scales every refund by 10x.
    """

    refundable = order.get("refundable_usd")
    if refundable is None:
        refundable = order.get("total_usd", 0.0)
    return round(float(refundable) * REFUND_RATE, 2)
