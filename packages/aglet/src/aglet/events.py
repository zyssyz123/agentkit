"""Event + EventBus.

Every Element invocation, Technique execution and Tool call emits an Event.
The Runtime publishes events on the bus; Observability Techniques subscribe and
ship them to OTel/JSONL/LangFuse/etc.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from aglet.context import ContextPatch


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"

    PERCEPTION_DONE = "perception.done"
    MEMORY_RECALLED = "memory.recalled"
    MEMORY_STORED = "memory.stored"

    PLANNER_THOUGHT = "planner.thought"
    PLANNER_ACTION = "planner.action"
    PLANNER_FINAL = "planner.final"

    EXECUTOR_STEP = "executor.step"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    TOOL_ERROR = "tool.error"

    SAFETY_ALERT = "safety.alert"
    SAFETY_BLOCKED = "safety.blocked"

    OUTPUT_CHUNK = "output.chunk"
    OUTPUT_END = "output.end"

    LIFECYCLE = "lifecycle"


EventHandler = Callable[["Event"], Awaitable[None]]


@dataclass(frozen=True)
class Event:
    type: EventType
    element: str = ""
    technique: str = ""
    payload: Any = None
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: str | None = None
    patch: ContextPatch | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "element": self.element,
            "technique": self.technique,
            "payload": _coerce(self.payload),
            "ts": self.ts.isoformat(),
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
        }


def _coerce(value: Any) -> Any:
    """Best-effort JSON coercion for arbitrary payloads."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _coerce(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_coerce(v) for v in value]
    if hasattr(value, "__dict__"):
        return {k: _coerce(v) for k, v in value.__dict__.items() if not k.startswith("_")}
    return repr(value)


class EventBus:
    """Async fan-out event bus.

    Each subscribed handler runs in its own task; failures are isolated per subscriber.
    """

    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        """Register a handler. Returns an unsubscribe callable."""
        self._subscribers.append(handler)

        def _unsubscribe() -> None:
            try:
                self._subscribers.remove(handler)
            except ValueError:
                pass

        return _unsubscribe

    async def emit(self, event: Event) -> None:
        if not self._subscribers:
            return
        results = await asyncio.gather(
            *(self._safe_call(h, event) for h in list(self._subscribers)),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                # Subscribers must not break the run; we swallow but could log here.
                pass

    @staticmethod
    async def _safe_call(handler: EventHandler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:  # noqa: BLE001 — isolate subscriber failures
            return
