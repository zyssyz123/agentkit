"""Verify Runtime.resume() rebuilds context from checkpoints and replays terminal events."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agentkit.config import load_agent_config
from agentkit.events import EventType
from agentkit.runtime import Runtime
from agentkit.store import JsonlContextStore


@pytest.mark.asyncio
async def test_resume_replays_already_completed_run(tmp_path: Path):
    runs_dir = tmp_path / "runs"
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            f"""\
            schema_version: "1.0"
            name: resume-demo
            elements:
              perception:    {{ techniques: [{{ name: passthrough }}] }}
              memory:        {{ techniques: [{{ name: sliding_window }}] }}
              planner:       {{ techniques: [{{ name: echo, config: {{ prefix: "Echo: " }} }}] }}
              safety:        {{ techniques: [{{ name: budget_only }}] }}
              output:        {{ techniques: [{{ name: streaming_text }}] }}
              observability: {{ techniques: [{{ name: console, config: {{ compact: true }} }}] }}
            budget:          {{ max_steps: 3 }}
            store:           {{ type: jsonl, directory: "{runs_dir}" }}
            """
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(yaml_path)

    # First run: produce a checkpoint.
    runtime = Runtime.from_config(cfg)
    captured_run_id: str | None = None
    final_chunks: list[str] = []
    async for ev in runtime.run("hello"):
        if ev.type == EventType.RUN_STARTED and isinstance(ev.payload, dict):
            captured_run_id = ev.payload["run_id"]
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final_chunks.append(ev.payload.get("text", ""))
    assert captured_run_id is not None
    assert "".join(final_chunks) == "Echo: hello"

    # Resume: should replay terminal "run.completed" with resumed=True.
    fresh = Runtime.from_config(cfg)
    seen_types: list[str] = []
    payloads: list[dict] = []
    async for ev in fresh.resume(captured_run_id):
        seen_types.append(ev.type.value)
        if isinstance(ev.payload, dict):
            payloads.append(ev.payload)

    assert "run.completed" in seen_types
    assert payloads and payloads[-1].get("resumed") is True


@pytest.mark.asyncio
async def test_resume_unknown_run_raises(tmp_path: Path):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            f"""\
            schema_version: "1.0"
            name: noop
            elements:
              perception:    {{ techniques: [{{ name: passthrough }}] }}
              planner:       {{ techniques: [{{ name: echo }}] }}
              output:        {{ techniques: [{{ name: streaming_text }}] }}
              observability: {{ techniques: [{{ name: console }}] }}
            store:           {{ type: jsonl, directory: "{tmp_path / 'runs'}" }}
            """
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(yaml_path)
    rt = Runtime.from_config(cfg)
    with pytest.raises(KeyError):
        async for _ in rt.resume("does-not-exist"):
            pass


@pytest.mark.asyncio
async def test_jsonl_store_list_runs(tmp_path: Path):
    store = JsonlContextStore(tmp_path / "runs")
    assert await store.list_runs() == []
    # Force a run by appending a stub patch.
    from agentkit.context import ContextPatch

    await store.append_patch("abc-1", ContextPatch(changes={"metadata": {"k": 1}}))
    await store.append_patch("abc-2", ContextPatch(changes={"metadata": {"k": 2}}))
    runs = await store.list_runs()
    assert set(runs) == {"abc-1", "abc-2"}
