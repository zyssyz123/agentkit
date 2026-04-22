"""Plugin SDK — helper that 3rd-party subprocess plugins use to expose Components.

A plugin process typically boils down to::

    from aglet.plugin_sdk import PluginServer, register

    @register(element="tool", name="weather")
    class WeatherTool:
        capabilities = ("list", "invoke")
        version = "0.1.0"
        async def list(self):
            return [{"name": "get_temp", "description": "Get temperature for a city",
                     "parameters_schema": {"type": "object", "properties": {"city": {"type": "string"}}}}]
        async def invoke(self, name, arguments):
            return {"call_id": "", "output": f"22C in {arguments['city']}", "error": None, "latency_ms": 10}

    if __name__ == "__main__":
        PluginServer().serve_stdio()

The server speaks the wire protocol documented in
:mod:`aglet.loader.subprocess` so it interoperates with Aglet's
``SubprocessPluginRuntime`` out of the box.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

# Module-level registry for ``@register(...)`` style declarations.
_DECLARED: list[dict[str, Any]] = []


def register(*, element: str, name: str):
    """Class decorator: declare a Component this plugin process exposes."""

    def _wrap(cls: type):
        _DECLARED.append({"element": element, "name": name, "cls": cls})
        return cls

    return _wrap


@dataclass
class _ComponentRecord:
    element: str
    name: str
    instance: Any
    capabilities: list[str] = field(default_factory=list)
    version: str = "0.0.0"


class PluginServer:
    """JSON-RPC server speaking Aglet's subprocess wire protocol over stdio."""

    def __init__(self, components: list[Any] | None = None) -> None:
        self._records: dict[str, _ComponentRecord] = {}
        if components is None:
            for decl in _DECLARED:
                self._add(decl["element"], decl["name"], decl["cls"]())
        else:
            for inst in components:
                self._add(getattr(inst, "element"), getattr(inst, "name"), inst)

    def _add(self, element: str, name: str, instance: Any) -> None:
        qualified = f"{element}.{name}"
        self._records[qualified] = _ComponentRecord(
            element=element,
            name=name,
            instance=instance,
            capabilities=list(getattr(instance, "capabilities", [])),
            version=str(getattr(instance, "version", "0.0.0")),
        )

    # ------------------------------------------------------------------

    def serve_stdio(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        # Send the ready notification.
        self._write({"jsonrpc": "2.0", "method": "ready", "params": {"schema_version": "1.0"}})
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                raw = await reader.readline()
            except Exception:  # noqa: BLE001
                break
            if not raw:
                break
            line = raw.decode().strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            await self._handle(msg)

    async def _handle(self, msg: dict[str, Any]) -> None:
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}

        try:
            if method == "list_components":
                result = [
                    {
                        "name": r.name if "." in r.name else f"{r.element}.{r.name}",
                        "element": r.element,
                        "capabilities": r.capabilities,
                        "version": r.version,
                    }
                    for r in self._records.values()
                ]
                self._reply(msg_id, result)
                return

            if method == "shutdown":
                self._reply(msg_id, {"ok": True})
                # Allow time for the line to flush before the process exits.
                await asyncio.sleep(0.01)
                sys.exit(0)

            if method == "invoke":
                qualified = params["component"]
                method_name = params["method"]
                args = params.get("args", {}) or {}
                rec = self._records.get(qualified) or self._records.get(
                    qualified.split(".", 1)[-1]
                )
                if rec is None:
                    self._error(msg_id, -32601, f"unknown component {qualified!r}")
                    return
                func = getattr(rec.instance, method_name, None)
                if func is None:
                    self._error(
                        msg_id, -32601, f"component {qualified!r} has no method {method_name!r}"
                    )
                    return
                if inspect.iscoroutinefunction(func):
                    result = await func(**args)
                else:
                    result = await asyncio.to_thread(lambda: func(**args))
                self._reply(msg_id, result)
                return

            self._error(msg_id, -32601, f"method not found: {method}")
        except Exception as exc:  # noqa: BLE001
            self._error(msg_id, -32000, f"{exc.__class__.__name__}: {exc}")

    # ------------------------------------------------------------------

    def _reply(self, msg_id: Any, result: Any) -> None:
        if msg_id is None:
            return
        self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _error(self, msg_id: Any, code: int, message: str) -> None:
        if msg_id is None:
            return
        self._write({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})

    @staticmethod
    def _write(payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()


__all__ = ["PluginServer", "register"]
