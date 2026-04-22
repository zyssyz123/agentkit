"""Safety Element — pre/post checks and tool-call wrapping."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aglet.context import AgentContext, ToolCall


@runtime_checkable
class SafetyTechnique(Protocol):
    name: str
    element: str = "safety"
    capabilities: frozenset[str]

    async def pre_check(self, ctx: AgentContext) -> None:
        """Inspect inputs/state before each Planner step. Raise on violation."""
        ...

    async def post_check(self, ctx: AgentContext) -> None:
        """Inspect outputs after each Planner/Executor step. Raise on violation."""
        ...

    async def wrap_tool(self, call: ToolCall) -> ToolCall:
        """Optionally rewrite a tool call (e.g. mask PII). Default: return unchanged."""
        ...
