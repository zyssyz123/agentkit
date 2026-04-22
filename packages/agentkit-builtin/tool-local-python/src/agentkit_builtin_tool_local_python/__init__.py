"""tool.local_python — turn local Python callables into invokable AgentKit Tools.

Config schema::

    config:
      tools:
        - name: echo
          import: "agentkit_builtin_tool_local_python.demo:echo"
          description: "Return the input verbatim"
          parameters_schema:
            type: object
            properties:
              text: { type: string }
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable

from agentkit.context import ToolResult, ToolSpec


@dataclass
class _Registered:
    spec: ToolSpec
    func: Callable[..., Any]


class LocalPythonTool:
    name = "local_python"
    element = "tool"
    version = "0.1.0"
    capabilities = frozenset({"list", "invoke"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._tools: dict[str, _Registered] = {}
        for entry in cfg.get("tools", []):
            self._add_from_dict(entry)

    # ------------------------------------------------------------------

    def _add_from_dict(self, entry: dict[str, Any]) -> None:
        name = entry["name"]
        dotted = entry["import"]
        module_path, _, attr = dotted.partition(":")
        if not attr:
            module_path, attr = dotted.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, attr)
        spec = ToolSpec(
            name=name,
            description=entry.get("description", func.__doc__ or ""),
            parameters_schema=entry.get(
                "parameters_schema",
                {"type": "object", "properties": {}, "additionalProperties": True},
            ),
            technique=self.name,
        )
        self._tools[name] = _Registered(spec=spec, func=func)

    # ------------------------------------------------------------------

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def list(self) -> list[ToolSpec]:
        return [reg.spec for reg in self._tools.values()]

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        reg = self._tools.get(name)
        if reg is None:
            return ToolResult(call_id="", output=None, error=f"unknown tool: {name}")
        started = time.monotonic()
        try:
            if inspect.iscoroutinefunction(reg.func):
                output = await reg.func(**arguments)
            else:
                output = await asyncio.to_thread(reg.func, **arguments)
            return ToolResult(
                call_id="",
                output=output,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                call_id="",
                output=None,
                error=f"{exc.__class__.__name__}: {exc}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
