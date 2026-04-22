"""Default Agent Runtime — the canonical loop assembling all 9 Elements.

Responsibilities:

1. Build an :class:`agentkit.hub.ElementHub` from an :class:`agentkit.config.AgentConfig` and
   the global :class:`agentkit.registry.Registry`.
2. Drive the canonical Loop (perception -> recall -> [plan -> execute]* -> store -> output).
3. Apply :class:`ContextPatch` returned by Components, emit :class:`Event` on the bus and
   into the :class:`ContextStore`.
4. Enforce :class:`Budget`.

This Loop is replaceable by setting ``runtime.loop`` to a custom callable in code; the YAML
escape hatch arrives in M3.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from agentkit.budget import Budget, BudgetExceededError
from agentkit.config import AgentConfig
from agentkit.context import (
    AgentContext,
    ContextPatch,
    MemoryItem,
    Message,
    RawInput,
)
from agentkit.events import Event, EventBus, EventType
from agentkit.hub import (
    ElementHub,
    ExecutorHost,
    MemoryHost,
    ObservabilityHost,
    OutputHost,
    PerceptionHost,
    PlannerHost,
    SafetyHost,
    ToolHostImpl,
)
from agentkit.models import ModelHub
from agentkit.protocols import BootContext
from agentkit.registry import Registry, get_registry
from agentkit.routing import get_strategy
from agentkit.store import ContextStore, JsonlContextStore

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    """The default Agent Runtime."""

    hub: ElementHub
    bus: EventBus
    store: ContextStore
    config: AgentConfig
    models: ModelHub

    # ---------- factories ---------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        cfg: AgentConfig,
        registry: Registry | None = None,
        store: ContextStore | None = None,
    ) -> Runtime:
        registry = registry or get_registry()

        # Side-effect import any locally-declared plugin modules.
        if cfg.plugin_modules:
            registry.import_paths(cfg.plugin_modules)

        # Always discover entry points so installed packages register themselves.
        registry.discover_entry_points()

        models = _build_model_hub(cfg)
        hub = _build_hub(cfg, registry, models)
        bus = EventBus()

        if store is None:
            if cfg.store.type == "jsonl":
                store = JsonlContextStore(cfg.store.directory)
            else:
                from agentkit.store import InMemoryContextStore  # local to avoid cycles

                store = InMemoryContextStore()

        # Wire Observability Techniques to the bus + store automatically.
        async def _fan_out(ev: Event) -> None:
            await hub.observability.on_event(ev)
            await store.append_event(ev_run_id_from(ev), ev)

        bus.subscribe(_fan_out)

        return cls(hub=hub, bus=bus, store=store, config=cfg, models=models)

    # ---------- public API --------------------------------------------------------------------

    async def run(
        self,
        input_text: str,
        *,
        conversation_id: str = "",
        history: tuple[Message, ...] | list[Message] = (),
    ) -> AsyncIterator[Event]:
        """Run a single turn and stream all Events to the caller.

        Pass ``history`` to thread previous turns of a multi-turn conversation through
        ``ctx.history``; the new user message is appended automatically.
        """
        prior = tuple(history)
        ctx = AgentContext(
            conversation_id=conversation_id,
            raw_input=RawInput(text=input_text),
            budget=Budget(
                max_steps=self.config.budget.max_steps,
                max_tokens=self.config.budget.max_tokens,
                max_seconds=self.config.budget.max_seconds,
                max_cost_usd=self.config.budget.max_cost_usd,
            ),
            history=prior + (Message(role="user", content=input_text),),
        )
        async for ev in self._loop(ctx):
            yield ev

    # ---------- canonical loop ---------------------------------------------------------------

    async def _loop(self, ctx: AgentContext) -> AsyncIterator[Event]:
        async def emit(ev: Event) -> Event:
            ev_with_run = ev  # Event is frozen; we attach run_id via metadata in store wrapper
            await self.bus.emit(_attach_run(ev_with_run, ctx.run_id))
            return ev_with_run

        # Run started
        yield await emit(Event(type=EventType.RUN_STARTED, payload={"run_id": ctx.run_id}))

        try:
            # 1. Perception
            patch = await self.hub.perception.parse(ctx)
            ctx = await self._apply(ctx, patch, "perception")
            yield await emit(
                Event(type=EventType.PERCEPTION_DONE, element="perception", patch=patch)
            )

            # 2. Memory recall
            query = ctx.parsed_input.query if ctx.parsed_input else ctx.raw_input.text
            patch = await self.hub.memory.recall(ctx, query)
            ctx = await self._apply(ctx, patch, "memory")
            yield await emit(
                Event(type=EventType.MEMORY_RECALLED, element="memory", patch=patch)
            )

            # 2b. Discover tools so the Planner can advertise them to the LLM.
            tool_specs = await self.hub.tool.list_tools()
            if tool_specs:
                tool_patch = ContextPatch(
                    changes={"available_tools": tool_specs},
                    source_element="tool",
                    source_technique="hub",
                )
                ctx = await self._apply(ctx, tool_patch, "tool")

            # 3. Plan / execute loop
            while True:
                if ctx.budget.exceeded():
                    raise BudgetExceededError(
                        f"Budget exceeded after step {ctx.budget.used_steps}"
                    )

                await self.hub.safety.pre_check(ctx)

                # 3a. Plan one round (streamed)
                async for ev in self.hub.planner.plan(ctx):
                    yield await emit(ev)
                    if ev.patch:
                        ctx = await self._apply(ctx, ev.patch, ev.element or "planner")

                ctx = ctx.patch(budget=ctx.budget.consume(steps=1))

                if ctx.plan and ctx.plan.is_done():
                    yield await emit(
                        Event(
                            type=EventType.PLANNER_FINAL,
                            element="planner",
                            payload={"final": ctx.plan.final_answer},
                        )
                    )
                    break

                # 3b. Execute next action via Tool Element
                if ctx.plan and ctx.plan.next_action is not None:
                    async for ev in self.hub.executor.run(ctx, self.hub.tool):
                        yield await emit(ev)
                        if ev.patch:
                            ctx = await self._apply(
                                ctx, ev.patch, ev.element or "executor"
                            )
                else:
                    # Planner produced neither final nor action — break to avoid infinite loop.
                    break

                await self.hub.safety.post_check(ctx)

            # 4. Store final memory
            if ctx.plan and ctx.plan.final_answer:
                store_patch = await self.hub.memory.store(
                    ctx,
                    MemoryItem(
                        content=ctx.plan.final_answer,
                        source="runtime.final",
                        metadata={"run_id": ctx.run_id},
                    ),
                )
                ctx = await self._apply(ctx, store_patch, "memory")
                yield await emit(
                    Event(type=EventType.MEMORY_STORED, element="memory", patch=store_patch)
                )

            # 5. Output formatting
            collected = []
            async for chunk in self.hub.output.format(ctx):
                collected.append(chunk.text)
                yield await emit(
                    Event(
                        type=EventType.OUTPUT_CHUNK,
                        element="output",
                        payload={"text": chunk.text, "kind": chunk.kind},
                    )
                )
            yield await emit(
                Event(
                    type=EventType.OUTPUT_END,
                    element="output",
                    payload={"text": "".join(collected)},
                )
            )

            yield await emit(
                Event(
                    type=EventType.RUN_COMPLETED,
                    payload={
                        "run_id": ctx.run_id,
                        "steps": ctx.budget.used_steps,
                    },
                )
            )

        except BudgetExceededError as exc:
            yield await emit(
                Event(type=EventType.RUN_FAILED, payload={"reason": str(exc), "kind": "budget"})
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Agent run failed")
            yield await emit(
                Event(
                    type=EventType.RUN_FAILED,
                    payload={"reason": str(exc), "kind": exc.__class__.__name__},
                )
            )

    # ---------- helpers ----------------------------------------------------------------------

    async def _apply(
        self, ctx: AgentContext, patch: ContextPatch, source_element: str
    ) -> AgentContext:
        if patch is None or not patch.changes:
            return ctx
        if not patch.source_element:
            patch = ContextPatch(
                changes=patch.changes,
                source_element=source_element,
                source_technique=patch.source_technique,
                ts=patch.ts,
            )
        await self.store.append_patch(ctx.run_id, patch)
        return patch.apply_to(ctx)


# ---------- private helpers ------------------------------------------------------------------


def _build_model_hub(cfg: AgentConfig) -> ModelHub:
    hub = ModelHub()
    factories = ModelHub.discover_factories()
    for prov_cfg in cfg.providers:
        factory = factories.get(prov_cfg.type)
        if factory is None:
            raise ValueError(
                f"Provider '{prov_cfg.name}' references unknown ModelProvider type "
                f"'{prov_cfg.type}'. Discovered: {sorted(factories)}"
            )
        try:
            instance = factory(config=prov_cfg.config)
        except TypeError:
            try:
                instance = factory(prov_cfg.config)
            except TypeError:
                instance = factory()
        hub.register(prov_cfg.name, prov_cfg.type, instance)
    for alias, qualified in cfg.models.items():
        hub.set_alias(alias, qualified)
    return hub


def _build_hub(cfg: AgentConfig, registry: Registry, models: ModelHub) -> ElementHub:
    hub = ElementHub()

    host_map: dict[str, object] = {
        "perception": hub.perception,
        "memory": hub.memory,
        "planner": hub.planner,
        "tool": hub.tool,
        "executor": hub.executor,
        "safety": hub.safety,
        "output": hub.output,
        "observability": hub.observability,
    }

    for element_name, element_cfg in cfg.elements.items():
        host = host_map.get(element_name)
        if host is None:
            # Custom (3rd-party) Element — create a generic ElementHost.
            from agentkit.hub import ElementHost

            host = ElementHost(element=element_name)
            hub.custom[element_name] = host
            host_map[element_name] = host

        for tech_cfg in element_cfg.techniques:
            try:
                factory = registry.get_technique_factory(element_name, tech_cfg.name)
            except KeyError as exc:
                raise ValueError(
                    f"Element '{element_name}' configured with unknown technique "
                    f"'{tech_cfg.name}'. {exc}"
                ) from exc
            instance = _instantiate_technique(factory, tech_cfg.config, models)
            host.add(instance)  # type: ignore[union-attr]

        host.routing = get_strategy(element_cfg.routing)  # type: ignore[union-attr]

    return hub


def _instantiate_technique(factory, config: dict, models: ModelHub):
    """Instantiate a Technique factory tolerantly.

    We probe four signatures in order, choosing the richest one the factory accepts:

    1. ``factory(config=config, models=models)``
    2. ``factory(boot=BootContext(...))``
    3. ``factory(config=config)``
    4. ``factory(config)`` (positional)
    5. ``factory()``

    We **only** swallow ``TypeError`` raised by Python's argument-binding step itself;
    any other exception (or a TypeError raised inside the factory body) is re-raised
    with the qualified Technique name attached, so plugin bugs are not silently masked.
    """
    boot = BootContext(config=config, models=models)
    import inspect

    sig = None
    try:
        sig = inspect.signature(factory)
    except (TypeError, ValueError):
        sig = None

    def _accepts(kwargs: dict) -> bool:
        if sig is None:
            return True  # No introspection — fall back to try/except.
        try:
            sig.bind_partial(**kwargs)
            return True
        except TypeError:
            return False

    candidates: list[tuple[tuple, dict]] = [
        ((), {"config": config, "models": models}),
        ((), {"boot": boot}),
        ((), {"config": config}),
        ((config,), {}),
        ((), {}),
    ]
    last_bind_failure: TypeError | None = None
    for args, kwargs in candidates:
        # Skip signatures we know won't bind, when introspection is available.
        if kwargs and not _accepts(kwargs):
            continue
        try:
            return factory(*args, **kwargs)
        except TypeError as exc:
            last_bind_failure = exc
            continue

    raise RuntimeError(
        f"Could not call Technique factory {factory!r} with any known signature"
    ) from last_bind_failure


def _attach_run(event: Event, run_id: str) -> Event:
    """Stamp run_id into the Event payload, normalising payloads to dicts.

    Many Event types are emitted with ``payload=None`` (e.g. ``perception.done``).
    We coerce them to ``{"run_id": ...}`` so downstream consumers can always rely on
    looking up ``payload["run_id"]``.
    """
    payload = event.payload
    if isinstance(payload, dict):
        if "run_id" in payload:
            return event
        new_payload = {**payload, "run_id": run_id}
    elif payload is None:
        new_payload = {"run_id": run_id}
    else:
        new_payload = {"value": payload, "run_id": run_id}
    return Event(
        type=event.type,
        element=event.element,
        technique=event.technique,
        payload=new_payload,
        ts=event.ts,
        span_id=event.span_id,
        parent_span_id=event.parent_span_id,
        patch=event.patch,
    )


def ev_run_id_from(event: Event) -> str:
    if isinstance(event.payload, dict) and "run_id" in event.payload:
        return str(event.payload["run_id"])
    return ""
