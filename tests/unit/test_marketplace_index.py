"""Validate the marketplace index ships as well-formed JSON and matches the
entry-point groups our published packages declare."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / "docs" / "marketplace.json"


def test_marketplace_index_is_valid_json():
    assert MARKETPLACE.exists(), f"{MARKETPLACE} missing"
    data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert isinstance(data["plugins"], list) and data["plugins"]


def test_marketplace_entries_have_mandatory_fields():
    data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    for p in data["plugins"]:
        assert {"name", "kind", "description", "version"}.issubset(
            p.keys()
        ), f"plugin missing fields: {p.get('name')}"
        if p["kind"] == "technique":
            assert p.get("element"), f"technique entry missing 'element': {p['name']}"
            assert p.get("technique"), f"technique entry missing 'technique': {p['name']}"


def test_marketplace_covers_every_publishable_builtin():
    """Every aglet-builtin-* workspace package should be listed."""
    pkgs = {p.name for p in (ROOT / "packages/aglet-builtin").iterdir() if p.is_dir()}
    data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    listed = {p["name"] for p in data["plugins"]}

    def _dist_for(dir_name: str) -> str:
        return f"aglet-builtin-{dir_name}"

    expected = {_dist_for(d) for d in pkgs}
    missing = expected - listed
    assert not missing, f"marketplace index missing packages: {sorted(missing)}"
