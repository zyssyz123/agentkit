"""tool.http_openapi — call HTTP endpoints as Tools.

M1 supports inline endpoint declarations only::

    config:
      base_url: https://api.example.com
      endpoints:
        - name: get_user
          method: GET
          path: /users/{id}
          parameters_schema:
            type: object
            properties:
              id: { type: string }

OpenAPI document parsing arrives in M2.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from agentkit.context import ToolResult, ToolSpec


class HttpOpenApiTool:
    name = "http_openapi"
    element = "tool"
    version = "0.1.0"
    capabilities = frozenset({"list", "invoke"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.base_url: str = cfg.get("base_url", "")
        self.timeout_s: float = float(cfg.get("timeout_s", 30.0))
        self._endpoints: dict[str, dict[str, Any]] = {
            ep["name"]: ep for ep in cfg.get("endpoints", [])
        }

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def list(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=ep["name"],
                description=ep.get("description", f"{ep['method']} {ep['path']}"),
                parameters_schema=ep.get(
                    "parameters_schema",
                    {"type": "object", "properties": {}, "additionalProperties": True},
                ),
                technique=self.name,
            )
            for ep in self._endpoints.values()
        ]

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        ep = self._endpoints.get(name)
        if ep is None:
            return ToolResult(call_id="", output=None, error=f"unknown endpoint: {name}")

        method = ep["method"].upper()
        path = ep["path"].format(**arguments)
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/") if self.base_url else path

        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                if method in ("GET", "DELETE"):
                    resp = await client.request(method, url, params=arguments)
                else:
                    resp = await client.request(method, url, json=arguments)
            try:
                payload = resp.json()
            except Exception:  # noqa: BLE001
                payload = resp.text
            return ToolResult(
                call_id="",
                output={"status": resp.status_code, "body": payload},
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                call_id="",
                output=None,
                error=f"{exc.__class__.__name__}: {exc}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )
