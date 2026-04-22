"""observability.console — print every Event to stdout, one line each."""

from __future__ import annotations

import json
import sys
from typing import Any

from agentkit.events import Event


class ConsoleObservability:
    name = "console"
    element = "observability"
    version = "0.1.0"
    capabilities = frozenset({"trace"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.compact: bool = bool(cfg.get("compact", True))

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def on_event(self, event: Event) -> None:
        if self.compact:
            line = f"[{event.ts.strftime('%H:%M:%S')}] {event.type.value:24s}"
            if event.element:
                line += f" element={event.element}"
            if event.technique:
                line += f" technique={event.technique}"
            if event.payload:
                summary = json.dumps(event.payload, default=str, ensure_ascii=False)
                if len(summary) > 200:
                    summary = summary[:197] + "..."
                line += f" payload={summary}"
            print(line, file=sys.stdout, flush=True)
        else:
            print(json.dumps(event.to_dict(), ensure_ascii=False), file=sys.stdout, flush=True)
