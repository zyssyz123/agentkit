"""Executor Element — run a Plan's next action(s) against the Tool host."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from agentkit.context import AgentContext, ToolCall, ToolResult, ToolSpec
from agentkit.events import Event


@runtime_checkable
class ToolHost(Protocol):
    """Minimal interface the Executor uses to talk to the Tool ElementHost."""

    async def list_tools(self) -> list[ToolSpec]: ...

    async def invoke_tool(self, call: ToolCall) -> ToolResult: ...


@runtime_checkable
class ExecutorTechnique(Protocol):
    name: str
    element: str = "executor"
    capabilities: frozenset[str]

    async def run(self, ctx: AgentContext, tools: ToolHost) -> AsyncIterator[Event]:
        """Stream Events while executing ctx.plan.next_action (and any sub-actions)."""
        ...
