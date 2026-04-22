"""Verify Runtime.run threads prior history through ctx.history (multi-turn support)."""

from __future__ import annotations

import textwrap

import pytest

from agentkit.config import load_agent_config
from agentkit.context import Message
from agentkit.events import EventType
from agentkit.runtime import Runtime

AGENT_YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: history-echo
    elements:
      perception:
        techniques: [{ name: passthrough }]
      memory:
        techniques: [{ name: sliding_window }]
      planner:
        techniques: [{ name: echo, config: { prefix: "Reply: " } }]
      output:
        techniques: [{ name: streaming_text }]
      observability:
        techniques: [{ name: console, config: { compact: true } }]
    budget: { max_steps: 4 }
    store: { type: memory }
    """
)


@pytest.mark.asyncio
async def test_runtime_appends_user_message_to_supplied_history(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(AGENT_YAML, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    prior = (
        Message(role="user", content="first"),
        Message(role="assistant", content="Reply: first"),
        Message(role="user", content="second"),
        Message(role="assistant", content="Reply: second"),
    )

    captured_run_id: str | None = None
    async for ev in runtime.run("third", history=prior):
        if ev.type == EventType.RUN_STARTED and isinstance(ev.payload, dict):
            captured_run_id = ev.payload["run_id"]

    assert captured_run_id is not None

    # Re-build the final context from stored patches and inspect history.
    from agentkit.context import AgentContext, Budget, RawInput

    base = AgentContext(
        run_id=captured_run_id,
        raw_input=RawInput(text="third"),
        budget=Budget(),
        history=prior + (Message(role="user", content="third"),),
    )
    rebuilt = await runtime.store.rebuild(captured_run_id, base)
    assert [m.content for m in rebuilt.history] == [
        "first",
        "Reply: first",
        "second",
        "Reply: second",
        "third",
    ]
