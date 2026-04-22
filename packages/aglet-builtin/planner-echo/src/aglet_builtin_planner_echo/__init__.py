"""planner.echo — deterministic, zero-dependency planner for the M1 echo-agent example.

Given any input it produces:
  Thought:  "Echoing back the user's input."
  Final:    f"{prefix}{ctx.parsed_input.query}{suffix}"

This is intentionally a non-LLM planner so the M1 skeleton runs without external services.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from aglet.context import AgentContext, ContextPatch, Plan, Thought
from aglet.events import Event, EventType


class EchoPlanner:
    name = "echo"
    element = "planner"
    version = "0.1.0"
    capabilities = frozenset({"plan"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.prefix: str = cfg.get("prefix", "")
        self.suffix: str = cfg.get("suffix", "")
        self.thought_template: str = cfg.get(
            "thought_template", "Echoing back the user's input."
        )

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        thought = Thought(content=self.thought_template, technique=self.name)
        yield Event(
            type=EventType.PLANNER_THOUGHT,
            element=self.element,
            technique=self.name,
            payload={"thought": thought.content},
            patch=ContextPatch(
                changes={"scratchpad_append": [thought]},
                source_element=self.element,
                source_technique=self.name,
            ),
        )

        query = ctx.parsed_input.query if ctx.parsed_input else ctx.raw_input.text
        final = f"{self.prefix}{query}{self.suffix}"
        plan = Plan(final_answer=final, reasoning=thought.content)

        yield Event(
            type=EventType.PLANNER_FINAL,
            element=self.element,
            technique=self.name,
            payload={"final": final},
            patch=ContextPatch(
                changes={"plan": plan},
                source_element=self.element,
                source_technique=self.name,
            ),
        )
