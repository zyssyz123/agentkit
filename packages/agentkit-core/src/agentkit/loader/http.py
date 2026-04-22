"""HTTP plugin runtime — wraps a remote HTTP service as a set of Technique proxies.

Wire protocol
-------------

The remote server must implement two endpoints::

    GET  /list_components
        → 200 OK
          [{"name": "...", "element": "tool", "capabilities": [...], "version": "..."},
           ...]

    POST /invoke
        body: {"component": "<name>", "method": "<method>", "args": {...}}
        → 200 OK with the method's JSON-encoded result, OR
          4xx / 5xx with {"error": {"code": ..., "message": "..."}}

This is intentionally simpler than JSON-RPC stdio so that an HTTP plugin can be
implemented in any language with a tiny FastAPI / Express / Gin handler.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agentkit.context import AgentContext, ContextPatch, MemoryItem, ToolCall, ToolResult, ToolSpec
from agentkit.protocols import HealthStatus
from agentkit.serialize import (
    context_to_dict,
    memory_item_to_dict,
    patch_from_dict,
    tool_result_from_dict,
    tool_specs_from_list,
)

log = logging.getLogger(__name__)


class HttpPluginRuntime:
    """Talks JSON over HTTP to a remote plugin server."""

    name = "http"

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=self.timeout_s,
            )
        return self._client

    async def list_components(self) -> list[dict]:
        client = await self._http()
        resp = await client.get("/list_components")
        resp.raise_for_status()
        return resp.json()

    async def invoke(self, component: str, method: str, args: dict) -> Any:
        client = await self._http()
        resp = await client.post(
            "/invoke",
            json={"component": component, "method": method, "args": args},
        )
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error") or {}
            except Exception:  # noqa: BLE001
                err = {"message": resp.text}
            raise RuntimeError(
                f"HTTP plugin error {err.get('code', resp.status_code)}: {err.get('message', '')}"
            )
        return resp.json()

    async def shutdown(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def build_proxy(self, component: dict) -> Any:
        element = component["element"]
        builder = _PROXY_BUILDERS.get(element)
        if builder is None:
            raise ValueError(
                f"HTTP plugin component for unknown Element {element!r}; "
                f"M3 supports: {sorted(_PROXY_BUILDERS)}"
            )
        return builder(self, component)


# ---------- per-Element proxies (mirror subprocess.py) -------------------------------------


class _BaseHttpProxy:
    def __init__(self, runtime: HttpPluginRuntime, component: dict) -> None:
        self._rt = runtime
        self._id = component["name"]
        self.name: str = component["name"].split(".", 1)[-1]
        self.element: str = component["element"]
        self.version: str = str(component.get("version", "0.0.0"))
        self.capabilities = frozenset(component.get("capabilities", []))

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self) -> HealthStatus:
        try:
            data = await self._rt.invoke(self._id, "health", {})
            return HealthStatus(
                healthy=bool((data or {}).get("healthy", True)),
                detail=str((data or {}).get("detail", "")),
            )
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(healthy=False, detail=str(exc))


class _ToolHttpProxy(_BaseHttpProxy):
    async def list(self) -> list[ToolSpec]:
        return tool_specs_from_list(await self._rt.invoke(self._id, "list", {}) or [])

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        data = await self._rt.invoke(self._id, "invoke", {"name": name, "arguments": arguments})
        return tool_result_from_dict(data or {})


class _MemoryHttpProxy(_BaseHttpProxy):
    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        data = await self._rt.invoke(
            self._id, "recall", {"ctx": context_to_dict(ctx), "query": query}
        )
        return patch_from_dict(data or {})

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        data = await self._rt.invoke(
            self._id, "store", {"ctx": context_to_dict(ctx), "item": memory_item_to_dict(item)}
        )
        return patch_from_dict(data or {})


class _PerceptionHttpProxy(_BaseHttpProxy):
    async def parse(self, ctx: AgentContext) -> ContextPatch:
        data = await self._rt.invoke(self._id, "parse", {"ctx": context_to_dict(ctx)})
        return patch_from_dict(data or {})


class _SafetyHttpProxy(_BaseHttpProxy):
    async def pre_check(self, ctx: AgentContext) -> None:
        await self._rt.invoke(self._id, "pre_check", {"ctx": context_to_dict(ctx)})

    async def post_check(self, ctx: AgentContext) -> None:
        await self._rt.invoke(self._id, "post_check", {"ctx": context_to_dict(ctx)})

    async def wrap_tool(self, call: ToolCall) -> ToolCall:
        data = await self._rt.invoke(
            self._id,
            "wrap_tool",
            {"call": {"id": call.id, "name": call.name, "arguments": call.arguments}},
        )
        if not data:
            return call
        return ToolCall(
            id=str(data.get("id", call.id)),
            name=str(data.get("name", call.name)),
            arguments=dict(data.get("arguments", call.arguments)),
        )


_PROXY_BUILDERS = {
    "tool": _ToolHttpProxy,
    "memory": _MemoryHttpProxy,
    "perception": _PerceptionHttpProxy,
    "safety": _SafetyHttpProxy,
}


async def load_http_plugin(
    base_url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[HttpPluginRuntime, list[Any]]:
    rt = HttpPluginRuntime(base_url=base_url, headers=headers)
    components = await rt.list_components()
    proxies = [rt.build_proxy(c) for c in components]
    return rt, proxies


__all__ = ["HttpPluginRuntime", "load_http_plugin"]
