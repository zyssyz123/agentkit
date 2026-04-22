"""Integration test: spin up the demo HTTP plugin in-process via TestClient and route
through the HttpRuntime."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from aglet.loader.http import HttpPluginRuntime, load_http_plugin


class _AsgiTransportRuntime(HttpPluginRuntime):
    """Override the inner httpx client to use ASGITransport against the demo app
    (so we can test without binding to a real port)."""

    def __init__(self, app, base_url: str = "http://test") -> None:
        super().__init__(base_url=base_url)
        self._app = app

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url=self.base_url,
                timeout=self.timeout_s,
            )
        return self._client


@pytest.mark.asyncio
async def test_http_plugin_list_and_invoke():
    from aglet_demo_http_tool import build_app

    rt = _AsgiTransportRuntime(build_app())
    components = await rt.list_components()
    assert any(c["element"] == "tool" and c["name"] == "tool.shout" for c in components)

    proxy = rt.build_proxy(components[0])
    specs = await proxy.list()
    assert specs and specs[0].name == "shout"

    result = await proxy.invoke("shout", {"text": "hello"})
    assert result.error is None
    assert result.output == "HELLO!!!"

    health = await proxy.health()
    assert health.healthy

    await rt.shutdown()
