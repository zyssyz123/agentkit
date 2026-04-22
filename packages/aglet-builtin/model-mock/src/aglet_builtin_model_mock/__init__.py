"""Mock ModelProvider — deterministic responses for tests / CI / offline demos.

Config schema::

    type: mock
    config:
      # A scripted sequence; each entry is a complete ModelResponse.
      script:
        - content: "Thought: I should call the echo tool."
          tool_calls:
            - name: echo
              arguments: {text: "hi"}
        - content: "Final: hi"
      # Or a fixed completion if `script` is omitted.
      content: "I am a mock LLM."
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from aglet.models import ModelChunk, ModelMessage, ModelResponse, ModelToolCall


class MockProvider:
    name = "mock"
    capabilities = frozenset({"chat", "stream", "tool_use", "embed"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._script: list[dict[str, Any]] = list(cfg.get("script", []))
        self._fallback: str = cfg.get("content", "")
        self._embedding_dim: int = int(cfg.get("embedding_dim", 8))
        self._cursor = 0

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    def reset(self) -> None:
        self._cursor = 0

    def _next(self) -> dict[str, Any]:
        if self._script:
            entry = self._script[min(self._cursor, len(self._script) - 1)]
            self._cursor += 1
            return entry
        return {"content": self._fallback}

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        entry = self._next()
        tool_calls = tuple(
            ModelToolCall(
                id=tc.get("id", f"call_{i}"),
                name=tc["name"],
                arguments=tc.get("arguments", {}),
            )
            for i, tc in enumerate(entry.get("tool_calls", []) or [])
        )
        return ModelResponse(
            content=entry.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=entry.get("finish_reason", "tool_calls" if tool_calls else "stop"),
        )

    async def stream(
        self,
        model: str,
        messages: list[ModelMessage],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelChunk]:
        entry = self._next()
        text = entry.get("content", "")
        for ch in text:
            yield ModelChunk(delta_content=ch)
        yield ModelChunk(finish_reason="stop")

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        # Deterministic, low-quality "hash embedding" useful for tests.
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._embedding_dim
            for i, ch in enumerate(text.encode("utf-8")):
                vec[i % self._embedding_dim] += float(ch) / 255.0
            out.append(vec)
        return out
