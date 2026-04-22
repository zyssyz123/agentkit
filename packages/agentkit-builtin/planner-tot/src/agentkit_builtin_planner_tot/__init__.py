"""planner.tot — minimal Tree-of-Thoughts planner.

The classic ToT framework explores a search tree of partial reasoning paths and
prunes via a value heuristic. This M4 incarnation is intentionally narrow:

* Generate ``branches`` candidate answers in parallel from the planning model.
* Score each candidate with a separate evaluator call ("rate from 1-10").
* Emit the highest-scoring candidate as the final answer.

This already covers the most common production use of "ToT-style sampling",
provides a clean extension point for richer search strategies (beam search,
MCTS) in M5, and works with any ModelProvider.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from agentkit.context import AgentContext, ContextPatch, Plan, Thought
from agentkit.events import Event, EventType
from agentkit.models import ModelHub, ModelMessage

GENERATOR_PROMPT_DEFAULT = (
    "You are a helpful assistant. Read the user's question and write the best "
    "single-paragraph answer you can. Be concise and concrete."
)
EVALUATOR_PROMPT = (
    "Score the following candidate answer to the user's question on a scale of "
    "1 (terrible) to 10 (excellent). Reply with EXACTLY a single integer 1-10 "
    "and nothing else."
)


class TreeOfThoughtsPlanner:
    name = "tot"
    element = "planner"
    version = "0.1.0"
    capabilities = frozenset({"plan", "sampling"})

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        models: ModelHub | None = None,
    ) -> None:
        cfg = config or {}
        self.branches: int = max(1, int(cfg.get("branches", 3)))
        self.generator_model: str = cfg.get("generator_model", "default")
        self.evaluator_model: str = cfg.get("evaluator_model", cfg.get("generator_model", "default"))
        self.generator_temperature: float = float(cfg.get("generator_temperature", 0.9))
        self.evaluator_temperature: float = float(cfg.get("evaluator_temperature", 0.0))
        self.system_prompt: str = cfg.get("system_prompt", GENERATOR_PROMPT_DEFAULT)
        self._models = models

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from agentkit.protocols import HealthStatus

        return HealthStatus(healthy=self._models is not None)

    # ------------------------------------------------------------------

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        if self._models is None:
            yield _final("ToT needs a ModelHub.", self.name)
            return

        question = ctx.parsed_input.query if ctx.parsed_input else ctx.raw_input.text
        gen_provider, gen_model = self._models.resolve(self.generator_model)
        eval_provider, eval_model = self._models.resolve(self.evaluator_model)

        # 1. Sample N candidates concurrently.
        async def _sample(_idx: int) -> str:
            resp = await gen_provider.complete(
                model=gen_model,
                messages=[
                    ModelMessage(role="system", content=self.system_prompt),
                    ModelMessage(role="user", content=question),
                ],
                temperature=self.generator_temperature,
            )
            return (resp.content or "").strip()

        candidates: list[str] = await asyncio.gather(
            *(_sample(i) for i in range(self.branches))
        )

        for i, cand in enumerate(candidates):
            thought = Thought(content=f"[branch {i}] {cand}", technique=self.name)
            yield Event(
                type=EventType.PLANNER_THOUGHT,
                element=self.element,
                technique=self.name,
                payload={"branch": i, "candidate": cand},
                patch=ContextPatch(
                    changes={"scratchpad_append": [thought]},
                    source_element=self.element,
                    source_technique=self.name,
                ),
            )

        # 2. Score each.
        async def _score(idx: int, candidate: str) -> tuple[int, int, str]:
            resp = await eval_provider.complete(
                model=eval_model,
                messages=[
                    ModelMessage(role="system", content=EVALUATOR_PROMPT),
                    ModelMessage(
                        role="user",
                        content=f"Question:\n{question}\n\nCandidate:\n{candidate}",
                    ),
                ],
                temperature=self.evaluator_temperature,
            )
            text = (resp.content or "").strip()
            match = re.search(r"\d+", text)
            score = int(match.group(0)) if match else 0
            return idx, max(1, min(10, score)), candidate

        scores = await asyncio.gather(
            *(_score(i, c) for i, c in enumerate(candidates))
        )
        scores.sort(key=lambda x: x[1], reverse=True)
        best_idx, best_score, best_text = scores[0]

        yield Event(
            type=EventType.PLANNER_THOUGHT,
            element=self.element,
            technique=self.name,
            payload={"selected_branch": best_idx, "score": best_score},
            patch=ContextPatch(
                changes={
                    "scratchpad_append": [
                        Thought(
                            content=f"Selected branch {best_idx} (score {best_score}/10).",
                            technique=self.name,
                        )
                    ]
                },
                source_element=self.element,
                source_technique=self.name,
            ),
        )

        yield _final(best_text, self.name)


def _final(text: str, technique: str) -> Event:
    plan = Plan(final_answer=text)
    return Event(
        type=EventType.PLANNER_FINAL,
        element="planner",
        technique=technique,
        payload={"final": text},
        patch=ContextPatch(
            changes={"plan": plan},
            source_element="planner",
            source_technique=technique,
        ),
    )
