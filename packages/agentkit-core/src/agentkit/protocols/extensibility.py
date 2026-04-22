"""Extensibility Element — meta-techniques like model routing, prompt versioning, webhooks.

This Element is intentionally open-ended: its Techniques typically register hooks into
other Elements' lifecycle rather than implementing a tight method contract.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agentkit.context import AgentContext


@runtime_checkable
class ExtensibilityTechnique(Protocol):
    name: str
    element: str = "extensibility"
    capabilities: frozenset[str]

    async def on_lifecycle(self, hook_name: str, ctx: AgentContext, payload: Any) -> Any:
        """Generic hook callback invoked by the Runtime/HookManager.

        ``hook_name`` follows the pattern ``<phase>.<element>.<method>``,
        e.g. ``before.tool.invoke``. Returning a ContextPatch lets the technique
        amend the context; returning None is a pure side-effect.
        """
        ...
