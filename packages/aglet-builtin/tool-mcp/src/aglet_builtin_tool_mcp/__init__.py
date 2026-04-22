"""tool.mcp — adopt one or more MCP servers as Aglet Tools (stdio transport, M2).

Config schema::

    type: mcp
    config:
      servers:
        - name: filesystem
          command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
          env: { LOG_LEVEL: info }
        - name: fetch
          command: ["npx", "-y", "@modelcontextprotocol/server-fetch"]

Each server's tools are exposed as ``<server_name>__<tool_name>`` to avoid name clashes.

SSE / Streamable-HTTP transports are tracked for M3.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack
from typing import Any

from aglet.context import ToolResult, ToolSpec

log = logging.getLogger(__name__)


class _ServerSession:
    def __init__(self, name: str, command: list[str], env: dict[str, str] | None) -> None:
        self.name = name
        self.command = command
        self.env = env or None
        self._stack: AsyncExitStack | None = None
        self.session: Any = None  # mcp.ClientSession
        self._tools_cache: list[ToolSpec] = []

    async def connect(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        params = StdioServerParameters(
            command=self.command[0],
            args=self.command[1:],
            env=self.env,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    async def list_tools(self) -> list[ToolSpec]:
        if self._tools_cache:
            return self._tools_cache
        result = await self.session.list_tools()
        out: list[ToolSpec] = []
        for tool in result.tools:
            qualified = f"{self.name}__{tool.name}"
            out.append(
                ToolSpec(
                    name=qualified,
                    description=tool.description or "",
                    parameters_schema=tool.inputSchema or {"type": "object", "properties": {}},
                    technique="mcp",
                )
            )
        self._tools_cache = out
        return out

    async def call_tool(self, raw_name: str, arguments: dict[str, Any]) -> Any:
        return await self.session.call_tool(raw_name, arguments)


class McpTool:
    name = "mcp"
    element = "tool"
    version = "0.1.0"
    capabilities = frozenset({"list", "invoke"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._servers: list[_ServerSession] = []
        for entry in cfg.get("servers", []):
            self._servers.append(
                _ServerSession(
                    name=entry["name"],
                    command=list(entry["command"]),
                    env=entry.get("env"),
                )
            )
        self._connected = False
        self._connect_lock = asyncio.Lock()

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        for srv in self._servers:
            try:
                await srv.close()
            except Exception:  # noqa: BLE001
                pass

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=self._connected)

    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        async with self._connect_lock:
            if self._connected:
                return
            for srv in self._servers:
                try:
                    await srv.connect()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Failed to connect MCP server %s: %s", srv.name, exc)
            self._connected = True

    async def list(self) -> list[ToolSpec]:
        await self._ensure_connected()
        out: list[ToolSpec] = []
        for srv in self._servers:
            try:
                out.extend(await srv.list_tools())
            except Exception as exc:  # noqa: BLE001
                log.warning("MCP server %s list_tools failed: %s", srv.name, exc)
        return out

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        await self._ensure_connected()
        server_name, _, raw_name = name.partition("__")
        if not raw_name:
            return ToolResult(
                call_id="",
                output=None,
                error=f"MCP tool name '{name}' must be of form '<server>__<tool>'",
            )
        srv = next((s for s in self._servers if s.name == server_name), None)
        if srv is None:
            return ToolResult(
                call_id="", output=None, error=f"unknown MCP server: {server_name}"
            )
        started = time.monotonic()
        try:
            result = await srv.call_tool(raw_name, arguments)
            content = _flatten_mcp_content(result)
            return ToolResult(
                call_id="",
                output=content,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                call_id="",
                output=None,
                error=f"{exc.__class__.__name__}: {exc}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )


def _flatten_mcp_content(call_result: Any) -> Any:
    """Best-effort conversion of an MCP CallToolResult to a JSON-friendly value."""
    parts = getattr(call_result, "content", None) or []
    out: list[Any] = []
    for part in parts:
        kind = getattr(part, "type", None)
        if kind == "text":
            out.append(getattr(part, "text", ""))
        elif kind == "image":
            out.append({"image": getattr(part, "data", ""), "mimeType": getattr(part, "mimeType", "")})
        else:
            out.append(repr(part))
    if len(out) == 1:
        return out[0]
    return out
