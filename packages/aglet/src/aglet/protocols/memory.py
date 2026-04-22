"""Memory Element — recall and store across short / long term layers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aglet.context import AgentContext, ContextPatch, MemoryItem


@runtime_checkable
class MemoryTechnique(Protocol):
    name: str
    element: str = "memory"
    capabilities: frozenset[str]

    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        """Return a patch appending recalled items to ctx.recalled_memory."""
        ...

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        """Persist a memory item; may be a no-op for ephemeral techniques."""
        ...
