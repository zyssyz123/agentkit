"""Brand-new `intent` Element for Aglet.

Contributes both an Element protocol and one technique (`intent.keyword`).
Zero changes to the aglet core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from aglet.context import AgentContext, ContextPatch


# -------- the new Element protocol -----------------------------------------

@dataclass(frozen=True)
class IntentLabel:
    name: str              # e.g. "debug", "summarise", "chit_chat"
    confidence: float = 1.0


@runtime_checkable
class IntentProtocol(Protocol):
    """Every Technique under `intent` must expose `classify(ctx) -> IntentLabel`."""

    element_kind: str

    async def classify(self, ctx: AgentContext) -> IntentLabel: ...


# -------- one technique implementing it ------------------------------------

class KeywordIntent:
    """Trivial keyword-matching intent classifier. Config:

        elements:
          intent:
            techniques:
              - name: keyword
                config:
                  rules:
                    - keywords: ["debug", "error", "traceback"]
                      label: debug
                    - keywords: ["summarise", "summary", "summarize"]
                      label: summarise
                  default: chit_chat
    """

    name = "keyword"
    element = "intent"
    version = "0.1.0"
    capabilities = frozenset({"classify"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._rules: list[tuple[list[str], str]] = [
            (
                [kw.lower() for kw in r.get("keywords", [])],
                r["label"],
            )
            for r in cfg.get("rules", [])
        ]
        self._default: str = cfg.get("default", "unknown")

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus
        return HealthStatus(healthy=True)

    async def classify(self, ctx: AgentContext) -> IntentLabel:
        text = (ctx.raw_input.text or "").lower()
        for keywords, label in self._rules:
            if any(kw in text for kw in keywords):
                return IntentLabel(name=label, confidence=1.0)
        return IntentLabel(name=self._default, confidence=0.5)

    # Aglet's canonical Loop doesn't know about our Element's `classify` method,
    # so we also implement a hook-compatible entry that ships the result into
    # ctx.metadata. Users wire it via agent.yaml `hooks:` — see README.
    async def on_lifecycle(
        self, event_name: str, ctx: AgentContext, payload: dict[str, Any]
    ) -> ContextPatch | None:
        if not event_name.endswith(".perception.parse"):
            return None
        if not event_name.startswith("after."):
            return None
        label = await self.classify(ctx)
        return ContextPatch(
            changes={
                "metadata": {
                    **ctx.metadata,
                    "intent": {"name": label.name, "confidence": label.confidence},
                }
            },
            source_element="intent",
            source_technique=self.name,
        )
