"""ModelProvider for any OpenAI-compatible chat-completions API.

Compatible with:
* OpenAI (default base_url)
* Azure OpenAI (override ``base_url``, ``api_version``, ``deployments``)
* Together / Groq / DeepSeek / Moonshot / Anyscale / vLLM / Ollama-OAI / etc.

Config schema::

    type: openai_compat
    config:
      api_key: ${OPENAI_API_KEY}
      base_url: https://api.openai.com/v1
      timeout_s: 60
      default_headers:
        OpenAI-Beta: assistants=v2
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from agentkit.models import ModelChunk, ModelMessage, ModelResponse, ModelToolCall


class OpenAICompatProvider:
    name = "openai_compat"
    capabilities = frozenset({"chat", "stream", "tool_use", "embed"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.api_key: str = _resolve(cfg.get("api_key", "${OPENAI_API_KEY}"))
        self.base_url: str = cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
        self.timeout_s: float = float(cfg.get("timeout_s", 60.0))
        self.default_headers: dict[str, str] = dict(cfg.get("default_headers", {}))

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None

    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        h.update(self.default_headers)
        return h

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
        body: dict[str, Any] = {
            "model": model,
            "messages": [_msg_to_openai(m) for m in messages],
            "temperature": temperature,
            **{k: v for k, v in kwargs.items() if v is not None},
        }
        if tools:
            body["tools"] = tools
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=body, headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        message = choice.get("message", {})
        return ModelResponse(
            content=message.get("content") or "",
            tool_calls=tuple(_tc_from_openai(tc) for tc in (message.get("tool_calls") or ())),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
            raw=data,
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
        body: dict[str, Any] = {
            "model": model,
            "messages": [_msg_to_openai(m) for m in messages],
            "temperature": temperature,
            "stream": True,
            **{k: v for k, v in kwargs.items() if v is not None},
        }
        if tools:
            body["tools"] = tools
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
                headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if not payload or payload == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    yield ModelChunk(
                        delta_content=delta.get("content") or "",
                        finish_reason=choice.get("finish_reason"),
                    )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": model, "input": texts},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]


# ---------- helpers ---------------------------------------------------------------------------


def _resolve(value: str) -> str:
    """Expand ``${ENV_VAR}`` shells in config values lazily."""
    if value.startswith("${") and value.endswith("}"):
        env = value[2:-1]
        return os.environ.get(env, "")
    return value


def _msg_to_openai(m: ModelMessage) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.name:
        out["name"] = m.name
    if m.tool_call_id:
        out["tool_call_id"] = m.tool_call_id
    return out


def _tc_from_openai(tc: dict[str, Any]) -> ModelToolCall:
    fn = tc.get("function", {}) or {}
    args = fn.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {"_raw": args}
    return ModelToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args or {})
