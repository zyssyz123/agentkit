"""End-to-end test for planner.reflexion using the mock model provider.

The mock provider is scripted to:
  1. (inner.react) emit a *bad* answer.
  2. (critic)      respond REVISE with a memo.
  3. (inner.react) emit a *good* answer.
  4. (critic)      respond OK.
"""

from __future__ import annotations

import textwrap

import pytest

from agentkit.config import load_agent_config
from agentkit.events import EventType
from agentkit.runtime import Runtime


YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: reflexion-mock
    providers:
      - name: mock
        type: mock
        config:
          script:
            - content: "Bad answer."
            - content: "REVISE: be more specific please"
            - content: "Better answer."
            - content: "OK"
    models:
      default: mock/anything

    elements:
      perception: { techniques: [{ name: passthrough }] }
      memory:     { techniques: [{ name: sliding_window }] }
      planner:
        techniques:
          - name: reflexion
            config:
              inner: react
              inner_config: { model: default, temperature: 0.0 }
              critic_model: default
              max_reflections: 1
      executor:   { techniques: [{ name: sequential }] }
      safety:     { techniques: [{ name: budget_only }] }
      output:     { techniques: [{ name: streaming_text }] }
      observability: { techniques: [{ name: console, config: { compact: true } }] }

    budget: { max_steps: 4 }
    store:  { type: memory }
    """
)


@pytest.mark.asyncio
async def test_reflexion_revises_bad_answer(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(YAML, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    final_chunks: list[str] = []
    saw_revision = False
    async for ev in runtime.run("question"):
        if (
            ev.type == EventType.PLANNER_THOUGHT
            and isinstance(ev.payload, dict)
            and "reflection" in ev.payload
        ):
            saw_revision = True
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))

    assert saw_revision, "Reflexion should have emitted a critique event"
    # Last final answer wins → should be the second (improved) one.
    assert "".join(final_chunks) == "Better answer."
