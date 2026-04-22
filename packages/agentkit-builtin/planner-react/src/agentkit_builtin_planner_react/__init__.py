"""planner.react — function-calling ReAct planner backed by any ModelProvider.

Each ``plan(ctx)`` call performs **one round** of LLM reasoning:

* Builds a chat-history prompt from ``ctx.history`` + a system prompt + observations
  (synthesised from ``ctx.tool_results``).
* Asks the model to either (a) issue a tool call, or (b) emit a final answer.
* Yields a PLANNER_THOUGHT and either a PLANNER_ACTION (with ``Plan.next_action`` set)
  or a PLANNER_FINAL (with ``Plan.final_answer`` set).

The Runtime drives the outer loop, applies tool results back into the context and
re-invokes ``plan()`` until ``Plan.is_done()``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from agentkit.context import (
    AgentContext,
    ContextPatch,
    Message,
    Plan,
    Thought,
    ToolCall,
)
from agentkit.events import Event, EventType
from agentkit.models import ModelHub, ModelMessage, ModelToolCall

DEFAULT_SYSTEM_PROMPT = """You are an AI agent. You can either:
- Call one of the available tools to gather information, OR
- Produce the final answer to the user.

Be concise. Only call tools when needed."""


class ReactPlanner:
    name = "react"
    element = "planner"
    version = "0.1.0"
    capabilities = frozenset({"plan", "tool_use"})

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        models: ModelHub | None = None,
    ) -> None:
        cfg = config or {}
        self.model_alias: str = cfg.get("model", "default")
        self.system_prompt: str = cfg.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        self.temperature: float = float(cfg.get("temperature", 0.2))
        self.max_tokens: int | None = cfg.get("max_tokens")
        self._models = models  # injected by Runtime via _instantiate_technique

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=self._models is not None)

    # ------------------------------------------------------------------

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        if self._models is None:
            yield _final(
                "ReactPlanner is not bound to a ModelHub. Did you forget the `providers:` "
                "block in agent.yaml?",
                self.name,
            )
            return

        provider, model_id = self._models.resolve(self.model_alias)
        messages = self._build_messages(ctx)
        tools_payload = self._build_tools(ctx)

        response = await provider.complete(
            model=model_id,
            messages=messages,
            tools=tools_payload or None,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Always emit a thought event capturing the model's reasoning text (if any).
        if response.content:
            thought = Thought(content=response.content, technique=self.name)
            yield Event(
                type=EventType.PLANNER_THOUGHT,
                element=self.element,
                technique=self.name,
                payload={"thought": thought.content, "usage": response.usage},
                patch=ContextPatch(
                    changes={"scratchpad_append": [thought]},
                    source_element=self.element,
                    source_technique=self.name,
                ),
            )

        if response.tool_calls:
            tc = response.tool_calls[0]  # M2: single-tool ReAct; multi-tool dispatch is M4.
            call = ToolCall(id=tc.id or "", name=tc.name, arguments=tc.arguments)
            new_plan = Plan(next_action=call, reasoning=response.content)
            yield Event(
                type=EventType.PLANNER_ACTION,
                element=self.element,
                technique=self.name,
                payload={"name": call.name, "arguments": call.arguments},
                patch=ContextPatch(
                    changes={"plan": new_plan},
                    source_element=self.element,
                    source_technique=self.name,
                ),
            )
            return

        # No tool call → final answer.
        yield _final(response.content or "(no answer)", self.name)

    # ------------------------------------------------------------------

    def _build_messages(self, ctx: AgentContext) -> list[ModelMessage]:
        msgs: list[ModelMessage] = [ModelMessage(role="system", content=self.system_prompt)]

        # Inject recalled memory (RAG hits, summaries, episodic, …) as a system
        # message so the model can ground its answer in retrieved context.
        if ctx.recalled_memory:
            joined = "\n".join(
                f"- ({item.source}) {item.content}" for item in ctx.recalled_memory
            )
            msgs.append(
                ModelMessage(
                    role="system",
                    content=f"Relevant context retrieved from memory:\n{joined}",
                )
            )

        # Conversation history (user + assistant messages from previous turns).
        for m in ctx.history:
            msgs.append(ModelMessage(role=m.role, content=m.content, name=m.name))

        # Replay this turn's tool round-trips so the model sees its own previous calls
        # and the resulting observations. The assistant message MUST carry tool_calls
        # so the provider can correlate tool_call_id on the subsequent tool message.
        results_by_id = {r.call_id: r for r in ctx.tool_results}
        for call in ctx.tool_calls:
            msgs.append(
                ModelMessage(
                    role="assistant",
                    content="",
                    tool_calls=(
                        ModelToolCall(id=call.id, name=call.name, arguments=call.arguments),
                    ),
                )
            )
            result = results_by_id.get(call.id)
            if result is not None:
                payload = result.output if result.error is None else f"ERROR: {result.error}"
                content = (
                    payload if isinstance(payload, str) else json.dumps(payload, default=str)
                )
                msgs.append(
                    ModelMessage(
                        role="tool",
                        content=content,
                        tool_call_id=call.id,
                    )
                )
        return msgs

    @staticmethod
    def _build_tools(ctx: AgentContext) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters_schema,
                },
            }
            for spec in ctx.available_tools
        ]


def _final(text: str, technique: str) -> Event:
    plan = Plan(final_answer=text)
    return Event(
        type=EventType.PLANNER_FINAL,
        element="planner",
        technique=technique,
        payload={"final": text},
        patch=ContextPatch(
            changes={"plan": plan},
            source_element="planner",
            source_technique=technique,
        ),
    )
