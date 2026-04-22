"""Integration tests for the Hook system.

We use the mock ModelProvider + planner.react + a local Python tool so the test runs
offline. The hooks themselves are the real ones from `extensibility-hooks`.
"""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime


HOOKED_AGENT = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: hook-demo
    providers:
      - name: mock
        type: mock
        config:
          script:
            - content: "calling reverse_text"
              tool_calls: [{ id: c1, name: reverse_text, arguments: { text: "Aglet" } }]
            - content: "Done"
    models:
      default: mock/anything

    elements:
      perception:
        techniques: [{ name: passthrough }]
      memory:
        techniques: [{ name: sliding_window }]
      planner:
        techniques: [{ name: react, config: { model: default, temperature: 0.0 } }]
      tool:
        techniques:
          - name: local_python
            config:
              tools:
                - name: reverse_text
                  import: aglet_demo_subprocess_tool:_inproc_reverse
                  description: Reverse a string
                  parameters_schema:
                    type: object
                    properties: { text: { type: string } }
      executor:
        techniques: [{ name: sequential }]
      safety:
        techniques: [{ name: budget_only }]
      output:
        techniques: [{ name: streaming_text }]
      observability:
        techniques: [{ name: console, config: { compact: true } }]

    hooks:
      - on: after.tool.invoke
        technique: extensibility.tool_audit
      - on: after.tool.invoke
        technique: extensibility.cost_tracker
        config: { rate_per_call_usd: 0.001 }

    budget: { max_steps: 4 }
    store: { type: memory }
    """
)


# Inject a tiny in-process function under the demo plugin's namespace so the
# local_python tool can resolve `aglet_demo_subprocess_tool:_inproc_reverse`.
import aglet_demo_subprocess_tool as _demo_pkg  # noqa: E402


def _inproc_reverse(text: str) -> str:
    return text[::-1]


_demo_pkg._inproc_reverse = _inproc_reverse  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_hooks_audit_and_cost_tracker_fire_on_tool_invoke(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(HOOKED_AGENT, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    final_chunks: list[str] = []
    seen_run_id: str | None = None
    async for ev in runtime.run("hello"):
        if ev.type == EventType.RUN_STARTED and isinstance(ev.payload, dict):
            seen_run_id = ev.payload["run_id"]
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))

    assert seen_run_id is not None
    rebuilt = await runtime.store.rebuild(seen_run_id, base=_empty_ctx(seen_run_id))

    audit = rebuilt.metadata.get("tool_audit", [])
    assert len(audit) == 1
    assert audit[0]["tool"] == "reverse_text"
    assert audit[0]["outcome"] == "ok"

    # The cost tracker advanced the run's used_cost_usd by 1 * 0.001.
    assert rebuilt.budget.used_cost_usd == pytest.approx(0.001, rel=1e-6)
    assert "".join(final_chunks) == "Done"


@pytest.mark.asyncio
async def test_hook_invalid_pattern_rejected_at_setup(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            schema_version: "1.0"
            name: bad-hook
            elements:
              perception: { techniques: [{ name: passthrough }] }
              planner:    { techniques: [{ name: echo }] }
              output:     { techniques: [{ name: streaming_text }] }
              observability: { techniques: [{ name: console }] }
            hooks:
              - on: not_a_valid_pattern
                technique: extensibility.tool_audit
            store: { type: memory }
            """
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(yaml_path)
    with pytest.raises(ValueError, match="Invalid hook pattern"):
        Runtime.from_config(cfg)


def _empty_ctx(run_id: str):
    from aglet.budget import Budget
    from aglet.context import AgentContext, RawInput

    return AgentContext(run_id=run_id, raw_input=RawInput(), budget=Budget())
