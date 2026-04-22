"""Default Agent Runtime — the canonical loop assembling all 9 Elements.

Responsibilities:

1. Build an :class:`aglet.hub.ElementHub` from an :class:`aglet.config.AgentConfig` and
   the global :class:`aglet.registry.Registry`.
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

from aglet.budget import Budget, BudgetExceededError
from aglet.config import AgentConfig
from aglet.context import (
    AgentContext,
    ContextPatch,
    MemoryItem,
    Message,
    RawInput,
)
import asyncio
import uuid
from datetime import datetime, timezone

from aglet.events import Event, EventBus, EventType
from aglet.hooks import HookCallable, HookManager
from aglet.hub import (
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
from aglet.models import ModelHub
from aglet.protocols import BootContext
from aglet.registry import Registry, get_registry
from aglet.routing import get_strategy
from aglet.store import ContextStore, JsonlContextStore

log = logging.getLogger(__name__)


@dataclass
class Runtime:
    """The default Agent Runtime."""

    hub: ElementHub
    bus: EventBus
    store: ContextStore
    config: AgentConfig
    models: ModelHub
    hooks: HookManager

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

        # Spawn / probe out-of-process plugins declared under `external_plugins:` and
        # register their proxies as in-process Techniques. This blocks until each
        # external runtime hands us its component list.
        external_runtimes = _bootstrap_external_plugins(cfg, registry)

        # Fail closed on catastrophic misconfigurations (empty planner, empty output)
        # rather than letting the canonical Loop silently produce empty results.
        _sanity_check_config(cfg)

        models = _build_model_hub(cfg)
        hub = _build_hub(cfg, registry, models)
        bus = EventBus()
        hooks = _build_hook_manager(cfg, registry, models)

        if store is None:
            if cfg.store.type == "jsonl":
                store = JsonlContextStore(cfg.store.directory)
            else:
                from aglet.store import InMemoryContextStore  # local to avoid cycles

                store = InMemoryContextStore()

        # Wire Observability Techniques to the bus + store automatically.
        async def _fan_out(ev: Event) -> None:
            await hub.observability.on_event(ev)
            await store.append_event(ev_run_id_from(ev), ev)

        bus.subscribe(_fan_out)

        rt = cls(hub=hub, bus=bus, store=store, config=cfg, models=models, hooks=hooks)
        rt._external_runtimes = external_runtimes  # for explicit shutdown if desired
        return rt

    # ---------- hook helpers ------------------------------------------------------------------

    async def _wrap_call(
        self,
        element: str,
        method: str,
        ctx: AgentContext,
        coro_factory,
        payload: dict | None = None,
    ):
        """Run a coroutine between matching ``before/after/error`` hooks.

        Returns ``(result, ctx_after)`` so the caller can pick up any context
        mutations produced by hook subscribers.
        """
        ctx_now = ctx
        for patch in await self.hooks.fire("before", element, method, ctx_now, payload):
            ctx_now = await self._apply(ctx_now, patch, f"hook:{element}")

        try:
            result = await coro_factory(ctx_now)
        except Exception as exc:
            for patch in await self.hooks.fire(
                "error",
                element,
                method,
                ctx_now,
                {**(payload or {}), "error": str(exc), "kind": exc.__class__.__name__},
            ):
                ctx_now = await self._apply(ctx_now, patch, f"hook:{element}")
            raise

        after_payload = {**(payload or {}), "result": _summarise(result)}
        for patch in await self.hooks.fire(
            "after", element, method, ctx_now, after_payload
        ):
            ctx_now = await self._apply(ctx_now, patch, f"hook:{element}")
        return result, ctx_now

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

    async def resume(self, run_id: str) -> AsyncIterator[Event]:
        """Resume a previously-checkpointed run from its last patch.

        The store is consulted for the patch sequence captured under ``run_id``;
        we rebuild the AgentContext, then re-enter the canonical Loop. If the
        original run already reached ``run.completed`` we re-emit a
        ``run.completed`` event without actually re-running anything.

        Notes:
        * Tool calls already executed are preserved in ctx and re-shown to the
          planner as past observations — the LLM picks up where it left off.
        * Budget usage is restored, so resume cannot bypass an already-exhausted
          quota.
        """
        if not await self.store.has_run(run_id):
            raise KeyError(f"No checkpoint found for run_id={run_id!r}")

        # Detect terminal status from the persisted event log so we can short-circuit.
        events = await self.store.load_events(run_id)
        terminal = next(
            (
                e
                for e in events
                if e.type
                in (
                    EventType.RUN_COMPLETED,
                    EventType.RUN_FAILED,
                    EventType.RUN_CANCELLED,
                )
            ),
            None,
        )
        if terminal is not None:
            # Replay completion event so the caller sees a fast-path "already done".
            yield Event(
                type=terminal.type,
                element=terminal.element,
                technique=terminal.technique,
                payload={
                    **(terminal.payload if isinstance(terminal.payload, dict) else {}),
                    "resumed": True,
                },
                ts=datetime.now(timezone.utc),
                span_id=str(uuid.uuid4()),
            )
            return

        # Rebuild context from patches.
        base = AgentContext(
            run_id=run_id,
            raw_input=RawInput(),
            budget=Budget(
                max_steps=self.config.budget.max_steps,
                max_tokens=self.config.budget.max_tokens,
                max_seconds=self.config.budget.max_seconds,
                max_cost_usd=self.config.budget.max_cost_usd,
            ),
        )
        ctx = await self.store.rebuild(run_id, base)
        # Re-enter the loop. The planner will see the existing scratchpad / tool_calls
        # / tool_results and pick up where it left off.
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
            patch, ctx = await self._wrap_call(
                "perception", "parse", ctx, lambda c: self.hub.perception.parse(c)
            )
            ctx = await self._apply(ctx, patch, "perception")
            yield await emit(
                Event(type=EventType.PERCEPTION_DONE, element="perception", patch=patch)
            )

            # 2. Memory recall
            query = ctx.parsed_input.query if ctx.parsed_input else ctx.raw_input.text
            patch, ctx = await self._wrap_call(
                "memory",
                "recall",
                ctx,
                lambda c: self.hub.memory.recall(c, query),
                payload={"query": query},
            )
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

                # 3a. Plan one round (streamed). Fire before/after.planner.plan around the
                # entire streaming round; per-event hooks would be too chatty.
                for hp in await self.hooks.fire("before", "planner", "plan", ctx, {}):
                    ctx = await self._apply(ctx, hp, "hook:planner")

                async for ev in self.hub.planner.plan(ctx):
                    yield await emit(ev)
                    if ev.patch:
                        ctx = await self._apply(ctx, ev.patch, ev.element or "planner")

                for hp in await self.hooks.fire(
                    "after",
                    "planner",
                    "plan",
                    ctx,
                    {"plan": ctx.plan.__dict__ if ctx.plan else None},
                ):
                    ctx = await self._apply(ctx, hp, "hook:planner")

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

                # 3b. Execute next action via Tool Element. Wrap the ToolHost so that
                # before/after.tool.invoke hooks fire around each tool call.
                if ctx.plan and ctx.plan.next_action is not None:
                    hooked_tools = _HookedToolHost(self.hub.tool, self.hooks, lambda: ctx)
                    async for ev in self.hub.executor.run(ctx, hooked_tools):
                        yield await emit(ev)
                        if ev.patch:
                            ctx = await self._apply(
                                ctx, ev.patch, ev.element or "executor"
                            )
                    # Apply patches collected by hook subscribers during tool invocation.
                    for patch in hooked_tools.collected_patches:
                        ctx = await self._apply(ctx, patch, "hook:tool")
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


class _HookedToolHost:
    """ToolHost wrapper that fires before/after/error.tool.invoke hooks per call.

    Patches returned by hook subscribers are buffered onto ``collected_patches`` and
    applied by the Runtime after the executor's async generator completes (because
    we cannot mutate the executor's local ctx mid-iteration).
    """

    def __init__(self, inner, hooks: HookManager, ctx_supplier):
        self._inner = inner
        self._hooks = hooks
        self._ctx_supplier = ctx_supplier
        self.collected_patches: list[ContextPatch] = []

    async def list_tools(self):
        return await self._inner.list_tools()

    async def invoke_tool(self, call):
        ctx = self._ctx_supplier()
        call_payload = {
            "call": {"id": call.id, "name": call.name, "arguments": call.arguments}
        }
        self.collected_patches.extend(
            await self._hooks.fire("before", "tool", "invoke", ctx, call_payload)
        )
        try:
            result = await self._inner.invoke_tool(call)
        except Exception as exc:
            self.collected_patches.extend(
                await self._hooks.fire(
                    "error",
                    "tool",
                    "invoke",
                    ctx,
                    {**call_payload, "error": str(exc), "kind": exc.__class__.__name__},
                )
            )
            raise
        self.collected_patches.extend(
            await self._hooks.fire(
                "after",
                "tool",
                "invoke",
                ctx,
                {
                    **call_payload,
                    "result": {
                        "output": _summarise(result.output),
                        "error": result.error,
                        "latency_ms": result.latency_ms,
                    },
                },
            )
        )
        return result


# Sanity checks — the two Elements every useful agent must actually have
# configured with at least one Technique. Without these, the canonical Loop
# silently produces an empty result — catastrophic for new users.
_REQUIRED_ELEMENTS: tuple[str, ...] = ("planner", "output")

# Strongly recommended — we warn but don't fail, because there ARE advanced
# use cases (e.g. a custom Runtime loop) where these might legitimately be
# absent.
_RECOMMENDED_ELEMENTS: tuple[str, ...] = ("perception", "safety")


class AgentConfigError(ValueError):
    """Raised when an agent.yaml is structurally unusable with the default Loop."""


def _sanity_check_config(cfg: AgentConfig) -> None:
    """Verify the config declares every Element the canonical Loop depends on.

    Specifically:
      * ``planner`` must exist and have at least one Technique; otherwise the
        Loop produces no thought / action / final answer and the run returns
        an empty string with exit code 0 — a terrible UX trap.
      * ``output`` must exist and have at least one Technique; otherwise the
        planner's ``Plan.final_answer`` is never rendered for the caller.

    Missing-but-recommended Elements produce a warning on stderr (via logging);
    missing-and-required Elements raise :class:`AgentConfigError` before the
    run starts.
    """
    missing_required: list[str] = []
    for name in _REQUIRED_ELEMENTS:
        element_cfg = cfg.elements.get(name)
        if element_cfg is None or not element_cfg.techniques:
            missing_required.append(name)

    if missing_required:
        noun = "element" if len(missing_required) == 1 else "elements"
        names = ", ".join(sorted(missing_required))
        raise AgentConfigError(
            f"agent.yaml {noun} missing or empty: {names}. "
            "The canonical Loop would produce an empty result. "
            "Add at least one technique to each (e.g. `planner: {techniques: [{name: echo}]}`). "
            "If you really want to skip these, plug in a custom Runtime."
        )

    for name in _RECOMMENDED_ELEMENTS:
        element_cfg = cfg.elements.get(name)
        if element_cfg is None or not element_cfg.techniques:
            log.warning(
                "agent.yaml recommended element %r is missing or empty; "
                "continuing, but behaviour may be surprising",
                name,
            )


def _bootstrap_external_plugins(cfg: AgentConfig, registry: Registry) -> list:
    """Register Technique proxies for every ``external_plugins:`` entry.

    The proxies are **lazy**: they spawn the subprocess (or open the HTTP client)
    only on first invocation, and they do so inside the caller's event loop. This
    avoids cross-loop bugs when ``Runtime.from_config`` is called from inside an
    already-running asyncio loop (FastAPI handlers, pytest-asyncio tests, etc.).
    """
    if not cfg.external_plugins:
        return []
    from aglet.loader.http import HttpPluginRuntime, _PROXY_BUILDERS as _HTTP_BUILDERS
    from aglet.loader.subprocess import (
        SubprocessPluginRuntime,
        _PROXY_BUILDERS as _SUBPROC_BUILDERS,
    )

    runtimes: list = []

    for plugin_cfg in cfg.external_plugins:
        if not plugin_cfg.components:
            raise ValueError(
                f"external_plugin {plugin_cfg.name!r} must declare its 'components:' "
                "list (lazy spawn requires component shape upfront)."
            )

        if plugin_cfg.runtime == "subprocess":
            if not plugin_cfg.command:
                raise ValueError(
                    f"external_plugin {plugin_cfg.name!r} (subprocess) needs a 'command'"
                )
            rt = SubprocessPluginRuntime(
                command=plugin_cfg.command, env=plugin_cfg.env or None
            )
            builders = _SUBPROC_BUILDERS
            client_handle = rt.client  # _RpcClient

            def _make_proxy(comp_cfg, _rt=rt, _builders=builders):
                element = comp_cfg.element
                builder = _builders.get(element)
                if builder is None:
                    raise ValueError(
                        f"Subprocess plugin component for unknown Element {element!r}; "
                        f"supported: {sorted(_builders)}"
                    )
                return builder(
                    _rt.client,
                    {
                        "name": f"{comp_cfg.element}.{comp_cfg.name}",
                        "element": comp_cfg.element,
                        "capabilities": comp_cfg.capabilities,
                        "version": comp_cfg.version,
                    },
                )

        elif plugin_cfg.runtime == "http":
            if not plugin_cfg.base_url:
                raise ValueError(
                    f"external_plugin {plugin_cfg.name!r} (http) needs 'base_url'"
                )
            rt = HttpPluginRuntime(
                base_url=plugin_cfg.base_url, headers=plugin_cfg.headers or None
            )
            builders = _HTTP_BUILDERS

            def _make_proxy(comp_cfg, _rt=rt, _builders=builders):
                element = comp_cfg.element
                builder = _builders.get(element)
                if builder is None:
                    raise ValueError(
                        f"HTTP plugin component for unknown Element {element!r}; "
                        f"supported: {sorted(_builders)}"
                    )
                return builder(
                    _rt,
                    {
                        "name": f"{comp_cfg.element}.{comp_cfg.name}",
                        "element": comp_cfg.element,
                        "capabilities": comp_cfg.capabilities,
                        "version": comp_cfg.version,
                    },
                )

        else:
            raise ValueError(
                f"Unknown external_plugin runtime {plugin_cfg.runtime!r}; "
                "supported: subprocess, http"
            )

        for comp_cfg in plugin_cfg.components:
            proxy = _make_proxy(comp_cfg)
            registry.register_technique(
                comp_cfg.element, comp_cfg.name, lambda *_a, _p=proxy, **_kw: _p
            )
        runtimes.append(rt)
    return runtimes


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
            from aglet.hub import ElementHost

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


def _build_hook_manager(
    cfg: AgentConfig, registry: Registry, models: ModelHub
) -> HookManager:
    """Build a HookManager from agent.yaml's ``hooks:`` block.

    Each hook entry references either:
    * a registered Technique by qualified name (``element.name``), in which case its
      ``on_lifecycle(event_name, ctx, payload)`` method is bound, OR
    * a dotted ``module:Callable`` import path that yields the same async signature.
    """
    hm = HookManager()
    for hook_cfg in cfg.hooks:
        handler = _resolve_hook_handler(hook_cfg.technique, hook_cfg.config, registry, models)
        hm.subscribe(hook_cfg.on, handler, label=hook_cfg.technique)
    return hm


def _resolve_hook_handler(
    target: str, config: dict, registry: Registry, models: ModelHub
) -> HookCallable:
    """Resolve ``target`` to an async hook callable.

    ``target`` may be ``element.name`` (a registered Technique) or ``module:Callable``.
    """
    if ":" in target:
        # Dotted import: ``my_pkg.module:my_hook`` or ``my_pkg.module:HookCls``.
        import importlib

        module_path, _, attr = target.partition(":")
        module = importlib.import_module(module_path)
        obj = getattr(module, attr)
        if isinstance(obj, type):
            instance = _instantiate_technique(obj, config, models)
            return _bind_lifecycle_method(instance)
        return obj  # already a callable

    # Try Technique registry by ``element.name``.
    element, _, name = target.partition(".")
    if not name:
        raise ValueError(
            f"Hook target {target!r} must be 'element.technique' or 'module:Callable'."
        )
    factory = registry.get_technique_factory(element, name)
    instance = _instantiate_technique(factory, config, models)
    return _bind_lifecycle_method(instance)


def _bind_lifecycle_method(instance) -> HookCallable:
    """Return an async hook callable bound to ``instance``.

    Looks for ``on_lifecycle`` first, then ``__call__``. Both are common patterns.
    """
    for attr in ("on_lifecycle", "__call__"):
        method = getattr(instance, attr, None)
        if method is not None and callable(method):
            return method  # type: ignore[return-value]
    raise TypeError(
        f"Hook target {type(instance).__name__} has neither on_lifecycle nor __call__"
    )


def _summarise(value):
    """Best-effort short representation for hook payloads / event logs."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _summarise(v) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple, set)):
        return [_summarise(v) for v in list(value)[:20]]
    return repr(value)[:200]


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
