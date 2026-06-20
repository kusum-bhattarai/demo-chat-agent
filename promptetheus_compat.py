"""Promptetheus SDK shim.

Prefer the real SDK (it proves the SDK is agent-agnostic). If it isn't installed
yet — e.g. you're building the demo before pulling the SDK from its separate
repo — fall back to a tiny local recorder that mirrors the documented API so the
chat UI and the in-memory event verification still work.

Install the real SDK with:
    pip install "git+https://github.com/obro79/promptetheus-hackathon.git@main#subdirectory=packages/promptetheus"

Whichever path is active, ``USING_REAL_SDK`` tells you, so the demo can show it
on screen and never surprise you on stage.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:  # The real thing, from the backend repo.
    from promptetheus import trace  # type: ignore
    from promptetheus.transport import InMemoryTransport  # type: ignore

    USING_REAL_SDK = True

except ModuleNotFoundError:  # Local fallback — same surface, no network dep.
    USING_REAL_SDK = False

    class InMemoryTransport:  # noqa: D401 - mirrors the real transport
        """Captures emitted events in ``self.events`` (list of dicts)."""

        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []

    class _Session:
        """Minimal stand-in for the SDK session. Records typed events."""

        def __init__(self, transport: Any, endpoint: str | None, api_key: str | None) -> None:
            self._transport = transport
            self._endpoint = endpoint
            self._api_key = api_key

        def _emit(self, type: str, **payload: Any) -> None:
            event = {"type": type, **payload}
            if self._transport is not None and hasattr(self._transport, "events"):
                self._transport.events.append(event)
            # HTTP posting in fallback mode is intentionally a no-op: the real
            # ingestion shape lives in the SDK. Install it for the live demo.

        def user_message(self, content: str) -> None:
            self._emit("user_message", content=content)

        def agent_message(self, content: str) -> None:
            self._emit("agent_message", content=content)

        def retrieval(self, query: str, documents: list[Any], metadata: Any = None) -> None:
            self._emit("retrieval", query=query, documents=documents, metadata=metadata)

        def tool_call(self, tool_name: str, arguments: Any, call_id: str) -> None:
            self._emit("tool_call", tool_name=tool_name, arguments=arguments, call_id=call_id)

        def tool_result(self, call_id: str, result: Any = None, error: Any = None) -> None:
            self._emit("tool_result", call_id=call_id, result=result, error=error)

        def goal_check(self, passed: bool, mismatches: list[str] | None = None) -> None:
            self._emit("goal_check", passed=passed, mismatches=mismatches or [])

        def end(self, status: str) -> None:
            self._emit("session_end", status=status)

    class _Trace:
        @staticmethod
        @contextmanager
        def start(
            *,
            transport: Any = None,
            endpoint: str | None = None,
            api_key: str | None = None,
            **_meta: Any,
        ) -> Iterator[_Session]:
            transport_obj = None if isinstance(transport, str) else transport
            session = _Session(transport_obj, endpoint, api_key)
            yield session

    trace = _Trace()  # type: ignore


__all__ = ["trace", "InMemoryTransport", "USING_REAL_SDK"]
