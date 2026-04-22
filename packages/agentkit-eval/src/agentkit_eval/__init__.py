"""AgentKit evaluation harness.

A ``suite.yaml`` describes one or more agents under test and a list of cases. Each
case has an input and a set of declarative assertions:

  - ``expected_contains: [...]``    every substring must appear in the final answer
  - ``expected_regex: "..."``       Python-regex match against the final answer
  - ``forbidden: [...]``            none of these substrings may appear
  - ``max_steps``                   the run must complete in ≤ this many planner steps
  - ``max_seconds``                 the run must complete in ≤ this wall-clock duration
  - ``min_tool_calls`` / ``max_tool_calls``
                                    bound on the number of TOOL_CALL events seen

Each case is executed independently against a fresh Runtime; results aggregate into
a pass / fail report with latency + tool-call counts.
"""

from agentkit_eval.harness import (
    CaseResult,
    EvalCase,
    EvalReport,
    EvalSuite,
    load_suite,
    run_case,
    run_suite,
)

__all__ = [
    "CaseResult",
    "EvalCase",
    "EvalReport",
    "EvalSuite",
    "load_suite",
    "run_case",
    "run_suite",
]
