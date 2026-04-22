"""End-to-end multi-agent test: parent agent invokes a sub-agent via tool.subagent."""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime


SUB_AGENT_YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: child-agent
    elements:
      perception: { techniques: [{ name: passthrough }] }
      planner:    { techniques: [{ name: echo, config: { prefix: "Child: " } }] }
      output:     { techniques: [{ name: streaming_text }] }
      observability: { techniques: [{ name: console, config: { compact: true } }] }
    store: { type: memory }
    """
)


def _parent_yaml(child_path):
    return textwrap.dedent(
        f"""\
        schema_version: "1.0"
        name: parent-agent
        providers:
          - name: mock
            type: mock
            config:
              script:
                - content: "Delegating to child."
                  tool_calls: [{{ id: c1, name: research, arguments: {{ question: "deep dive" }} }}]
                - content: "All done."
        models:
          default: mock/anything

        elements:
          perception: {{ techniques: [{{ name: passthrough }}] }}
          memory:     {{ techniques: [{{ name: sliding_window }}] }}
          planner:    {{ techniques: [{{ name: react, config: {{ model: default, temperature: 0.0 }} }}] }}
          tool:
            techniques:
              - name: subagent
                config:
                  agents:
                    - name: research
                      description: A small child agent
                      path: "{child_path}"
                      input_field: question
          executor:   {{ techniques: [{{ name: sequential }}] }}
          safety:     {{ techniques: [{{ name: budget_only }}] }}
          output:     {{ techniques: [{{ name: streaming_text }}] }}
          observability: {{ techniques: [{{ name: console, config: {{ compact: true }} }}] }}

        budget: {{ max_steps: 4 }}
        store: {{ type: memory }}
        """
    )


@pytest.mark.asyncio
async def test_parent_calls_subagent_via_tool(tmp_path):
    child_path = tmp_path / "child.yaml"
    child_path.write_text(SUB_AGENT_YAML, encoding="utf-8")
    parent_path = tmp_path / "parent.yaml"
    parent_path.write_text(_parent_yaml(child_path), encoding="utf-8")

    cfg = load_agent_config(parent_path)
    runtime = Runtime.from_config(cfg)

    tool_outputs: list[object] = []
    final_chunks: list[str] = []
    async for ev in runtime.run("Investigate X"):
        if ev.type == EventType.TOOL_RESULT and isinstance(ev.payload, dict):
            tool_outputs.append(ev.payload.get("output"))
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))

    # The child's output is "Child: deep dive" — proves the inner agent ran.
    assert tool_outputs == ["Child: deep dive"]
    assert "".join(final_chunks) == "All done."
