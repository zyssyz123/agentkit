"""Tool Element — expose callable tools and execute invocations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aglet.context import ToolResult, ToolSpec


@runtime_checkable
class ToolTechnique(Protocol):
    name: str
    element: str = "tool"
    capabilities: frozenset[str]

    async def list(self) -> list[ToolSpec]:
        """Return the tools this Technique exposes (e.g. local Python funcs, MCP tools, OpenAPI)."""
        ...

    async def invoke(self, name: str, arguments: dict) -> ToolResult:
        """Invoke one of this Technique's tools by qualified name."""
        ...
