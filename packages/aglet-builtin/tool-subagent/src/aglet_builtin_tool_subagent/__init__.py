"""tool.subagent — wrap another agent.yaml as a callable Aglet Tool.

The multi-agent primitive: any Aglet agent can declare another agent as one
of its Tool techniques and the parent's planner.react / executor.sequential
will dispatch to it like to any other tool.

Config schema::

    type: subagent
    config:
      agents:
        - name: research                       # tool name the parent will call
          description: Detailed research on a topic
          path: ./agents/research-agent.yaml   # path is resolved relative to cwd
          input_field: question                # JSON-Schema arg the parent must pass
        - name: code_reviewer
          description: Reviews a code diff and returns suggestions
          path: ./agents/code-reviewer.yaml
          input_field: diff
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aglet.context import ToolResult, ToolSpec
from aglet.events import EventType

log = logging.getLogger(__name__)


@dataclass
class _SubAgent:
    name: str
    description: str
    path: Path
    input_field: str
    runtime: Any = None  # lazily constructed on first call


class SubAgentTool:
    name = "subagent"
    element = "tool"
    version = "0.1.0"
    capabilities = frozenset({"list", "invoke", "multi_agent"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self._agents: dict[str, _SubAgent] = {}
        for entry in cfg.get("agents", []):
            sub = _SubAgent(
                name=entry["name"],
                description=entry.get("description", f"Sub-agent {entry['name']}"),
                path=Path(entry["path"]).expanduser().resolve(),
                input_field=entry.get("input_field", "input"),
            )
            self._agents[sub.name] = sub

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        missing = [s.name for s in self._agents.values() if not s.path.exists()]
        return HealthStatus(
            healthy=not missing,
            detail="" if not missing else f"missing yaml: {missing}",
        )

    async def list(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        for sub in self._agents.values():
            out.append(
                ToolSpec(
                    name=sub.name,
                    description=sub.description,
                    parameters_schema={
                        "type": "object",
                        "properties": {sub.input_field: {"type": "string"}},
                        "required": [sub.input_field],
                        "additionalProperties": True,
                    },
                    technique=self.name,
                )
            )
        return out

    async def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        sub = self._agents.get(name)
        if sub is None:
            return ToolResult(
                call_id="", output=None, error=f"unknown sub-agent {name!r}"
            )
        if not sub.path.exists():
            return ToolResult(
                call_id="", output=None, error=f"agent.yaml not found: {sub.path}"
            )

        # Lazy-build the inner Runtime so cycles in 3rd-party plugin discovery
        # don't bite us at import time.
        if sub.runtime is None:
            from aglet.config import load_agent_config
            from aglet.runtime import Runtime

            cfg = load_agent_config(sub.path)
            sub.runtime = Runtime.from_config(cfg)

        question = str(arguments.get(sub.input_field) or arguments.get("input") or "")
        if not question:
            return ToolResult(
                call_id="",
                output=None,
                error=f"sub-agent {name!r} expects field {sub.input_field!r}",
            )

        started = time.monotonic()
        final_chunks: list[str] = []
        last_error: str | None = None
        try:
            async for ev in sub.runtime.run(question):
                if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
                    final_chunks.append(ev.payload.get("text", ""))
                if ev.type == EventType.RUN_FAILED and isinstance(ev.payload, dict):
                    last_error = str(ev.payload.get("reason", "subagent failed"))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                call_id="",
                output=None,
                error=f"{exc.__class__.__name__}: {exc}",
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        return ToolResult(
            call_id="",
            output="".join(final_chunks),
            error=last_error,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
