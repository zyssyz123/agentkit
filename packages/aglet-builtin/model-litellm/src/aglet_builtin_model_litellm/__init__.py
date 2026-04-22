"""ModelProvider via LiteLLM — one configuration to talk to 100+ LLMs.

Use this when you want a single provider entry that can dispatch to OpenAI / Anthropic /
Bedrock / Vertex / Cohere / Together / Groq / Ollama / etc. depending on the model id
namespace (e.g. ``anthropic/claude-3-5-sonnet``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from aglet.models import ModelChunk, ModelMessage, ModelResponse, ModelToolCall


class LiteLLMProvider:
    name = "litellm"
    capabilities = frozenset({"chat", "stream", "tool_use", "embed"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.api_base: str | None = cfg.get("api_base")
        self.api_key: str | None = cfg.get("api_key")
        self.timeout_s: float = float(cfg.get("timeout_s", 60.0))
        # Lazily import litellm so the rest of Aglet installs without it.
        import litellm  # noqa: F401  (defer import errors until first use)

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    # ------------------------------------------------------------------

    def _kwargs(self, **extra: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.api_base:
            out["api_base"] = self.api_base
        if self.api_key:
            out["api_key"] = self.api_key
        out["timeout"] = self.timeout_s
        out.update({k: v for k, v in extra.items() if v is not None})
        return out

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
        import litellm

        resp = await litellm.acompletion(
            model=model,
            messages=[_to_dict(m) for m in messages],
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            **self._kwargs(**kwargs),
        )
        choice = resp["choices"][0]
        message = choice["message"]
        tool_calls: tuple[ModelToolCall, ...] = ()
        if message.get("tool_calls"):
            import json

            converted = []
            for tc in message["tool_calls"]:
                fn = tc.get("function", {}) or {}
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_raw": args}
                converted.append(
                    ModelToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args or {})
                )
            tool_calls = tuple(converted)
        return ModelResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=resp.get("usage", {}) or {},
            raw=resp,
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
        import litellm

        stream = await litellm.acompletion(
            model=model,
            messages=[_to_dict(m) for m in messages],
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **self._kwargs(**kwargs),
        )
        async for chunk in stream:
            choice = chunk["choices"][0]
            delta = choice.get("delta", {}) or {}
            yield ModelChunk(
                delta_content=delta.get("content") or "",
                finish_reason=choice.get("finish_reason"),
            )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        import litellm

        resp = await litellm.aembedding(model=model, input=texts, **self._kwargs())
        return [item["embedding"] for item in resp["data"]]


def _to_dict(m: ModelMessage) -> dict[str, Any]:
    import json as _json

    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.name:
        out["name"] = m.name
    if m.tool_call_id:
        out["tool_call_id"] = m.tool_call_id
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": _json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in m.tool_calls
        ]
        if m.role == "assistant" and not m.content:
            out["content"] = None
    return out
