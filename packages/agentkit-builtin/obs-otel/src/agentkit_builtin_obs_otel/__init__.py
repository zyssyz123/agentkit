"""observability.otel — emit AgentKit Events as OpenTelemetry spans.

We model an entire agent run as a tree:

* one root span per ``run.started`` … ``run.completed/failed`` pair
* per-element spans for perception/memory/planner/etc.
* per-tool-call spans for ``tool.call`` … ``tool.result`` pairs

Config schema::

    type: otel
    config:
      service_name: agentkit
      endpoint: http://localhost:4318/v1/traces
      headers: { "x-api-key": "${OTEL_KEY}" }
"""

from __future__ import annotations

import logging
from typing import Any

from agentkit.events import Event, EventType

log = logging.getLogger(__name__)


class OtelObservability:
    name = "otel"
    element = "observability"
    version = "0.1.0"
    capabilities = frozenset({"trace"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.service_name: str = cfg.get("service_name", "agentkit")
        self.endpoint: str = cfg.get("endpoint", "http://localhost:4318/v1/traces")
        self.headers: dict[str, str] = dict(cfg.get("headers", {}))

        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": self.service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=self.endpoint, headers=self.headers or None)
            )
        )
        # Don't override an existing global provider if the host application set one.
        try:
            trace.set_tracer_provider(provider)
        except Exception:  # noqa: BLE001
            pass
        self._tracer = trace.get_tracer("agentkit", "0.1.0")
        self._spans: dict[str, Any] = {}  # run_id -> root Span
        self._tool_spans: dict[str, Any] = {}  # call_id -> Span

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    # ------------------------------------------------------------------

    async def on_event(self, event: Event) -> None:
        run_id = ""
        if isinstance(event.payload, dict):
            run_id = str(event.payload.get("run_id", ""))

        if event.type == EventType.RUN_STARTED:
            span = self._tracer.start_span(name="agentkit.run", attributes={"run.id": run_id})
            self._spans[run_id] = span
            return

        if event.type in (
            EventType.RUN_COMPLETED,
            EventType.RUN_FAILED,
            EventType.RUN_CANCELLED,
        ):
            span = self._spans.pop(run_id, None)
            if span is not None:
                span.set_attribute("run.outcome", event.type.value)
                span.end()
            return

        # Tool call/result correlation
        if event.type == EventType.TOOL_CALL:
            payload = event.payload if isinstance(event.payload, dict) else {}
            call = payload.get("call", {})
            child = self._tracer.start_span(
                name=f"tool.{call.get('name','?')}",
                attributes={
                    "tool.name": call.get("name", ""),
                    "tool.args": str(call.get("args", "")),
                    "run.id": run_id,
                },
            )
            self._tool_spans[call.get("id", "")] = child
            return

        if event.type in (EventType.TOOL_RESULT, EventType.TOOL_ERROR):
            payload = event.payload if isinstance(event.payload, dict) else {}
            call_id = payload.get("call_id", "")
            child = self._tool_spans.pop(call_id, None)
            if child is not None:
                child.set_attribute("tool.latency_ms", int(payload.get("latency_ms", 0)))
                if event.type == EventType.TOOL_ERROR:
                    child.set_attribute("error", payload.get("error", "") or "")
                child.end()
            return

        # Other events: emit as point-in-time events on the root span.
        root = self._spans.get(run_id)
        if root is not None:
            try:
                root.add_event(event.type.value, attributes=_safe_attrs(event.payload))
            except Exception:  # noqa: BLE001
                pass


def _safe_attrs(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, (str, int, float, bool)):
            out[str(k)] = v
        else:
            out[str(k)] = str(v)
    return out
