"""Observability Element — receive every Event from the Runtime."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentkit.events import Event


@runtime_checkable
class ObservabilityTechnique(Protocol):
    name: str
    element: str = "observability"
    capabilities: frozenset[str]

    async def on_event(self, event: Event) -> None:
        """Called for every Event the Runtime emits. Must not raise."""
        ...
