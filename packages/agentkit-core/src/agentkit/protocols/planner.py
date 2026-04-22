"""Planner Element — produce thoughts and decide the next action / final answer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from agentkit.context import AgentContext
from agentkit.events import Event


@runtime_checkable
class PlannerTechnique(Protocol):
    name: str
    element: str = "planner"
    capabilities: frozenset[str]

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        """Stream Events. Each Event may carry a ContextPatch the Runtime applies.

        Typical sequence: PLANNER_THOUGHT* -> (PLANNER_ACTION | PLANNER_FINAL).
        The Planner is responsible for setting ``Plan.next_action`` (to invoke a tool)
        or ``Plan.final_answer`` (to terminate the loop) via patches on the emitted events.
        """
        ...
