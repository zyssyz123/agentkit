"""Output Element — render the final ctx into user-facing chunks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from aglet.context import AgentContext


@dataclass(frozen=True)
class OutputChunk:
    text: str = ""
    kind: Literal["text", "citation", "suggestion", "metadata"] = "text"
    extra: dict[str, Any] | None = None


@runtime_checkable
class OutputTechnique(Protocol):
    name: str
    element: str = "output"
    capabilities: frozenset[str]

    async def format(self, ctx: AgentContext) -> AsyncIterator[OutputChunk]:
        """Stream OutputChunks. The Runtime concatenates / forwards them to the client."""
        ...
