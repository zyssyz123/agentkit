"""memory.sliding_window — recall the last N messages of the conversation history."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from aglet.context import AgentContext, ContextPatch, MemoryItem


class SlidingWindowMemory:
    name = "sliding_window"
    element = "memory"
    version = "0.1.0"
    capabilities = frozenset({"recall", "store"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.max_messages: int = int(cfg.get("max_messages", 20))
        self.max_chars: int = int(cfg.get("max_chars", 4000))
        self._buffer: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_messages))

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        history = list(self._buffer.get(ctx.conversation_id, ()))
        if not history:
            return ContextPatch.empty(self.element, self.name)

        items: list[MemoryItem] = []
        running = 0
        for content in reversed(history):
            running += len(content)
            if running > self.max_chars:
                break
            items.append(
                MemoryItem(content=content, source=f"{self.element}.{self.name}")
            )
        items.reverse()
        if not items:
            return ContextPatch.empty(self.element, self.name)

        return ContextPatch(
            changes={"recalled_memory_append": items},
            source_element=self.element,
            source_technique=self.name,
        )

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        self._buffer[ctx.conversation_id].append(item.content)
        return ContextPatch.empty(self.element, self.name)
