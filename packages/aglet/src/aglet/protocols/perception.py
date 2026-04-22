"""Perception Element — turn raw input into a structured ParsedInput."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aglet.context import AgentContext, ContextPatch


@runtime_checkable
class PerceptionTechnique(Protocol):
    name: str
    element: str = "perception"
    capabilities: frozenset[str]

    async def parse(self, ctx: AgentContext) -> ContextPatch:
        """Read ctx.raw_input; return a patch typically setting parsed_input."""
        ...
