"""FastAPI application that exposes registered AgentKit agents via REST + SSE.

Endpoints (M2 subset of the design doc):

    GET    /v1/agents
    GET    /v1/agents/{name}
    POST   /v1/agents/{name}/runs       (SSE stream of events)
    GET    /v1/elements
    GET    /v1/elements/{name}/techniques
    GET    /v1/healthz
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agentkit.config import AgentConfig, load_agent_config
from agentkit.events import Event
from agentkit.protocols import ELEMENT_NAMES
from agentkit.registry import get_registry
from agentkit.runtime import Runtime


@dataclass
class _AgentRecord:
    name: str
    config: AgentConfig
    config_path: Path | None


_AGENTS: dict[str, _AgentRecord] = {}


def registered_agents() -> dict[str, _AgentRecord]:
    return _AGENTS


def register_agent_from_path(path: Path) -> _AgentRecord:
    cfg = load_agent_config(path)
    record = _AgentRecord(name=cfg.name, config=cfg, config_path=path)
    _AGENTS[cfg.name] = record
    return record


def create_runtime_for(name: str) -> Runtime:
    record = _AGENTS.get(name)
    if record is None:
        raise KeyError(f"Agent '{name}' not registered")
    return Runtime.from_config(record.config)


# ---------- request / response models -------------------------------------------------------


class RunRequest(BaseModel):
    input: str = Field(..., description="User input text for this turn.")
    conversation_id: str = Field(default="default")


class AgentSummary(BaseModel):
    name: str
    description: str
    elements: list[str]


# ---------- app -----------------------------------------------------------------------------


def build_app(agents: list[Path] | None = None) -> FastAPI:
    """Build the FastAPI app, optionally pre-registering agent.yaml files."""
    if agents:
        for path in agents:
            register_agent_from_path(path)

    app = FastAPI(
        title="AgentKit Server",
        version="0.1.0",
        description="HTTP + SSE interface for the AgentKit runtime.",
    )

    @app.get("/v1/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/agents", response_model=list[AgentSummary])
    async def list_agents() -> list[AgentSummary]:
        return [
            AgentSummary(
                name=r.name,
                description=r.config.description,
                elements=sorted(r.config.elements.keys()),
            )
            for r in _AGENTS.values()
        ]

    @app.get("/v1/agents/{name}", response_model=AgentSummary)
    async def get_agent(name: str) -> AgentSummary:
        record = _AGENTS.get(name)
        if record is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return AgentSummary(
            name=record.name,
            description=record.config.description,
            elements=sorted(record.config.elements.keys()),
        )

    @app.post("/v1/agents/{name}/runs")
    async def run_agent(name: str, body: RunRequest) -> EventSourceResponse:
        record = _AGENTS.get(name)
        if record is None:
            raise HTTPException(status_code=404, detail="agent not found")
        runtime = Runtime.from_config(record.config)

        async def _stream() -> AsyncIterator[dict[str, Any]]:
            async for ev in runtime.run(body.input, conversation_id=body.conversation_id):
                yield {
                    "event": ev.type.value,
                    "id": ev.span_id,
                    "data": json.dumps(ev.to_dict(), ensure_ascii=False, default=str),
                }

        return EventSourceResponse(_stream())

    @app.get("/v1/elements")
    async def list_elements() -> dict[str, Any]:
        registry = get_registry()
        registry.discover_entry_points()
        builtins = set(ELEMENT_NAMES)
        return {
            "elements": [
                {"name": name, "source": "built-in" if name in builtins else "third-party"}
                for name in registry.known_elements()
            ]
        }

    @app.get("/v1/elements/{element}/techniques")
    async def list_techniques(element: str) -> dict[str, Any]:
        registry = get_registry()
        registry.discover_entry_points()
        rows = registry.list_techniques(element)
        if not rows:
            raise HTTPException(status_code=404, detail="no techniques for element")
        return {"element": element, "techniques": [r.split(".", 1)[1] for r in rows]}

    return app


# helper for typing
__all__ = ["build_app", "create_runtime_for", "registered_agents", "register_agent_from_path"]
