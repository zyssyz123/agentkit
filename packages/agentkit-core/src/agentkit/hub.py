"""ElementHost (one Element, many Techniques) + ElementHub (all Elements)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agentkit.context import AgentContext, ContextPatch, MemoryItem, ToolCall, ToolResult, ToolSpec
from agentkit.events import Event
from agentkit.protocols import (
    ELEMENT_NAMES,
    ExecutorTechnique,
    MemoryTechnique,
    ObservabilityTechnique,
    OutputChunk,
    OutputTechnique,
    PerceptionTechnique,
    PlannerTechnique,
    SafetyTechnique,
    ToolHost,
    ToolTechnique,
)
from agentkit.routing import RoutingStrategy, get_strategy


# ---------- generic host -----------------------------------------------------------------------


@dataclass
class ElementHost:
    """Holds the active Techniques for a single Element + the routing strategy."""

    element: str
    techniques: list[Any] = field(default_factory=list)
    routing: RoutingStrategy = field(default_factory=lambda: get_strategy("all"))

    def add(self, technique: Any) -> None:
        self.techniques.append(technique)

    def __bool__(self) -> bool:
        return bool(self.techniques)


# ---------- specialised hosts (typed wrappers around ElementHost) -----------------------------


@dataclass
class PerceptionHost(ElementHost):
    async def parse(self, ctx: AgentContext) -> ContextPatch:
        async def call(t: PerceptionTechnique) -> ContextPatch:
            return await t.parse(ctx)

        result = await self.routing.dispatch(self.techniques, call, ctx)
        return result if isinstance(result, ContextPatch) else ContextPatch.empty()


@dataclass
class MemoryHost(ElementHost):
    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        async def call(t: MemoryTechnique) -> ContextPatch:
            return await t.recall(ctx, query)

        result = await self.routing.dispatch(self.techniques, call, ctx)
        return result if isinstance(result, ContextPatch) else ContextPatch.empty()

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        async def call(t: MemoryTechnique) -> ContextPatch:
            return await t.store(ctx, item)

        result = await self.routing.dispatch(self.techniques, call, ctx)
        return result if isinstance(result, ContextPatch) else ContextPatch.empty()


@dataclass
class PlannerHost(ElementHost):
    """Planners cannot be routed across multiple Techniques; pick the first one configured."""

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        if not self.techniques:
            return
        primary: PlannerTechnique = self.techniques[0]
        async for ev in primary.plan(ctx):
            yield ev


@dataclass
class ToolHostImpl(ElementHost):
    """Concrete ToolHost: aggregates ToolSpecs across Techniques and dispatches by qualified name."""

    async def list_tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for tech in self.techniques:
            spec_list = await tech.list()
            for spec in spec_list:
                # Re-stamp the technique attribution for clarity in traces.
                if spec.technique:
                    out.append(spec)
                else:
                    out.append(
                        ToolSpec(
                            name=spec.name,
                            description=spec.description,
                            parameters_schema=spec.parameters_schema,
                            technique=tech.name,
                        )
                    )
        return out

    async def invoke_tool(self, call: ToolCall) -> ToolResult:
        for tech in self.techniques:
            for spec in await tech.list():
                if spec.name == call.name:
                    return await tech.invoke(call.name, call.arguments)
        return ToolResult(
            call_id=call.id,
            output=None,
            error=f"No Tool Technique exposes tool '{call.name}'",
        )


@dataclass
class ExecutorHost(ElementHost):
    async def run(self, ctx: AgentContext, tools: ToolHost) -> AsyncIterator[Event]:
        if not self.techniques:
            return
        primary: ExecutorTechnique = self.techniques[0]
        async for ev in primary.run(ctx, tools):
            yield ev


@dataclass
class SafetyHost(ElementHost):
    async def pre_check(self, ctx: AgentContext) -> None:
        for t in self.techniques:
            await t.pre_check(ctx)

    async def post_check(self, ctx: AgentContext) -> None:
        for t in self.techniques:
            await t.post_check(ctx)

    async def wrap_tool(self, call: ToolCall) -> ToolCall:
        for t in self.techniques:
            call = await t.wrap_tool(call)
        return call


@dataclass
class OutputHost(ElementHost):
    async def format(self, ctx: AgentContext) -> AsyncIterator[OutputChunk]:
        for t in self.techniques:
            async for chunk in t.format(ctx):
                yield chunk


@dataclass
class ObservabilityHost(ElementHost):
    async def on_event(self, event: Event) -> None:
        for t in self.techniques:
            try:
                await t.on_event(event)
            except Exception:  # noqa: BLE001
                continue


# ---------- Hub --------------------------------------------------------------------------------


@dataclass
class ElementHub:
    """Container for all ElementHosts in a single Agent. Built by the Runtime from config."""

    perception: PerceptionHost = field(default_factory=lambda: PerceptionHost("perception"))
    memory: MemoryHost = field(default_factory=lambda: MemoryHost("memory"))
    planner: PlannerHost = field(default_factory=lambda: PlannerHost("planner"))
    tool: ToolHostImpl = field(default_factory=lambda: ToolHostImpl("tool"))
    executor: ExecutorHost = field(default_factory=lambda: ExecutorHost("executor"))
    safety: SafetyHost = field(default_factory=lambda: SafetyHost("safety"))
    output: OutputHost = field(default_factory=lambda: OutputHost("output"))
    observability: ObservabilityHost = field(
        default_factory=lambda: ObservabilityHost("observability")
    )
    custom: dict[str, ElementHost] = field(default_factory=dict)

    def get(self, element: str) -> ElementHost:
        if element in ELEMENT_NAMES:
            return getattr(self, element if element != "tool" else "tool")
        if element in self.custom:
            return self.custom[element]
        raise KeyError(f"Unknown element '{element}'")

    def all_hosts(self) -> list[ElementHost]:
        builtins: list[ElementHost] = [
            self.perception,
            self.memory,
            self.planner,
            self.tool,
            self.executor,
            self.safety,
            self.output,
            self.observability,
        ]
        return [*builtins, *self.custom.values()]


# Re-export RoutingStrategy for ergonomic imports.
__all__ = [
    "ElementHub",
    "ElementHost",
    "PerceptionHost",
    "MemoryHost",
    "PlannerHost",
    "ToolHostImpl",
    "ExecutorHost",
    "SafetyHost",
    "OutputHost",
    "ObservabilityHost",
    "RoutingStrategy",
]
