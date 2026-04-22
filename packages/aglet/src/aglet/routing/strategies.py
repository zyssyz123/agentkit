"""Routing strategies: how an ElementHost dispatches a method across N Techniques."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aglet.context import AgentContext, ContextPatch


class RoutingStrategy(Protocol):
    """Coordinates a method call across all Techniques bound to one ElementHost.

    Implementations decide ordering, parallelism and merge semantics. They MUST
    return either a single ContextPatch (merged) or whatever a single Technique
    would return for non-patch-producing methods.
    """

    name: str

    async def dispatch(
        self,
        techniques: list[Any],
        invoker: Callable[[Any], Awaitable[Any]],
        ctx: AgentContext | None = None,
    ) -> Any: ...


# ---------- concrete strategies ---------------------------------------------------------------


class AllStrategy:
    """Invoke every Technique sequentially; merge ContextPatches in order."""

    name = "all"

    async def dispatch(
        self,
        techniques: list[Any],
        invoker: Callable[[Any], Awaitable[Any]],
        ctx: AgentContext | None = None,
    ) -> Any:
        if not techniques:
            return ContextPatch.empty()
        merged = ContextPatch.empty()
        for tech in techniques:
            result = await invoker(tech)
            merged = _merge(merged, result)
        return merged


class FirstMatchStrategy:
    """Try Techniques in order; stop at the first one returning a non-empty patch."""

    name = "first_match"

    async def dispatch(
        self,
        techniques: list[Any],
        invoker: Callable[[Any], Awaitable[Any]],
        ctx: AgentContext | None = None,
    ) -> Any:
        for tech in techniques:
            result = await invoker(tech)
            if isinstance(result, ContextPatch) and result.changes:
                return result
            if result is not None and not isinstance(result, ContextPatch):
                return result
        return ContextPatch.empty()


class ParallelMergeStrategy:
    """Run all Techniques concurrently; merge ContextPatches via append semantics."""

    name = "parallel_merge"

    async def dispatch(
        self,
        techniques: list[Any],
        invoker: Callable[[Any], Awaitable[Any]],
        ctx: AgentContext | None = None,
    ) -> Any:
        if not techniques:
            return ContextPatch.empty()
        results = await asyncio.gather(*(invoker(t) for t in techniques))
        merged = ContextPatch.empty()
        for r in results:
            merged = _merge(merged, r)
        return merged


_REGISTRY: dict[str, RoutingStrategy] = {
    "all": AllStrategy(),
    "first_match": FirstMatchStrategy(),
    "parallel_merge": ParallelMergeStrategy(),
}


def get_strategy(name: str) -> RoutingStrategy:
    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown routing strategy '{name}'; available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


# ---------- helpers ---------------------------------------------------------------------------


def _merge(left: Any, right: Any) -> Any:
    """Merge two ContextPatch values, with right-side taking precedence on conflicts.

    *_append keys concatenate. Other keys are last-write-wins.
    """
    if not isinstance(left, ContextPatch) or not isinstance(right, ContextPatch):
        return right if right is not None else left
    out: dict[str, Any] = dict(left.changes)
    for key, value in right.changes.items():
        if key.endswith("_append") and key in out:
            existing = list(out[key])
            existing.extend(value)
            out[key] = existing
        else:
            out[key] = value
    return ContextPatch(
        changes=out,
        source_element=right.source_element or left.source_element,
        source_technique=f"{left.source_technique}+{right.source_technique}".strip("+"),
    )
