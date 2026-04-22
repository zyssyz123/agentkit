"""End-to-end test for planner.workflow — a two-node DAG over a local tool."""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime


YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: workflow-demo
    elements:
      perception: { techniques: [{ name: passthrough }] }
      memory:     { techniques: [{ name: sliding_window }] }
      planner:
        techniques:
          - name: workflow
            config:
              nodes:
                - id: reverse_input
                  tool: rev
                  arguments: { text: "{input}" }
                - id: final
                  final: "reversed:{nodes.reverse_input}"
      tool:
        techniques:
          - name: local_python
            config:
              tools:
                - name: rev
                  import: aglet_demo_subprocess_tool:_inproc_reverse_v2
                  description: Reverse a string
                  parameters_schema:
                    type: object
                    properties: { text: { type: string } }
      executor:   { techniques: [{ name: sequential }] }
      safety:     { techniques: [{ name: budget_only }] }
      output:     { techniques: [{ name: streaming_text }] }
      observability: { techniques: [{ name: console, config: { compact: true } }] }
    budget: { max_steps: 4 }
    store:  { type: memory }
    """
)


# Inject a tiny in-process reverse function under the demo plugin's namespace
# so local_python can resolve it without a separate dist.
import aglet_demo_subprocess_tool as _demo  # noqa: E402


def _inproc_reverse_v2(text: str) -> str:
    return text[::-1]


_demo._inproc_reverse_v2 = _inproc_reverse_v2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_workflow_planner_dispatches_dag_in_order(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(YAML, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    tool_outputs = []
    final_chunks = []
    async for ev in runtime.run("hello"):
        if ev.type == EventType.TOOL_RESULT and isinstance(ev.payload, dict):
            tool_outputs.append(ev.payload.get("output"))
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))

    assert tool_outputs == ["olleh"]
    assert "".join(final_chunks) == "reversed:olleh"
