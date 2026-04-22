"""Smoke test for planner.tot using the mock provider."""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime


YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: tot-mock
    providers:
      - name: mock
        type: mock
        config:
          script:
            # 3 candidates, then 3 scores (3, 9, 6) -> branch 1 wins
            - { content: "Candidate A — short" }
            - { content: "Candidate B — best!" }
            - { content: "Candidate C — middle" }
            - { content: "3" }
            - { content: "9" }
            - { content: "6" }
    models:
      default: mock/anything

    elements:
      perception: { techniques: [{ name: passthrough }] }
      memory:     { techniques: [{ name: sliding_window }] }
      planner:
        techniques:
          - name: tot
            config:
              branches: 3
              generator_model: default
              evaluator_model: default
              generator_temperature: 0.0
      output:     { techniques: [{ name: streaming_text }] }
      observability: { techniques: [{ name: console, config: { compact: true } }] }

    budget: { max_steps: 3 }
    store:  { type: memory }
    """
)


@pytest.mark.asyncio
async def test_tot_picks_highest_scoring_branch(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(YAML, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    final_chunks: list[str] = []
    selected_branch: int | None = None
    async for ev in runtime.run("question"):
        if (
            ev.type == EventType.PLANNER_THOUGHT
            and isinstance(ev.payload, dict)
            and "selected_branch" in ev.payload
        ):
            selected_branch = ev.payload["selected_branch"]
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))

    assert selected_branch == 1
    assert "".join(final_chunks) == "Candidate B — best!"
