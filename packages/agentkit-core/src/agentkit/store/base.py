"""ContextStore protocol — append-only patch log per run, replayable into a context."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentkit.context import AgentContext, ContextPatch
from agentkit.events import Event


@runtime_checkable
class ContextStore(Protocol):
    async def append_patch(self, run_id: str, patch: ContextPatch) -> None: ...

    async def append_event(self, run_id: str, event: Event) -> None: ...

    async def load_patches(self, run_id: str) -> list[ContextPatch]: ...

    async def load_events(self, run_id: str) -> list[Event]: ...

    async def rebuild(self, run_id: str, base: AgentContext) -> AgentContext: ...

    async def list_runs(self) -> list[str]: ...

    async def has_run(self, run_id: str) -> bool: ...
