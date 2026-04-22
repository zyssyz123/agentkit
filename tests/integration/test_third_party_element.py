"""End-to-end test for the third-party-element demo: confirms a wholly new Element kind
('compliance') contributed via PyPI entry-points works with no core changes.

Validates Aglet's two-dimensional pluggability promise."""

from __future__ import annotations

from pathlib import Path

import pytest

from aglet.config import load_agent_config
from aglet.events import EventType
from aglet.protocols import ELEMENT_NAMES
from aglet.registry import get_registry
from aglet.runtime import Runtime

AGENT_YAML = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "third-party-element-demo"
    / "agent.yaml"
)


@pytest.mark.asyncio
async def test_compliance_element_is_discovered_and_runs(tmp_path):
    registry = get_registry()
    registry.discover_entry_points()

    # 1. The new Element protocol is registered.
    assert "compliance" in registry.elements
    assert "compliance" not in ELEMENT_NAMES, "compliance is not built-in"

    # 2. The new Technique is registered under that Element.
    assert "compliance.cn_pii_scanner" in registry.list_techniques()

    # 3. The agent boots and runs end-to-end with the custom Element wired in.
    cfg = load_agent_config(AGENT_YAML)
    cfg.store.directory = str(tmp_path / "runs")
    runtime = Runtime.from_config(cfg)

    assert "compliance" in runtime.hub.custom
    assert runtime.hub.custom["compliance"].techniques

    seen = []
    final = []
    async for ev in runtime.run("phone 13800138000 email me at me@example.com"):
        seen.append(ev.type.value)
        if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
            final.append(ev.payload.get("text", ""))

    # The agent's canonical loop completed (compliance Element is invoked separately
    # via hooks in M3; here we just confirm the loop tolerates an unknown Element).
    assert EventType.RUN_COMPLETED.value in seen
    assert "".join(final).startswith("Echo:")


@pytest.mark.asyncio
async def test_compliance_technique_can_scan_pii_directly():
    """The 3rd-party Technique speaks its own Element protocol — verify directly."""
    from aglet_demo_compliance import CnPiiScanner

    scanner = CnPiiScanner(config={"scan_field": "raw_input"})
    findings = await scanner.scan(
        "Mobile 13900001234, email user@example.com, ID 110101199001011234"
    )
    kinds = sorted(f.kind for f in findings)
    assert kinds == ["cn_id_card", "cn_phone", "email"]
