"""safety.budget_only — minimal Safety Technique.

Budget enforcement already happens inside the Runtime (the unbypassable layer).
This Technique is provided so users can declare ``safety: [{name: budget_only}]`` in YAML
without pulling in heavier moderation dependencies.
"""

from __future__ import annotations

from typing import Any

from aglet.budget import BudgetExceededError
from aglet.context import AgentContext, ToolCall


class BudgetSafety:
    name = "budget_only"
    element = "safety"
    version = "0.1.0"
    capabilities = frozenset({"pre_check", "post_check"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def pre_check(self, ctx: AgentContext) -> None:
        if ctx.budget.exceeded():
            raise BudgetExceededError("Budget exceeded before planner step")

    async def post_check(self, ctx: AgentContext) -> None:
        if ctx.budget.exceeded():
            raise BudgetExceededError("Budget exceeded after executor step")

    async def wrap_tool(self, call: ToolCall) -> ToolCall:
        return call
