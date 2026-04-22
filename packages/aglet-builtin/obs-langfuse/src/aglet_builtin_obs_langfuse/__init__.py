"""observability.langfuse — ship every Aglet run as a LangFuse trace.

Config schema::

    type: langfuse
    config:
      public_key: ${LANGFUSE_PUBLIC_KEY}
      secret_key: ${LANGFUSE_SECRET_KEY}
      host: https://cloud.langfuse.com
"""

from __future__ import annotations

import logging
import os
from typing import Any

from aglet.events import Event, EventType

log = logging.getLogger(__name__)


def _resolve(value: str) -> str:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


class LangfuseObservability:
    name = "langfuse"
    element = "observability"
    version = "0.1.0"
    capabilities = frozenset({"trace"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=_resolve(cfg.get("public_key", "${LANGFUSE_PUBLIC_KEY}")),
            secret_key=_resolve(cfg.get("secret_key", "${LANGFUSE_SECRET_KEY}")),
            host=cfg.get("host", "https://cloud.langfuse.com"),
        )
        self._traces: dict[str, Any] = {}
        self._spans: dict[str, Any] = {}  # call_id -> span

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        try:
            self._client.flush()
        except Exception:  # noqa: BLE001
            pass

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def on_event(self, event: Event) -> None:
        run_id = ""
        if isinstance(event.payload, dict):
            run_id = str(event.payload.get("run_id", ""))

        try:
            if event.type == EventType.RUN_STARTED:
                self._traces[run_id] = self._client.trace(
                    name="aglet.run", id=run_id, metadata={"runtime": "aglet"}
                )
                return

            if event.type in (
                EventType.RUN_COMPLETED,
                EventType.RUN_FAILED,
                EventType.RUN_CANCELLED,
            ):
                trace = self._traces.pop(run_id, None)
                if trace is not None:
                    trace.update(output=event.payload, status_message=event.type.value)
                return

            trace = self._traces.get(run_id)
            if trace is None:
                return

            if event.type == EventType.TOOL_CALL:
                payload = event.payload if isinstance(event.payload, dict) else {}
                call = payload.get("call", {})
                span = trace.span(
                    name=f"tool.{call.get('name','?')}",
                    input=call.get("args"),
                )
                self._spans[call.get("id", "")] = span
                return

            if event.type in (EventType.TOOL_RESULT, EventType.TOOL_ERROR):
                payload = event.payload if isinstance(event.payload, dict) else {}
                span = self._spans.pop(payload.get("call_id", ""), None)
                if span is not None:
                    span.end(
                        output=payload.get("output"),
                        status_message=payload.get("error") or "ok",
                    )
                return

            # Other events become observation events on the trace.
            trace.event(name=event.type.value, input=event.payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("LangFuse observability failed: %s", exc)
