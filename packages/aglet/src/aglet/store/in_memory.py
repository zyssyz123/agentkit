"""In-memory ContextStore — default for unit tests and ephemeral runs."""

from __future__ import annotations

from collections import defaultdict

from aglet.context import AgentContext, ContextPatch
from aglet.events import Event


class InMemoryContextStore:
    def __init__(self) -> None:
        self._patches: dict[str, list[ContextPatch]] = defaultdict(list)
        self._events: dict[str, list[Event]] = defaultdict(list)

    async def append_patch(self, run_id: str, patch: ContextPatch) -> None:
        self._patches[run_id].append(patch)

    async def append_event(self, run_id: str, event: Event) -> None:
        self._events[run_id].append(event)

    async def load_patches(self, run_id: str) -> list[ContextPatch]:
        return list(self._patches[run_id])

    async def load_events(self, run_id: str) -> list[Event]:
        return list(self._events[run_id])

    async def rebuild(self, run_id: str, base: AgentContext) -> AgentContext:
        ctx = base
        for patch in self._patches[run_id]:
            ctx = patch.apply_to(ctx)
        return ctx

    async def list_runs(self) -> list[str]:
        return sorted(self._patches.keys() | self._events.keys())

    async def has_run(self, run_id: str) -> bool:
        return run_id in self._patches or run_id in self._events

    def events(self, run_id: str) -> list[Event]:
        return list(self._events[run_id])
