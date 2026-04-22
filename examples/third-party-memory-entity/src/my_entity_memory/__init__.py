"""Third-party `memory.entity` — tracks named entities across a conversation
and surfaces ones relevant to the current query.

No new Element protocol needed; implements the existing MemoryTechnique contract
(recall / store). Registered under the `aglet.techniques` entry-point group.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from aglet.context import AgentContext, ContextPatch, MemoryItem

# Naive entity patterns. Real implementations would swap this for spaCy / a
# dedicated NER model / LLM extraction.
_PATTERNS = {
    "person":   re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"),
    "project":  re.compile(r"\b(project\s+[A-Z][\w-]+)\b", re.IGNORECASE),
    "decision": re.compile(r"\b(?:decided|agreed)\s+(?:to\s+)?([^.!\?]{5,80})", re.IGNORECASE),
}


class EntityMemory:
    name = "entity"
    element = "memory"
    version = "0.1.0"
    capabilities = frozenset({"recall", "store", "extract"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._top_k: int = int(cfg.get("top_k", 5))
        # conv_id -> {entity_type -> {surface_form -> hit_count}}
        self._store: dict[str, dict[str, dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(int))
        )

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus
        return HealthStatus(healthy=True)

    # ------------------------------------------------------------------

    def _extract(self, text: str) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for kind, pat in _PATTERNS.items():
            matches = [m.strip() for m in pat.findall(text)]
            if matches:
                found[kind] = matches
        return found

    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        conv = ctx.conversation_id or "default"

        # Update entity bag from anything in history we haven't processed yet.
        for msg in ctx.history:
            for kind, surfaces in self._extract(msg.content).items():
                for s in surfaces:
                    self._store[conv][kind][s] += 1

        # Pick entities mentioned in the current query with high score.
        entities_here = self._extract(query)
        items: list[MemoryItem] = []

        bag = self._store[conv]
        # Surface the top-k most-frequently-seen entities as memory items.
        flat: list[tuple[str, str, int]] = []
        for kind, counts in bag.items():
            for surface, count in counts.items():
                flat.append((kind, surface, count))
        flat.sort(key=lambda x: x[2], reverse=True)

        for kind, surface, count in flat[: self._top_k]:
            marker = " (mentioned now)" if kind in entities_here and surface in entities_here[kind] else ""
            items.append(
                MemoryItem(
                    content=f"{kind}={surface}  (seen x{count}){marker}",
                    source=f"{self.element}.{self.name}",
                    score=float(count),
                    metadata={"kind": kind, "surface": surface, "count": count},
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
        conv = ctx.conversation_id or "default"
        for kind, surfaces in self._extract(item.content).items():
            for s in surfaces:
                self._store[conv][kind][s] += 1
        return ContextPatch.empty(self.element, self.name)
