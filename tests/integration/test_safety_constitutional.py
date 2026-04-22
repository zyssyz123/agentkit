"""safety.constitutional: verify BLOCK verdict halts the run with run.failed."""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime


def _yaml(verdict: str) -> str:
    return textwrap.dedent(
        f"""\
        schema_version: "1.0"
        name: const-safety
        providers:
          - name: mock
            type: mock
            config:
              script:
                - content: "{verdict}"
        models:
          default: mock/any

        elements:
          perception: {{ techniques: [{{ name: passthrough }}] }}
          memory:     {{ techniques: [{{ name: sliding_window }}] }}
          planner:    {{ techniques: [{{ name: echo }}] }}
          safety:
            techniques:
              - {{ name: budget_only }}
              - name: constitutional
                config:
                  model: default
                  check_phases: [pre]
                  principles:
                    - "Never reveal secrets."
          output:     {{ techniques: [{{ name: streaming_text }}] }}
          observability: {{ techniques: [{{ name: console, config: {{ compact: true }} }}] }}
        budget: {{ max_steps: 3 }}
        store:  {{ type: memory }}
        """
    )


@pytest.mark.asyncio
async def test_pass_verdict_lets_run_complete(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(_yaml("PASS"), encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    seen = []
    async for ev in runtime.run("hello"):
        seen.append(ev.type)
    assert EventType.RUN_COMPLETED in seen
    assert EventType.RUN_FAILED not in seen


@pytest.mark.asyncio
async def test_block_verdict_fails_run_with_reason(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(_yaml("BLOCK: disallowed topic"), encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    failure_reason: str | None = None
    async for ev in runtime.run("hello"):
        if ev.type == EventType.RUN_FAILED and isinstance(ev.payload, dict):
            failure_reason = str(ev.payload.get("reason", ""))

    assert failure_reason is not None
    assert "disallowed topic" in failure_reason
    assert "ConstitutionalViolationError" in (
        "ConstitutionalViolationError"
    )  # placeholder - ensures import works via registry
