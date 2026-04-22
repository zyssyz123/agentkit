"""Suite loader + runner.

Designed so callers can either drive the eval programmatically (CI integration)
or via the ``agentkit-eval`` CLI.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentkit.config import expand_env, load_agent_config
from agentkit.events import EventType
from agentkit.runtime import Runtime


# ---------- schema ---------------------------------------------------------------------------


@dataclass
class EvalCase:
    name: str
    input: str
    expected_contains: list[str] = field(default_factory=list)
    expected_regex: str | None = None
    forbidden: list[str] = field(default_factory=list)
    max_steps: int | None = None
    max_seconds: float | None = None
    min_tool_calls: int | None = None
    max_tool_calls: int | None = None


@dataclass
class EvalSuite:
    agent_path: Path
    cases: list[EvalCase]


@dataclass
class CaseResult:
    case: EvalCase
    passed: bool
    failures: list[str] = field(default_factory=list)
    final_answer: str = ""
    latency_seconds: float = 0.0
    tool_calls: int = 0
    used_steps: int = 0
    used_cost_usd: float = 0.0


@dataclass
class EvalReport:
    suite: EvalSuite
    results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def p95_latency(self) -> float:
        if not self.results:
            return 0.0
        latencies = sorted(r.latency_seconds for r in self.results)
        idx = max(0, int(0.95 * len(latencies)) - 1)
        return latencies[idx]

    @property
    def total_cost_usd(self) -> float:
        return sum(r.used_cost_usd for r in self.results)


# ---------- loader ---------------------------------------------------------------------------


def load_suite(path: str | Path) -> EvalSuite:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(expand_env(text)) or {}
    if "agent" not in data or "cases" not in data:
        raise ValueError(
            f"{path}: suite.yaml must declare top-level 'agent' (path) and 'cases' (list)"
        )
    agent_path = Path(data["agent"])
    if not agent_path.is_absolute():
        agent_path = (Path(path).parent / agent_path).resolve()
    cases = [
        EvalCase(
            name=c.get("name", f"case-{i+1}"),
            input=c["input"],
            expected_contains=list(c.get("expected_contains", [])),
            expected_regex=c.get("expected_regex"),
            forbidden=list(c.get("forbidden", [])),
            max_steps=c.get("max_steps"),
            max_seconds=c.get("max_seconds"),
            min_tool_calls=c.get("min_tool_calls"),
            max_tool_calls=c.get("max_tool_calls"),
        )
        for i, c in enumerate(data["cases"])
    ]
    return EvalSuite(agent_path=agent_path, cases=cases)


# ---------- runner ---------------------------------------------------------------------------


async def run_case(runtime: Runtime, case: EvalCase) -> CaseResult:
    """Execute a single case against an already-built Runtime."""
    started = time.monotonic()
    chunks: list[str] = []
    tool_calls = 0
    used_steps = 0
    used_cost_usd = 0.0
    failure_reason: str | None = None

    try:
        async for ev in runtime.run(case.input, conversation_id=case.name):
            if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
                chunks.append(ev.payload.get("text", ""))
            elif ev.type == EventType.TOOL_CALL:
                tool_calls += 1
            elif ev.type == EventType.RUN_COMPLETED and isinstance(ev.payload, dict):
                used_steps = int(ev.payload.get("steps", 0))
            elif ev.type == EventType.RUN_FAILED and isinstance(ev.payload, dict):
                failure_reason = str(ev.payload.get("reason", "run.failed"))
    except Exception as exc:  # noqa: BLE001
        failure_reason = f"{exc.__class__.__name__}: {exc}"

    latency = time.monotonic() - started
    final = "".join(chunks)
    failures: list[str] = []
    if failure_reason:
        failures.append(f"runtime: {failure_reason}")

    for needle in case.expected_contains:
        if needle not in final:
            failures.append(f"expected_contains missing: {needle!r}")

    if case.expected_regex and not re.search(case.expected_regex, final):
        failures.append(f"expected_regex did not match: {case.expected_regex!r}")

    for forbidden in case.forbidden:
        if forbidden in final:
            failures.append(f"forbidden substring present: {forbidden!r}")

    if case.max_steps is not None and used_steps > case.max_steps:
        failures.append(f"max_steps exceeded: {used_steps} > {case.max_steps}")

    if case.max_seconds is not None and latency > case.max_seconds:
        failures.append(f"max_seconds exceeded: {latency:.2f}s > {case.max_seconds}s")

    if case.min_tool_calls is not None and tool_calls < case.min_tool_calls:
        failures.append(f"min_tool_calls not met: {tool_calls} < {case.min_tool_calls}")

    if case.max_tool_calls is not None and tool_calls > case.max_tool_calls:
        failures.append(f"max_tool_calls exceeded: {tool_calls} > {case.max_tool_calls}")

    return CaseResult(
        case=case,
        passed=not failures,
        failures=failures,
        final_answer=final,
        latency_seconds=latency,
        tool_calls=tool_calls,
        used_steps=used_steps,
        used_cost_usd=used_cost_usd,
    )


async def run_suite(suite: EvalSuite) -> EvalReport:
    """Run every case in a suite (each gets a fresh Runtime for isolation)."""
    cfg = load_agent_config(suite.agent_path)
    report = EvalReport(suite=suite)
    for case in suite.cases:
        runtime = Runtime.from_config(cfg)
        result = await run_case(runtime, case)
        report.results.append(result)
    return report


def run_suite_sync(suite: EvalSuite) -> EvalReport:
    return asyncio.run(run_suite(suite))
