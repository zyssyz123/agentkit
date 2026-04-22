"""perception.passthrough — copy ctx.raw_input.text -> ctx.parsed_input.query."""

from __future__ import annotations

from typing import Any

from agentkit.context import AgentContext, ContextPatch, ParsedInput


class PassthroughPerception:
    name = "passthrough"
    element = "perception"
    version = "0.1.0"
    capabilities = frozenset({"parse"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    async def setup(self, ctx) -> None:  # noqa: D401, ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def parse(self, ctx: AgentContext) -> ContextPatch:
        parsed = ParsedInput(query=ctx.raw_input.text)
        return ContextPatch(
            changes={"parsed_input": parsed},
            source_element=self.element,
            source_technique=self.name,
        )
