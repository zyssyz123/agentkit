"""memory.summary — rolling LLM-summarised conversation memory.

Complements ``memory.sliding_window`` for long conversations. When the
per-conversation message buffer grows beyond ``trigger_chars`` characters,
the technique asks an LLM to compress the oldest half into a single
system-message-style bullet summary and recalls it alongside future turns.

Config schema::

    type: summary
    config:
      model: default              # alias from agent.yaml `models:`
      trigger_chars: 6000         # compress when running size exceeds this
      keep_recent: 6              # keep the N most recent messages verbatim
      summary_prefix: "[Prior conversation summary]"

Routing-wise, combine it with ``memory.sliding_window`` under a ``parallel_merge``
routing strategy — the window gives you verbatim recent turns, the summary
injects a compressed prefix.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from aglet.context import AgentContext, ContextPatch, MemoryItem, Message
from aglet.models import ModelHub, ModelMessage

log = logging.getLogger(__name__)

SUMMARY_PROMPT = (
    "You are compressing an agent's conversation history for long-term memory. "
    "Read the messages below and return ONE concise paragraph (<=80 words) "
    "capturing the user's goals, decisions made, and facts established. "
    "Do not add new information. Do not include greetings or meta-commentary."
)


class SummaryMemory:
    name = "summary"
    element = "memory"
    version = "0.1.0"
    capabilities = frozenset({"recall", "store", "summarize"})

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        models: ModelHub | None = None,
    ) -> None:
        cfg = config or {}
        self.model_alias: str = cfg.get("model", "default")
        self.trigger_chars: int = int(cfg.get("trigger_chars", 6000))
        self.keep_recent: int = int(cfg.get("keep_recent", 6))
        self.summary_prefix: str = cfg.get("summary_prefix", "[Prior conversation summary]")
        self._models = models

        # Per-conversation state: list of verbatim Messages + running summary.
        self._state: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"messages": [], "summary": None}
        )
        self._compress_lock = asyncio.Lock()

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=self._models is not None)

    # ------------------------------------------------------------------

    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        # Seed per-turn state from ctx.history (the Runtime threads history in via run()).
        state = self._state[ctx.conversation_id or "default"]
        # Merge any incoming messages we haven't seen yet.
        known = {id(m) for m in state["messages"]}
        for msg in ctx.history:
            if id(msg) not in known:
                state["messages"].append(msg)

        await self._maybe_compress(state)

        items: list[MemoryItem] = []
        if state["summary"]:
            items.append(
                MemoryItem(
                    content=f"{self.summary_prefix}: {state['summary']}",
                    source=f"{self.element}.{self.name}",
                )
            )
        if not items:
            return ContextPatch.empty(self.element, self.name)

        return ContextPatch(
            changes={"recalled_memory_append": items},
            source_element=self.element,
            source_technique=self.name,
        )

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        # Append the final answer as an assistant message so the summary keeps
        # track of the agent's own responses too.
        state = self._state[ctx.conversation_id or "default"]
        state["messages"].append(Message(role="assistant", content=item.content))
        await self._maybe_compress(state)
        return ContextPatch.empty(self.element, self.name)

    # ------------------------------------------------------------------

    async def _maybe_compress(self, state: dict[str, Any]) -> None:
        total = sum(len(m.content) for m in state["messages"])
        if total <= self.trigger_chars or self._models is None:
            return

        async with self._compress_lock:
            total = sum(len(m.content) for m in state["messages"])
            if total <= self.trigger_chars or self._models is None:
                return

            head = state["messages"][: -self.keep_recent] if self.keep_recent else state["messages"]
            tail = state["messages"][-self.keep_recent :] if self.keep_recent else []
            if not head:
                return

            try:
                provider, model_id = self._models.resolve(self.model_alias)
            except KeyError:
                log.warning("memory.summary: model alias %r unresolved", self.model_alias)
                return

            prior = state["summary"] or ""
            body = "\n".join(f"[{m.role}] {m.content}" for m in head)
            msgs = [
                ModelMessage(role="system", content=SUMMARY_PROMPT),
                ModelMessage(
                    role="user",
                    content=(
                        (f"Existing summary:\n{prior}\n\n" if prior else "")
                        + f"New messages:\n{body}\n\nReturn the updated paragraph."
                    ),
                ),
            ]
            try:
                resp = await provider.complete(
                    model=model_id, messages=msgs, temperature=0.0, max_tokens=200
                )
                new_summary = (resp.content or "").strip()
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "memory.summary: compression failed (%s): %s",
                    exc.__class__.__name__,
                    exc,
                )
                return

            if new_summary:
                state["summary"] = new_summary
                state["messages"] = list(tail)
