"""Verify the config-sanity guards we added after the first-time-user dogfood."""

from __future__ import annotations

import textwrap

import pytest

from aglet.config import load_agent_config
from aglet.runtime import AgentConfigError, Runtime


BASE_YAML = """\
schema_version: "1.0"
name: sanity-test
elements:
  perception: {{ techniques: [{{ name: passthrough }}] }}
  planner:    {{ techniques: [{{ name: {planner_techs} }}] }}
  output:     {{ techniques: [{{ name: streaming_text }}] }}
  observability: {{ techniques: [{{ name: console, config: {{ compact: true }} }}] }}
store: {{ type: memory }}
"""


@pytest.mark.parametrize(
    "yaml_body, missing",
    [
        # no elements at all
        (
            textwrap.dedent(
                """\
                schema_version: "1.0"
                name: zero
                store: { type: memory }
                """
            ),
            "planner",
        ),
        # elements but no planner
        (
            textwrap.dedent(
                """\
                schema_version: "1.0"
                name: no-planner
                elements:
                  perception: { techniques: [{ name: passthrough }] }
                  output:     { techniques: [{ name: streaming_text }] }
                store: { type: memory }
                """
            ),
            "planner",
        ),
        # planner with empty techniques list
        (
            textwrap.dedent(
                """\
                schema_version: "1.0"
                name: empty-planner
                elements:
                  perception: { techniques: [{ name: passthrough }] }
                  planner:    { techniques: [] }
                  output:     { techniques: [{ name: streaming_text }] }
                store: { type: memory }
                """
            ),
            "planner",
        ),
        # no output
        (
            textwrap.dedent(
                """\
                schema_version: "1.0"
                name: no-output
                elements:
                  perception: { techniques: [{ name: passthrough }] }
                  planner:    { techniques: [{ name: echo }] }
                store: { type: memory }
                """
            ),
            "output",
        ),
    ],
)
def test_missing_required_element_raises(tmp_path, yaml_body, missing):
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(yaml_body, encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    with pytest.raises(AgentConfigError) as exc:
        Runtime.from_config(cfg)
    assert missing in str(exc.value)


def test_missing_recommended_element_only_warns(tmp_path, caplog):
    """Missing `perception` / `safety` -> warning on stderr, run still starts."""
    import logging

    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            schema_version: "1.0"
            name: no-perception-or-safety
            elements:
              planner: { techniques: [{ name: echo }] }
              output:  { techniques: [{ name: streaming_text }] }
            store: { type: memory }
            """
        ),
        encoding="utf-8",
    )
    cfg = load_agent_config(yaml_path)
    with caplog.at_level(logging.WARNING, logger="aglet.runtime"):
        Runtime.from_config(cfg)  # must NOT raise
    messages = "\n".join(r.message for r in caplog.records)
    assert "perception" in messages
    assert "safety" in messages


def test_full_config_passes_sanity(tmp_path):
    """The two REQUIRED elements present with at least one technique each → OK."""
    yaml_path = tmp_path / "agent.yaml"
    yaml_path.write_text(BASE_YAML.format(planner_techs="echo"), encoding="utf-8")
    cfg = load_agent_config(yaml_path)
    # Must not raise; the constructed Runtime is enough proof.
    rt = Runtime.from_config(cfg)
    assert rt is not None
