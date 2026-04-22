"""observability.jsonl — append every Event to <directory>/<run_id>.events.jsonl.

Note: this Technique is independent of the JsonlContextStore. The store keeps
*both* events and patches; this Observability Technique gives users an extra,
focused per-event file when they only want events (e.g. for log shipping).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anyio

from agentkit.events import Event


class JsonlObservability:
    name = "jsonl"
    element = "observability"
    version = "0.1.0"
    capabilities = frozenset({"trace"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.directory = Path(cfg.get("directory", ".agentkit/runs"))
        self.directory.mkdir(parents=True, exist_ok=True)

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def on_event(self, event: Event) -> None:
        run_id = ""
        if isinstance(event.payload, dict):
            run_id = str(event.payload.get("run_id", ""))
        path = self.directory / f"{run_id or 'unknown'}.events.jsonl"
        line = json.dumps(event.to_dict(), ensure_ascii=False)

        def _append() -> None:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

        await anyio.to_thread.run_sync(_append)
