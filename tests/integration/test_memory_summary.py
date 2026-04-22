"""memory.summary: verify rolling LLM summarisation kicks in and is recalled."""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime


YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: summary-agent
    providers:
      - name: mock
        type: mock
        config:
          script:
            - content: "USER prefers concise, bulleted answers. Working on refactoring."
            - content: "Acknowledged."
    models:
      default: mock/any

    elements:
      perception: { techniques: [{ name: passthrough }] }
      memory:
        techniques:
          - name: summary
            config: { model: default, trigger_chars: 20, keep_recent: 1 }
      planner:    { techniques: [{ name: echo, config: { prefix: "ok: " } }] }
      output:     { techniques: [{ name: streaming_text }] }
      observability: { techniques: [{ name: console, config: { compact: true } }] }
    budget: { max_steps: 3 }
    store:  { type: memory }
    """
)


@pytest.mark.asyncio
async def test_summary_technique_compresses_and_recalls(tmp_path):
    from aglet.context import Message

    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(YAML, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    runtime = Runtime.from_config(cfg)

    # Feed two turns so the trigger_chars=20 threshold is exceeded.
    history = (
        Message(role="user", content="Build a login form please."),
        Message(role="assistant", content="Sure, what stack?"),
        Message(role="user", content="React + FastAPI."),
        Message(role="assistant", content="Got it."),
    )

    recalled_contents: list[str] = []
    async for ev in runtime.run("Continue", history=history, conversation_id="c1"):
        if ev.type == EventType.MEMORY_RECALLED and ev.patch is not None:
            appended = ev.patch.changes.get("recalled_memory_append") or []
            for item in appended:
                text = getattr(item, "content", "") if hasattr(item, "content") else item.get("content", "")
                recalled_contents.append(text)

    # The mock LLM returned "USER prefers concise...", which should appear in the recall.
    assert any("USER prefers concise" in c for c in recalled_contents), (
        f"expected summary recalled; got {recalled_contents!r}"
    )
