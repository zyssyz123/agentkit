"""Built-in Hook Techniques (Extensibility Element).

Each class below conforms to the Extensibility protocol — async ``on_lifecycle`` —
and can be wired in agent.yaml's ``hooks:`` block::

    hooks:
      - on: before.tool.invoke
        technique: extensibility.tool_audit
      - on: after.tool.invoke
        technique: extensibility.cost_tracker
        config: { rate_per_call_usd: 0.0001 }
      - on: before.tool.invoke
        technique: extensibility.tool_gate
        config:
          allow: ["echo", "now_iso"]
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agentkit.context import AgentContext, ContextPatch

log = logging.getLogger(__name__)


# ---------- common scaffolding --------------------------------------------------------------


class _BaseHook:
    """Shared setup/teardown/health for hook-style Techniques."""

    name = "base"
    element = "extensibility"
    version = "0.1.0"
    capabilities = frozenset()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)


# ---------- ToolAuditHook --------------------------------------------------------------------


class ToolAuditHook(_BaseHook):
    """Append every tool invocation to ``ctx.metadata['tool_audit']`` for compliance."""

    name = "tool_audit"
    capabilities = frozenset({"audit"})

    async def on_lifecycle(
        self, event_name: str, ctx: AgentContext, payload: dict[str, Any]
    ) -> ContextPatch | None:
        # Only react to before/after.tool.invoke events.
        if not event_name.endswith(".tool.invoke"):
            return None
        if not event_name.startswith("after."):
            return None
        call = payload.get("call", {}) or {}
        result = payload.get("result", {}) or {}
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": call.get("name"),
            "arguments": call.get("arguments"),
            "outcome": "error" if result.get("error") else "ok",
            "latency_ms": result.get("latency_ms"),
        }
        existing = ctx.metadata.get("tool_audit", [])
        return ContextPatch(
            changes={"metadata": {**ctx.metadata, "tool_audit": [*existing, entry]}},
            source_element=self.element,
            source_technique=self.name,
        )


# ---------- CostTrackerHook ------------------------------------------------------------------


class CostTrackerHook(_BaseHook):
    """Add a fixed per-tool-call cost into ``ctx.budget.used_cost_usd``.

    Useful as a coarse "I want to cap external API spend" guardrail when individual
    tools don't report their own cost. Subclass / replace for precise pricing.
    """

    name = "cost_tracker"
    capabilities = frozenset({"cost"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.rate_per_call_usd: float = float(self._config.get("rate_per_call_usd", 0.0001))

    async def on_lifecycle(
        self, event_name: str, ctx: AgentContext, payload: dict[str, Any]
    ) -> ContextPatch | None:
        if not event_name.startswith("after.tool.invoke"):
            return None
        new_budget = ctx.budget.consume(cost_usd=self.rate_per_call_usd)
        return ContextPatch(
            changes={"budget": new_budget},
            source_element=self.element,
            source_technique=self.name,
        )


# ---------- ToolGateHook ---------------------------------------------------------------------


class GateBlockedError(RuntimeError):
    """Raised by ToolGateHook to abort a forbidden tool call."""


class ToolGateHook(_BaseHook):
    """Whitelist / blacklist tool calls before they execute.

    Config::

        config:
          allow: ["echo", "now_iso"]   # if set, only these may run
          deny:  ["dangerous_tool"]    # if set, these never run (overrides allow)
          on_block: skip               # "skip" -> raise so executor records error,
                                       # "warn" -> log only, allow the call
    """

    name = "tool_gate"
    capabilities = frozenset({"safety", "gate"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.allow: set[str] | None = (
            set(self._config["allow"]) if "allow" in self._config else None
        )
        self.deny: set[str] = set(self._config.get("deny", []))
        self.on_block: str = self._config.get("on_block", "skip")

    async def on_lifecycle(
        self, event_name: str, ctx: AgentContext, payload: dict[str, Any]
    ) -> ContextPatch | None:
        if not event_name.startswith("before.tool.invoke"):
            return None
        call = payload.get("call", {}) or {}
        name = call.get("name")
        if name in self.deny or (self.allow is not None and name not in self.allow):
            msg = f"tool '{name}' blocked by ToolGateHook"
            if self.on_block == "warn":
                log.warning(msg)
                return None
            raise GateBlockedError(msg)
        return None
