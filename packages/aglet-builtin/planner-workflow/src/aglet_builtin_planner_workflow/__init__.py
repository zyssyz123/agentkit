"""planner.workflow — a deterministic declarative-DAG planner.

Use this when you already know the exact call graph (extract → summarise →
render) and want the agent to walk it without asking an LLM to decide.
It produces the same PLANNER_ACTION / PLANNER_FINAL events as any other
planner, so the rest of the Runtime (executor, safety, observability, …)
keeps working unchanged.

Config schema::

    type: workflow
    config:
      nodes:
        - id: fetch
          tool: http_get
          arguments:
            url: "https://example.com"
        - id: analyse
          tool: summarise
          # Template strings reference previous node outputs via {nodes.<id>}.
          arguments:
            text: "{nodes.fetch.body}"
        - id: final
          # A node with no `tool` and a `final` template is the sink — its
          # rendered text becomes Plan.final_answer.
          final: "Summary: {nodes.analyse}"
      # (optional) explicit edges; when omitted we use declaration order.
      edges:
        - [fetch, analyse]
        - [analyse, final]

Substitution rules
------------------

* ``{nodes.<id>}`` — the full output of node <id>.
* ``{nodes.<id>.<field>}`` — a nested field of a dict/JSON output.
* ``{input}`` — the user's raw input text for this turn.

Anything not substituted is left as-is, so you can mix literal YAML with
template references freely.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from aglet.context import AgentContext, ContextPatch, Plan, Thought, ToolCall
from aglet.events import Event, EventType


_TEMPLATE_RE = re.compile(r"\{([^{}]+)\}")


@dataclass
class _Node:
    id: str
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    final: str | None = None


class WorkflowPlanner:
    name = "workflow"
    element = "planner"
    version = "0.1.0"
    capabilities = frozenset({"plan", "dag"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        raw_nodes = cfg.get("nodes", []) or []
        self._nodes: list[_Node] = [
            _Node(
                id=n["id"],
                tool=n.get("tool"),
                arguments=n.get("arguments"),
                final=n.get("final"),
            )
            for n in raw_nodes
        ]
        self._order = self._topo_order(cfg.get("edges"))
        self._fail_on_error: bool = bool(cfg.get("fail_on_error", True))
        # Per-run state. The Runtime resets us via setup() on each run; we
        # keep state on ctx.metadata so resume() works for free.

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    # ------------------------------------------------------------------

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        # Node outputs accumulated across rounds are stashed on ctx.metadata
        # so we can re-enter plan() after each tool round-trip and read them.
        outputs: dict[str, Any] = dict(ctx.metadata.get("_workflow_outputs", {}))

        # First, consume any tool_result from the previous round-trip.
        # The last ToolCall + ToolResult pair is what we issued last time.
        last_call = ctx.tool_calls[-1] if ctx.tool_calls else None
        last_result = ctx.tool_results[-1] if ctx.tool_results else None
        if last_call is not None and last_result is not None:
            # Our call ids are of the form "workflow:<node_id>". Ignore any
            # other planners' calls to stay composable.
            if last_call.id.startswith("workflow:"):
                node_id = last_call.id.split(":", 1)[1]
                outputs[node_id] = (
                    last_result.output if last_result.error is None else None
                )

        # Pick the next undone tool node.
        query = ctx.parsed_input.query if ctx.parsed_input else ctx.raw_input.text
        for node_id in self._order:
            node = self._get(node_id)
            if node_id in outputs:
                continue
            if node.tool:
                args = self._render_obj(node.arguments or {}, outputs, query)
                yield Event(
                    type=EventType.PLANNER_THOUGHT,
                    element=self.element,
                    technique=self.name,
                    payload={"node": node_id, "tool": node.tool, "arguments": args},
                    patch=ContextPatch(
                        changes={
                            "scratchpad_append": [
                                Thought(
                                    content=f"[workflow] {node_id} -> {node.tool}({args})",
                                    technique=self.name,
                                )
                            ]
                        },
                        source_element=self.element,
                        source_technique=self.name,
                    ),
                )
                call = ToolCall(
                    id=f"workflow:{node_id}",
                    name=node.tool,
                    arguments=args,
                )
                new_plan = Plan(next_action=call, reasoning=f"workflow node {node_id}")
                yield Event(
                    type=EventType.PLANNER_ACTION,
                    element=self.element,
                    technique=self.name,
                    payload={"name": call.name, "arguments": call.arguments, "node": node_id},
                    patch=ContextPatch(
                        changes={
                            "plan": new_plan,
                            "metadata": {
                                **ctx.metadata,
                                "_workflow_outputs": outputs,
                            },
                        },
                        source_element=self.element,
                        source_technique=self.name,
                    ),
                )
                return  # one tool per plan() round — Runtime will re-invoke us
            if node.final is not None:
                text = self._render(node.final, outputs, query)
                yield Event(
                    type=EventType.PLANNER_FINAL,
                    element=self.element,
                    technique=self.name,
                    payload={"final": text, "node": node_id},
                    patch=ContextPatch(
                        changes={"plan": Plan(final_answer=text)},
                        source_element=self.element,
                        source_technique=self.name,
                    ),
                )
                return

        # Nothing left to do with no final sink — produce a trivial summary.
        fallback = " | ".join(f"{k}={_short(v)}" for k, v in outputs.items()) or "(no output)"
        yield Event(
            type=EventType.PLANNER_FINAL,
            element=self.element,
            technique=self.name,
            payload={"final": fallback, "reason": "no final node"},
            patch=ContextPatch(
                changes={"plan": Plan(final_answer=fallback)},
                source_element=self.element,
                source_technique=self.name,
            ),
        )

    # ------------------------------------------------------------------
    # Topology + templating helpers

    def _get(self, node_id: str) -> _Node:
        for n in self._nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"workflow: unknown node {node_id!r}")

    def _topo_order(self, edges: list[list[str]] | None) -> list[str]:
        if not edges:
            return [n.id for n in self._nodes]
        from collections import defaultdict, deque

        indeg: dict[str, int] = defaultdict(int)
        adj: dict[str, list[str]] = defaultdict(list)
        ids = [n.id for n in self._nodes]
        for a, b in edges:
            adj[a].append(b)
            indeg[b] += 1
            indeg.setdefault(a, indeg.get(a, 0))
        queue = deque(n for n in ids if indeg.get(n, 0) == 0)
        order: list[str] = []
        while queue:
            cur = queue.popleft()
            order.append(cur)
            for nxt in adj[cur]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(ids):
            raise ValueError("workflow: edges contain a cycle")
        return order

    def _render(self, template: str, outputs: dict[str, Any], user_input: str) -> str:
        def _sub(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if expr == "input":
                return str(user_input)
            if expr.startswith("nodes."):
                parts = expr.split(".")[1:]
                if not parts:
                    return match.group(0)
                value: Any = outputs.get(parts[0], "")
                for p in parts[1:]:
                    if isinstance(value, dict):
                        value = value.get(p, "")
                    else:
                        value = ""
                        break
                return str(value) if not isinstance(value, (dict, list)) else json.dumps(
                    value, default=str
                )
            return match.group(0)

        return _TEMPLATE_RE.sub(_sub, template)

    def _render_obj(self, obj: Any, outputs: dict, user_input: str) -> Any:
        if isinstance(obj, str):
            return self._render(obj, outputs, user_input)
        if isinstance(obj, dict):
            return {k: self._render_obj(v, outputs, user_input) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._render_obj(v, outputs, user_input) for v in obj]
        return obj


def _short(v: Any) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= 60 else s[:57] + "..."
