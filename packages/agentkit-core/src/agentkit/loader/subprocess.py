"""Subprocess plugin runtime — out-of-process Techniques over JSON-RPC 2.0 stdio.

Wire protocol
-------------

Bidirectional newline-delimited JSON. Client (AgentKit Runtime) initiates calls;
server (plugin process) responds.

Initial handshake from server when ready::

    {"jsonrpc": "2.0", "method": "ready", "params": {"schema_version": "1.0"}}

Methods (client → server):

* ``list_components``                                 → list of component descriptors
* ``invoke(component, method, args)``                 → JSON-encoded result
* ``stream(component, method, args)``                 → not implemented in M3
* ``shutdown``                                        → server should exit gracefully

Error responses follow JSON-RPC 2.0 error format.

Why dict-only?
--------------

Plugins receive lossy dict snapshots of AgentContext (see ``agentkit.serialize``).
This is good enough for common Tool / Memory / Safety techniques and avoids forcing
plugins to import the full AgentKit Python types — which keeps subprocess plugins
language-agnostic in the future.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

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


# ---------- low-level JSON-RPC client --------------------------------------------------------


@dataclass
class _RpcClient:
    """Async newline-JSON client speaking to a child process over stdio."""

    command: list[str]
    env: dict[str, str] | None = None
    cwd: str | None = None

    process: asyncio.subprocess.Process | None = None
    _reader_task: asyncio.Task | None = None
    _pending: dict[str, asyncio.Future] = field(default_factory=dict)
    _ready: asyncio.Event = field(default_factory=asyncio.Event)
    _started_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def start(self) -> None:
        async with self._started_lock:
            if self.process is not None:
                return
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **(self.env or {})},
                cwd=self.cwd,
            )
            self._reader_task = asyncio.create_task(self._reader_loop())
            try:
                await asyncio.wait_for(self._ready.wait(), timeout=20.0)
            except asyncio.TimeoutError:
                stderr = await self._drain_stderr()
                raise RuntimeError(
                    f"Subprocess plugin {self.command!r} did not send 'ready' within 20s. "
                    f"stderr:\n{stderr}"
                )

    async def _drain_stderr(self) -> str:
        if self.process is None or self.process.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(self.process.stderr.read(4096), timeout=0.5)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            return ""
        return data.decode(errors="replace")

    async def _reader_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        async for raw in self.process.stdout:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                log.warning("plugin sent non-JSON line: %r", line[:200])
                continue
            method = msg.get("method")
            if method == "ready":
                self._ready.set()
                continue
            msg_id = msg.get("id")
            if msg_id is None:
                # Notification (e.g. log message). Ignore for now.
                continue
            fut = self._pending.pop(msg_id, None)
            if fut is None:
                continue
            if "error" in msg and msg["error"]:
                err = msg["error"]
                fut.set_exception(
                    RuntimeError(
                        f"plugin error {err.get('code')}: {err.get('message')}"
                    )
                )
            else:
                fut.set_result(msg.get("result"))
        # Reader exited — notify all pending callers.
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(
                    RuntimeError("plugin process exited while RPC was pending")
                )

    async def call(self, method: str, params: dict | None = None, *, timeout: float = 30.0) -> Any:
        await self.start()
        assert self.process is not None and self.process.stdin is not None
        msg_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[msg_id] = fut
        line = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
                "params": params or {},
            },
            ensure_ascii=False,
        )
        self.process.stdin.write((line + "\n").encode())
        await self.process.stdin.drain()
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

    async def stop(self) -> None:
        if self.process is None:
            return
        try:
            await self.call("shutdown", timeout=2.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.process.terminate()
            await asyncio.wait_for(self.process.wait(), timeout=3.0)
        except Exception:  # noqa: BLE001
            try:
                self.process.kill()
            except Exception:  # noqa: BLE001
                pass


# ---------- runtime + factory ----------------------------------------------------------------


class SubprocessPluginRuntime:
    """Owns one subprocess; produces Technique proxies for the components it ships."""

    name = "subprocess"

    def __init__(self, command: str | list[str], env: dict[str, str] | None = None) -> None:
        if isinstance(command, str):
            command = shlex.split(command)
        self.client = _RpcClient(command=list(command), env=env)
        self._cached_components: list[dict] | None = None

    async def list_components(self) -> list[dict]:
        if self._cached_components is None:
            self._cached_components = await self.client.call("list_components")
        return self._cached_components

    async def shutdown(self) -> None:
        await self.client.stop()

    # --- factory methods -----------------------------------------------------------------------

    def build_proxy(self, component: dict) -> Any:
        element = component["element"]
        builder = _PROXY_BUILDERS.get(element)
        if builder is None:
            raise ValueError(
                f"Subprocess plugin component for unknown Element {element!r}; "
                f"M3 supports: {sorted(_PROXY_BUILDERS)}"
            )
        return builder(self.client, component)


# ---------- per-Element proxy classes ---------------------------------------------------------


class _BaseProxy:
    """Common scaffolding shared by every remote Technique proxy."""

    def __init__(self, client: _RpcClient, component: dict) -> None:
        self._client = client
        self._id = component["name"]  # qualified-by-element on the server side
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
            data = await self._client.call(
                "invoke",
                {"component": self._id, "method": "health", "args": {}},
                timeout=3.0,
            )
            return HealthStatus(
                healthy=bool((data or {}).get("healthy", True)),
                detail=str((data or {}).get("detail", "")),
            )
        except Exception as exc:  # noqa: BLE001
            return HealthStatus(healthy=False, detail=str(exc))

    async def _invoke(self, method: str, args: dict) -> Any:
        return await self._client.call(
            "invoke",
            {"component": self._id, "method": method, "args": args},
        )


class _ToolProxy(_BaseProxy):
    async def list(self) -> list[ToolSpec]:
        data = await self._invoke("list", {}) or []
        return tool_specs_from_list(data)

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        data = await self._invoke("invoke", {"name": name, "arguments": arguments})
        return tool_result_from_dict(data or {})


class _MemoryProxy(_BaseProxy):
    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        data = await self._invoke(
            "recall",
            {"ctx": context_to_dict(ctx), "query": query},
        )
        return patch_from_dict(data or {})

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        data = await self._invoke(
            "store",
            {"ctx": context_to_dict(ctx), "item": memory_item_to_dict(item)},
        )
        return patch_from_dict(data or {})


class _PerceptionProxy(_BaseProxy):
    async def parse(self, ctx: AgentContext) -> ContextPatch:
        data = await self._invoke("parse", {"ctx": context_to_dict(ctx)})
        return patch_from_dict(data or {})


class _SafetyProxy(_BaseProxy):
    async def pre_check(self, ctx: AgentContext) -> None:
        await self._invoke("pre_check", {"ctx": context_to_dict(ctx)})

    async def post_check(self, ctx: AgentContext) -> None:
        await self._invoke("post_check", {"ctx": context_to_dict(ctx)})

    async def wrap_tool(self, call: ToolCall) -> ToolCall:
        data = await self._invoke(
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
    "tool": _ToolProxy,
    "memory": _MemoryProxy,
    "perception": _PerceptionProxy,
    "safety": _SafetyProxy,
}


# ---------- factory entry-point used by Plugin loader ----------------------------------------


async def load_subprocess_plugin(
    command: str | list[str],
    env: dict[str, str] | None = None,
) -> tuple[SubprocessPluginRuntime, list[Any]]:
    """Spawn the plugin process, list its components and build proxies for each.

    Returns the runtime handle plus the list of proxy instances so the caller can
    register them with the global :class:`agentkit.registry.Registry`.
    """
    rt = SubprocessPluginRuntime(command=command, env=env)
    components = await rt.list_components()
    proxies = [rt.build_proxy(c) for c in components]
    return rt, proxies


__all__ = [
    "SubprocessPluginRuntime",
    "load_subprocess_plugin",
]
