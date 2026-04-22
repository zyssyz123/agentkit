"""executor.sequential — invoke the planner's next_action through the ToolHost."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from aglet.context import AgentContext, ContextPatch, ToolCall, ToolResult
from aglet.events import Event, EventType
from aglet.protocols import ToolHost


class SequentialExecutor:
    name = "sequential"
    element = "executor"
    version = "0.1.0"
    capabilities = frozenset({"run"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def run(self, ctx: AgentContext, tools: ToolHost) -> AsyncIterator[Event]:
        if not ctx.plan or ctx.plan.next_action is None:
            return

        call: ToolCall = ctx.plan.next_action
        if not call.id:
            call = replace(call, id=str(uuid.uuid4()))

        yield Event(
            type=EventType.TOOL_CALL,
            element=self.element,
            technique=self.name,
            payload={"call": {"id": call.id, "name": call.name, "args": call.arguments}},
            patch=ContextPatch(
                changes={"tool_calls_append": [call]},
                source_element=self.element,
                source_technique=self.name,
            ),
        )

        result: ToolResult = await tools.invoke_tool(call)
        result = replace(result, call_id=call.id)

        # Clear the next_action so the planner moves on next iteration.
        new_plan = replace(ctx.plan, next_action=None)

        yield Event(
            type=EventType.TOOL_RESULT if result.error is None else EventType.TOOL_ERROR,
            element=self.element,
            technique=self.name,
            payload={
                "call_id": call.id,
                "output": result.output,
                "error": result.error,
                "latency_ms": result.latency_ms,
            },
            patch=ContextPatch(
                changes={"tool_results_append": [result], "plan": new_plan},
                source_element=self.element,
                source_technique=self.name,
            ),
        )
