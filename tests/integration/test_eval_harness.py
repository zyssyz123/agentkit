"""Eval harness end-to-end test using the mock provider for deterministic outcomes."""

from __future__ import annotations

import textwrap

import pytest

from aglet_eval import load_suite, run_suite

AGENT_YAML = textwrap.dedent(
    """\
    schema_version: "1.0"
    name: eval-target
    elements:
      perception: { techniques: [{ name: passthrough }] }
      memory:     { techniques: [{ name: sliding_window }] }
      planner:    { techniques: [{ name: echo, config: { prefix: "Reply: " } }] }
      output:     { techniques: [{ name: streaming_text }] }
      observability: { techniques: [{ name: console, config: { compact: true } }] }
    store: { type: memory }
    """
)

SUITE_YAML_TEMPLATE = textwrap.dedent(
    """\
    agent: {agent_path}
    cases:
      - name: passes-substring
        input: hello
        expected_contains: ["Reply:", "hello"]
        max_seconds: 5
      - name: fails-on-forbidden
        input: nope
        forbidden: ["Reply"]
      - name: fails-on-tool-bound
        input: again
        max_tool_calls: 0
        expected_regex: "Reply: again"
    """
)


@pytest.mark.asyncio
async def test_eval_suite_aggregates_pass_and_fail(tmp_path):
    agent_path = tmp_path / "agent.yaml"
    agent_path.write_text(AGENT_YAML, encoding="utf-8")
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(SUITE_YAML_TEMPLATE.format(agent_path=agent_path), encoding="utf-8")

    suite = load_suite(suite_path)
    report = await run_suite(suite)

    assert report.total == 3
    by_name = {r.case.name: r for r in report.results}
    assert by_name["passes-substring"].passed
    assert not by_name["fails-on-forbidden"].passed
    assert any("forbidden" in f for f in by_name["fails-on-forbidden"].failures)
    # Third case asserts no tool calls AND a regex; both should hold for echo planner.
    assert by_name["fails-on-tool-bound"].passed

    assert report.passed == 2
    assert report.pass_rate == pytest.approx(2 / 3, rel=1e-6)
