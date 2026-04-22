"""memory.rag — embedded LanceDB vector memory.

Embeddings are produced via the Aglet :class:`ModelHub` so any provider
(OpenAI / LiteLLM / Mock) supplying ``embed`` can power this technique.

Config schema::

    type: rag
    config:
      uri: ./data/lance
      table: memory
      embedder: embedder           # alias from agent.yaml `models:` block
      top_k: 5
      seed:                        # optional documents to ingest at startup
        - "Aglet is a pluggable Agent runtime."
        - "Every Element and Technique is a swappable plugin."
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from aglet.context import AgentContext, ContextPatch, MemoryItem
from aglet.models import ModelHub

log = logging.getLogger(__name__)


class RagMemory:
    name = "rag"
    element = "memory"
    version = "0.1.0"
    capabilities = frozenset({"recall", "store", "embed"})

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        models: ModelHub | None = None,
    ) -> None:
        cfg = config or {}
        self.uri: str = cfg.get("uri", "./data/lance")
        self.table_name: str = cfg.get("table", "memory")
        self.embedder_alias: str = cfg.get("embedder", "embedder")
        self.top_k: int = int(cfg.get("top_k", 5))
        self._seed: list[str] = list(cfg.get("seed", []))
        self._models = models
        self._db: Any = None
        self._table: Any = None
        self._init_lock = asyncio.Lock()

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=self._models is not None)

    # ------------------------------------------------------------------

    async def _ensure(self) -> None:
        if self._table is not None:
            return
        async with self._init_lock:
            if self._table is not None:
                return
            import lancedb
            import pyarrow as pa

            Path(self.uri).mkdir(parents=True, exist_ok=True)
            self._db = await asyncio.to_thread(lancedb.connect, self.uri)

            # Decide vector dimension by embedding a probe.
            provider, model_id = self._require_embedder()
            probe = await provider.embed(model_id, ["probe"])
            dim = len(probe[0])
            schema = pa.schema(
                [
                    pa.field("id", pa.string()),
                    pa.field("content", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), dim)),
                ]
            )
            try:
                self._table = await asyncio.to_thread(self._db.open_table, self.table_name)
            except Exception:  # noqa: BLE001 — table missing
                self._table = await asyncio.to_thread(
                    self._db.create_table, self.table_name, schema=schema
                )
                if self._seed:
                    await self._ingest(self._seed)

    def _require_embedder(self):
        if self._models is None:
            raise RuntimeError(
                "memory.rag needs a ModelHub (declare `providers:` and `models:` in agent.yaml)."
            )
        return self._models.resolve(self.embedder_alias)

    async def _ingest(self, texts: list[str]) -> None:
        provider, model_id = self._require_embedder()
        vectors = await provider.embed(model_id, texts)
        rows = [
            {"id": str(uuid.uuid4()), "content": t, "vector": v}
            for t, v in zip(texts, vectors, strict=True)
        ]
        await asyncio.to_thread(self._table.add, rows)

    # ------------------------------------------------------------------

    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        if not query:
            return ContextPatch.empty(self.element, self.name)
        try:
            await self._ensure()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "memory.rag setup failed (%s): %s", exc.__class__.__name__, exc, exc_info=True
            )
            return ContextPatch.empty(self.element, self.name)
        try:
            provider, model_id = self._require_embedder()
            q_vec = (await provider.embed(model_id, [query]))[0]

            def _search() -> list[dict[str, Any]]:
                return self._table.search(q_vec).limit(self.top_k).to_list()

            rows = await asyncio.to_thread(_search)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "memory.rag recall failed (%s): %s", exc.__class__.__name__, exc, exc_info=True
            )
            return ContextPatch.empty(self.element, self.name)

        items = [
            MemoryItem(
                content=r["content"],
                source=f"{self.element}.{self.name}",
                score=float(r.get("_distance", 0.0)),
            )
            for r in rows
        ]
        if not items:
            return ContextPatch.empty(self.element, self.name)
        return ContextPatch(
            changes={"recalled_memory_append": items},
            source_element=self.element,
            source_technique=self.name,
        )

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        try:
            await self._ensure()
            await self._ingest([item.content])
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "memory.rag store failed (%s): %s", exc.__class__.__name__, exc, exc_info=True
            )
        return ContextPatch.empty(self.element, self.name)
