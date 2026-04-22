"""Integration test: spawn the demo subprocess plugin and route a tool call to it."""

from __future__ import annotations

import asyncio
import sys

import pytest

from aglet.loader.subprocess import load_subprocess_plugin


@pytest.mark.asyncio
async def test_subprocess_plugin_spawn_invoke_shutdown():
    # Use the same Python interpreter so workspace deps are visible.
    rt, proxies = await load_subprocess_plugin(
        [sys.executable, "-m", "aglet_demo_subprocess_tool"]
    )
    try:
        assert len(proxies) == 1
        proxy = proxies[0]
        assert proxy.element == "tool"
        assert proxy.name == "reverse"

        # The Tool exposes a single 'reverse_text' tool.
        specs = await proxy.list()
        assert [s.name for s in specs] == ["reverse_text"]
        assert specs[0].technique == "reverse"

        # Invoke it and verify cross-process round-trip.
        result = await proxy.invoke("reverse_text", {"text": "hello"})
        assert result.error is None
        assert result.output == "olleh"

        # Health check.
        h = await proxy.health()
        assert h.healthy
    finally:
        await rt.shutdown()


@pytest.mark.asyncio
async def test_runtime_loads_subprocess_plugin_via_external_plugins(tmp_path):
    """The Runtime auto-bootstraps subprocess plugins declared under external_plugins."""
    import textwrap

    from aglet.config import load_agent_config
    from aglet.events import EventType
    from aglet.runtime import Runtime

    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            f"""\
            schema_version: "1.0"
            name: subprocess-tool-agent
            providers:
              - name: mock
                type: mock
                config:
                  script:
                    - content: "use tool"
                      tool_calls: [{{ id: c1, name: reverse_text, arguments: {{ text: "abc" }} }}]
                    - content: "Final"
            models:
              default: mock/anything

            external_plugins:
              - name: reverse-tool
                runtime: subprocess
                command: ["{sys.executable}", "-m", "aglet_demo_subprocess_tool"]
                components:
                  - {{ element: tool, name: reverse, capabilities: [list, invoke] }}

            elements:
              perception: {{ techniques: [{{ name: passthrough }}] }}
              memory:     {{ techniques: [{{ name: sliding_window }}] }}
              planner:    {{ techniques: [{{ name: react, config: {{ model: default, temperature: 0.0 }} }}] }}
              tool:       {{ techniques: [{{ name: reverse }}] }}
              executor:   {{ techniques: [{{ name: sequential }}] }}
              safety:     {{ techniques: [{{ name: budget_only }}] }}
              output:     {{ techniques: [{{ name: streaming_text }}] }}
              observability: {{ techniques: [{{ name: console, config: {{ compact: true }} }}] }}

            budget: {{ max_steps: 4 }}
            store:  {{ type: memory }}
            """
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    tool_outputs: list[object] = []
    final_chunks: list[str] = []
    async for ev in runtime.run("reverse abc please"):
        if ev.type == EventType.TOOL_RESULT and isinstance(ev.payload, dict):
            tool_outputs.append(ev.payload.get("output"))
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))

    # 'cba' is the reversal of 'abc', proving the subprocess executed the tool.
    assert tool_outputs == ["cba"]
    assert "".join(final_chunks) == "Final"

    # Tear down the subprocess to avoid lingering zombies.
    for rt in runtime._external_runtimes:
        await rt.shutdown()
