"""End-to-end M2 test that exercises planner.react + tool.local_python + executor.sequential
using the mock ModelProvider, so it runs offline in CI."""

from __future__ import annotations

import textwrap

import pytest

from agentkit.config import load_agent_config
from agentkit.events import EventType
from agentkit.runtime import Runtime


AGENT_YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: react-mock-agent
    description: Mock ReAct loop for CI.

    providers:
      - name: mock
        type: mock
        config:
          script:
            - content: "Need current time."
              tool_calls:
                - id: call_1
                  name: now_iso
                  arguments: {}
            - content: "Done."
              # no tool_calls -> final answer

    models:
      default: mock/anything

    elements:
      perception:
        techniques:
          - name: passthrough
      memory:
        techniques:
          - name: sliding_window
      planner:
        techniques:
          - name: react
            config:
              model: default
              temperature: 0.0
      tool:
        techniques:
          - name: local_python
            config:
              tools:
                - name: now_iso
                  import: agentkit_builtin_tool_local_python.demo:now_iso
                  description: Current UTC time.
                  parameters_schema:
                    type: object
                    properties: {}
      executor:
        techniques:
          - name: sequential
      safety:
        techniques:
          - name: budget_only
      output:
        techniques:
          - name: streaming_text
      observability:
        techniques:
          - name: console
            config: { compact: true }

    budget:
      max_steps: 4
      max_tokens: 5000
      max_seconds: 30
      max_cost_usd: 0.0

    store:
      type: memory
      directory: .agentkit/test-runs
    """
)


@pytest.mark.asyncio
async def test_react_agent_with_mock_provider(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(AGENT_YAML, encoding="utf-8")
    cfg = load_agent_config(yaml_path)

    runtime = Runtime.from_config(cfg)

    seen_types: list[str] = []
    tool_call_names: list[str] = []
    tool_result_outputs: list[object] = []
    final_text_chunks: list[str] = []

    async for ev in runtime.run("what time is it?"):
        seen_types.append(ev.type.value)
        if ev.type == EventType.TOOL_CALL and isinstance(ev.payload, dict):
            tool_call_names.append(ev.payload.get("call", {}).get("name", ""))
        if ev.type == EventType.TOOL_RESULT and isinstance(ev.payload, dict):
            tool_result_outputs.append(ev.payload.get("output"))
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_text_chunks.append(ev.payload.get("text", ""))

    assert EventType.PLANNER_THOUGHT.value in seen_types
    assert EventType.PLANNER_ACTION.value in seen_types
    assert EventType.TOOL_CALL.value in seen_types
    assert EventType.TOOL_RESULT.value in seen_types
    assert EventType.PLANNER_FINAL.value in seen_types
    assert EventType.RUN_COMPLETED.value in seen_types

    assert tool_call_names == ["now_iso"]
    assert tool_result_outputs and isinstance(tool_result_outputs[0], str)
    # Final mock answer was "Done." — streaming_text breaks it into chunks; reassemble.
    assert "".join(final_text_chunks) == "Done."
