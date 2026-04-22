"""output.streaming_text — chunk the final answer into N-character pieces and stream them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agentkit.context import AgentContext
from agentkit.protocols import OutputChunk


class StreamingTextOutput:
    name = "streaming_text"
    element = "output"
    version = "0.1.0"
    capabilities = frozenset({"format"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.chunk_size: int = int(cfg.get("chunk_size", 16))

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def format(self, ctx: AgentContext) -> AsyncIterator[OutputChunk]:
        text = (ctx.plan.final_answer if ctx.plan else None) or ""
        if not text:
            return
        for i in range(0, len(text), self.chunk_size):
            yield OutputChunk(text=text[i : i + self.chunk_size])
