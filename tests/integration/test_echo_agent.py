"""End-to-end smoke test for the M1 skeleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.runtime import Runtime

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "echo-agent"


@pytest.mark.asyncio
async def test_echo_agent_end_to_end(tmp_path):
    cfg = load_agent_config(EXAMPLE_DIR / "agent.yaml")
    # Redirect store + jsonl observability into a temp dir to keep tests hermetic.
    cfg.store.directory = str(tmp_path / "runs")
    for tech in cfg.elements["observability"].techniques:
        if tech.name == "jsonl":
            tech.config["directory"] = str(tmp_path / "runs")

    runtime = Runtime.from_config(cfg)

    seen_types: list[str] = []
    output_chunks: list[str] = []

    async for ev in runtime.run("hello, Aglet!"):
        seen_types.append(ev.type.value)
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            output_chunks.append(ev.payload.get("text", ""))

    assert seen_types[0] == EventType.RUN_STARTED.value
    assert EventType.PERCEPTION_DONE.value in seen_types
    assert EventType.MEMORY_RECALLED.value in seen_types
    assert EventType.PLANNER_THOUGHT.value in seen_types
    assert EventType.PLANNER_FINAL.value in seen_types
    assert EventType.OUTPUT_END.value in seen_types
    assert EventType.RUN_COMPLETED.value in seen_types

    assert "".join(output_chunks) == "Echo: hello, Aglet!"

    # The store should have written at least one trace file.
    runs_dir = tmp_path / "runs"
    assert any(runs_dir.glob("*.jsonl"))
