"""Smoke test for the FastAPI server: /v1/agents and a streaming /runs call against the
echo-agent (no external services)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aglet_server import build_app

ECHO_AGENT_YAML = Path(__file__).resolve().parents[2] / "examples" / "echo-agent" / "agent.yaml"


@pytest.fixture()
def client(tmp_path):
    # Tweak the run directories to avoid polluting cwd.
    yaml_text = ECHO_AGENT_YAML.read_text(encoding="utf-8").replace(
        ".aglet/runs", str(tmp_path / "runs")
    )
    target = tmp_path / "agent.yaml"
    target.write_text(yaml_text, encoding="utf-8")
    app = build_app(agents=[target])
    return TestClient(app)


def test_health_and_listing(client):
    r = client.get("/v1/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}

    r = client.get("/v1/agents")
    assert r.status_code == 200
    body = r.json()
    assert any(a["name"] == "echo-agent" for a in body)


def test_runs_streams_output(client):
    with client.stream(
        "POST",
        "/v1/agents/echo-agent/runs",
        json={"input": "hi server"},
    ) as resp:
        assert resp.status_code == 200
        # Collect SSE payloads (data: lines) until run.completed.
        chunks: list[str] = []
        completed_seen = False
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                payload = json.loads(line[len("data:") :].strip())
                if payload["type"] == "output.chunk":
                    chunks.append(payload["payload"]["text"])
                if payload["type"] == "run.completed":
                    completed_seen = True
                    break
    assert completed_seen
    assert "".join(chunks) == "Echo: hi server"


def test_elements_endpoint(client):
    r = client.get("/v1/elements")
    assert r.status_code == 200
    names = [e["name"] for e in r.json()["elements"]]
    assert "memory" in names and "planner" in names

    r = client.get("/v1/elements/planner/techniques")
    assert r.status_code == 200
    body = r.json()
    assert body["element"] == "planner"
    assert "echo" in body["techniques"]
