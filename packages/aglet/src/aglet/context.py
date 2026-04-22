"""Immutable AgentContext + ContextPatch.

`AgentContext` is the single data contract that flows through every Element call.
Components never mutate it directly; they return `ContextPatch` objects which the
Runtime applies. This gives us free event-sourcing, replay and parallel-safe execution.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Literal

from aglet.budget import Budget


# ---------- atomic value types ----------------------------------------------------------------


@dataclass(frozen=True)
class RawInput:
    """User-provided raw input. May contain text plus references to attachments."""

    text: str = ""
    attachments: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedInput:
    """Output of the Perception Element."""

    query: str = ""
    intent: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    embeddings: tuple[float, ...] | None = None


@dataclass(frozen=True)
class Message:
    """A single chat message in conversation history."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class MemoryItem:
    """An item recalled from or stored to memory."""

    content: str
    source: str  # which Technique produced it (e.g. "memory.rag")
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Thought:
    """A single ReAct/CoT thought emitted by a Planner Technique."""

    content: str
    technique: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Public description of a callable tool."""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    technique: str = ""  # which Tool Technique exposed it


@dataclass(frozen=True)
class ToolCall:
    """A pending or executed tool invocation."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a single ToolCall."""

    call_id: str
    output: Any
    error: str | None = None
    latency_ms: int = 0


@dataclass(frozen=True)
class Plan:
    """The Planner's current plan for the run."""

    next_action: ToolCall | None = None  # if set, Executor should run it next iteration
    final_answer: str | None = None  # if set, planner is done
    reasoning: str = ""

    def is_done(self) -> bool:
        return self.final_answer is not None


# ---------- AgentContext + ContextPatch ------------------------------------------------------


@dataclass(frozen=True)
class AgentContext:
    """Immutable snapshot threaded through one Agent run.

    All fields are immutable (tuple / frozen dataclass / primitives). Components
    return :class:`ContextPatch` objects describing partial updates; the Runtime
    applies them and emits an :class:`Event` for each.
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = ""
    user_id: str | None = None

    raw_input: RawInput = field(default_factory=RawInput)
    parsed_input: ParsedInput | None = None

    history: tuple[Message, ...] = ()
    recalled_memory: tuple[MemoryItem, ...] = ()

    scratchpad: tuple[Thought, ...] = ()
    plan: Plan | None = None

    available_tools: tuple[ToolSpec, ...] = ()
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()

    budget: Budget = field(default_factory=Budget)

    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ----- helpers ---------------------------------------------------------------------------

    def patch(self, **changes: Any) -> AgentContext:
        """Return a new context with the given fields replaced. Tuple fields auto-coerce."""
        normalized = {k: tuple(v) if isinstance(v, list) else v for k, v in changes.items()}
        return replace(self, **normalized)

    def append_history(self, *msgs: Message) -> AgentContext:
        return self.patch(history=self.history + tuple(msgs))

    def append_thought(self, thought: Thought) -> AgentContext:
        return self.patch(scratchpad=self.scratchpad + (thought,))

    def append_tool_call(self, call: ToolCall) -> AgentContext:
        return self.patch(tool_calls=self.tool_calls + (call,))

    def append_tool_result(self, result: ToolResult) -> AgentContext:
        return self.patch(tool_results=self.tool_results + (result,))


# ---------- ContextPatch ---------------------------------------------------------------------


@dataclass(frozen=True)
class ContextPatch:
    """A partial, attributable update to an AgentContext.

    `changes` is a flat dict of field-name -> new value. Tuple fields support an
    "append" shortcut via the special `_append` suffix, e.g. ``{"scratchpad_append": [t]}``.
    """

    changes: dict[str, Any] = field(default_factory=dict)
    source_element: str = ""
    source_technique: str = ""
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def apply_to(self, ctx: AgentContext) -> AgentContext:
        if not self.changes:
            return ctx
        replacements: dict[str, Any] = {}
        for key, value in self.changes.items():
            if key.endswith("_append"):
                target = key[: -len("_append")]
                current = getattr(ctx, target)
                if not isinstance(current, tuple):
                    raise TypeError(
                        f"ContextPatch field '{target}' is not a tuple; cannot _append"
                    )
                replacements[target] = current + tuple(value)
            else:
                replacements[key] = tuple(value) if isinstance(value, list) else value
        return replace(ctx, **replacements)

    @staticmethod
    def empty(element: str = "", technique: str = "") -> ContextPatch:
        return ContextPatch(changes={}, source_element=element, source_technique=technique)
