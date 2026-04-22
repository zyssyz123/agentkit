"""Lifecycle Hook system.

Hooks are the cross-cutting extension point that lets users wedge custom logic into
the canonical Agent Loop **without** replacing the Runtime or any Element implementation.

Naming
------

Hook event names follow a fixed three-part shape::

    <phase>.<element>.<method>

* ``phase``  : ``before`` | ``after`` | ``error``
* ``element``: any registered Element kind (``perception``, ``memory``, ``planner``,
               ``tool``, ``executor``, ``safety``, ``output``, ``observability``, plus
               any 3rd-party Element)
* ``method`` : the Element's protocol method (``parse``, ``recall``, ``plan``,
               ``invoke``, ``run``, …) **or** the wildcard ``*``.

Examples that are valid: ``before.tool.invoke``, ``after.memory.recall``,
``error.planner.plan``, ``after.tool.*``, ``before.*.invoke``, ``*.*.*``.

Subscriber contract
-------------------

A hook subscriber is an ``async`` callable::

    async def hook(event_name: str, ctx: AgentContext, payload: dict) -> ContextPatch | None

Returning ``None`` is a pure side-effect (logging, metrics). Returning a
:class:`ContextPatch` lets the hook amend the AgentContext; the Runtime applies all
patches in order.

Subscribers MUST NOT raise except in pathological cases — exceptions are caught and
emitted as ``Event(EventType.SAFETY_ALERT, payload={"hook": ..., "error": ...})``
so a single buggy hook cannot crash the run.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from aglet.context import AgentContext, ContextPatch

log = logging.getLogger(__name__)

HookCallable = Callable[[str, AgentContext, dict[str, Any]], Awaitable["ContextPatch | None"]]
Phase = Literal["before", "after", "error"]


@dataclass
class _Subscription:
    pattern: str  # phase.element.method, may contain '*' wildcards
    handler: HookCallable
    label: str = ""

    def matches(self, event_name: str) -> bool:
        return _glob_match(self.pattern, event_name)


@dataclass
class HookManager:
    """Registry of hook subscribers + dispatcher.

    Subscribers are invoked **sequentially** in registration order. The Runtime
    accumulates returned patches and applies them between steps.
    """

    subscriptions: list[_Subscription] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Registration

    def subscribe(
        self,
        pattern: str,
        handler: HookCallable,
        *,
        label: str = "",
    ) -> Callable[[], None]:
        """Register a handler. Returns an unsubscribe callable."""
        if not _is_valid_pattern(pattern):
            raise ValueError(
                f"Invalid hook pattern {pattern!r}; expected '<phase>.<element>.<method>' "
                f"with phase in (before, after, error). Use '*' for wildcard."
            )
        sub = _Subscription(pattern=pattern, handler=handler, label=label or pattern)
        self.subscriptions.append(sub)

        def _unsub() -> None:
            try:
                self.subscriptions.remove(sub)
            except ValueError:
                pass

        return _unsub

    # ------------------------------------------------------------------
    # Dispatch

    async def fire(
        self,
        phase: Phase,
        element: str,
        method: str,
        ctx: AgentContext,
        payload: dict[str, Any] | None = None,
    ) -> list[ContextPatch]:
        """Fire all subscribers matching ``<phase>.<element>.<method>``.

        Returns the (possibly empty) list of ContextPatches in registration order.
        Hook exceptions are logged and converted into a synthetic patch carrying the
        error in metadata — they never propagate up.
        """
        if not self.subscriptions:
            return []
        event_name = f"{phase}.{element}.{method}"
        matching = [s for s in self.subscriptions if s.matches(event_name)]
        if not matching:
            return []

        payload = payload or {}
        patches: list[ContextPatch] = []
        for sub in matching:
            try:
                result = await sub.handler(event_name, ctx, payload)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Hook %r failed on %s: %s", sub.label, event_name, exc, exc_info=True
                )
                continue
            if isinstance(result, ContextPatch) and result.changes:
                patches.append(result)
        return patches

    def clear(self) -> None:
        self.subscriptions.clear()

    def __len__(self) -> int:
        return len(self.subscriptions)


# ---------- pattern helpers -------------------------------------------------------------------


_VALID_PHASES = {"before", "after", "error", "*"}


def _is_valid_pattern(pattern: str) -> bool:
    parts = pattern.split(".")
    if len(parts) != 3:
        return False
    phase, element, method = parts
    if phase not in _VALID_PHASES:
        return False
    if not element or not method:
        return False
    return True


def _glob_match(pattern: str, name: str) -> bool:
    """Match a dotted pattern against a dotted name; ``*`` matches one segment."""
    p_parts = pattern.split(".")
    n_parts = name.split(".")
    if len(p_parts) != len(n_parts):
        return False
    return all(p == "*" or p == n for p, n in zip(p_parts, n_parts, strict=True))


# ---------- public re-exports ----------------------------------------------------------------

__all__ = ["HookManager", "HookCallable", "Phase"]


# ---------- helpers exposed for testing convenience -----------------------------------------


async def gather_safe(awaitables: list[Awaitable[Any]]) -> list[Any]:
    """Gather, swallowing exceptions (returns them in-place as Exception instances)."""
    return await asyncio.gather(*awaitables, return_exceptions=True)
