"""planner.reflexion — wrap planner.react with self-critique + retry.

The Reflexion loop:

1. Run the inner planner once. Capture its proposed final answer (and any tool
   errors that arrived during the round).
2. Ask the *critic* model: "Did this answer the user well? If not, give a
   one-paragraph improvement memo." If the critic says ``OK``, we accept.
3. Otherwise, store the critique as a Thought and ask the inner planner again,
   this time with the critique injected into the system prompt as guidance.
4. Repeat up to ``max_reflections``.

This is intentionally lightweight: we don't try to detect "task failure"
heuristically; instead the critic LLM is the judge. Configure a cheaper model
for the critic to control cost.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from aglet.context import AgentContext, ContextPatch, Plan, Thought
from aglet.events import Event, EventType
from aglet.models import ModelHub, ModelMessage

CRITIC_PROMPT = (
    "You are a meticulous reviewer. The user asked a question and the agent "
    "produced an answer. Decide whether the answer is correct, complete and "
    "helpful for the user's question.\n\n"
    "Reply with EXACTLY one of:\n"
    "  OK             - the answer is good as-is.\n"
    "  REVISE: <memo> - the answer is wrong or incomplete; in <memo> give a "
    "concise paragraph (<=120 words) telling the agent what to do differently.\n"
    "Do not output anything else."
)


class ReflexionPlanner:
    name = "reflexion"
    element = "planner"
    version = "0.1.0"
    capabilities = frozenset({"plan", "self_critique"})

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        models: ModelHub | None = None,
    ) -> None:
        cfg = config or {}
        self.inner_name: str = cfg.get("inner", "react")
        self.inner_config: dict[str, Any] = cfg.get("inner_config", {})
        self.critic_model_alias: str = cfg.get("critic_model", "default")
        self.critic_temperature: float = float(cfg.get("critic_temperature", 0.0))
        self.max_reflections: int = int(cfg.get("max_reflections", 1))
        self._models = models
        self._inner = None
        self._inner_factory = None  # populated lazily so we can read the registry

    async def setup(self, ctx) -> None:  # noqa: ARG002
        # Resolve the inner planner via the global registry the first time we run.
        from aglet.registry import get_registry

        factory = get_registry().get_technique_factory("planner", self.inner_name)
        # Defer to the standard "tolerant" factory call that the Runtime uses.
        from aglet.runtime import _instantiate_technique

        self._inner = _instantiate_technique(
            factory, self.inner_config, self._models
        )
        if hasattr(self._inner, "setup"):
            await self._inner.setup(ctx)  # type: ignore[arg-type]

    async def teardown(self) -> None:
        if self._inner is not None and hasattr(self._inner, "teardown"):
            await self._inner.teardown()  # type: ignore[func-returns-value]

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(
            healthy=self._models is not None and self._inner is not None
        )

    # ------------------------------------------------------------------

    async def plan(self, ctx: AgentContext) -> AsyncIterator[Event]:
        if self._inner is None:
            await self.setup(ctx)
        if self._models is None:
            yield _final("Reflexion needs a ModelHub.", self.name)
            return

        attempt_ctx = ctx
        critique: str | None = None

        for attempt in range(self.max_reflections + 1):
            # If we have a critique from a previous attempt, inject it as a
            # synthetic system message via ctx.metadata which the inner planner
            # may read; planner.react also picks up ctx.scratchpad which we
            # already store the critique into below.
            if critique:
                attempt_ctx = attempt_ctx.patch(
                    metadata={**attempt_ctx.metadata, "reflexion_critique": critique}
                )

            # Stream the inner planner's events and capture its final answer.
            captured_final: list[str] = []
            async for ev in self._inner.plan(attempt_ctx):
                # Re-stamp technique to make traces clear about who's planning.
                yield Event(
                    type=ev.type,
                    element=ev.element,
                    technique=f"{self.name}->{ev.technique or self.inner_name}",
                    payload=ev.payload,
                    ts=ev.ts,
                    span_id=ev.span_id,
                    parent_span_id=ev.parent_span_id,
                    patch=ev.patch,
                )
                if ev.patch:
                    attempt_ctx = ev.patch.apply_to(attempt_ctx)
                if (
                    ev.type == EventType.PLANNER_FINAL
                    and isinstance(ev.payload, dict)
                ):
                    captured_final.append(str(ev.payload.get("final", "")))

            # If the inner planner did NOT produce a final answer this round
            # (e.g. it issued a tool call), we cannot critique yet — let the
            # outer Runtime loop dispatch the action and the next round will
            # naturally re-enter Reflexion.
            if not captured_final:
                return

            if attempt >= self.max_reflections:
                return

            # Run the critic.
            critique = await self._critique(ctx, captured_final[-1])
            if critique == "OK":
                return

            # Record the critique as a thought, then loop.
            thought = Thought(
                content=f"Reflexion critique: {critique}", technique=self.name
            )
            yield Event(
                type=EventType.PLANNER_THOUGHT,
                element=self.element,
                technique=self.name,
                payload={"reflection": critique, "attempt": attempt + 1},
                patch=ContextPatch(
                    changes={
                        "scratchpad_append": [thought],
                        # Reset the current plan so the inner planner re-plans.
                        "plan": Plan(),
                    },
                    source_element=self.element,
                    source_technique=self.name,
                ),
            )
            attempt_ctx = attempt_ctx.patch(
                scratchpad=attempt_ctx.scratchpad + (thought,),
                plan=Plan(),
            )

    # ------------------------------------------------------------------

    async def _critique(self, ctx: AgentContext, candidate_answer: str) -> str:
        provider, model_id = self._models.resolve(self.critic_model_alias)
        user_question = ctx.parsed_input.query if ctx.parsed_input else ctx.raw_input.text
        msgs = [
            ModelMessage(role="system", content=CRITIC_PROMPT),
            ModelMessage(
                role="user",
                content=(
                    f"User question:\n{user_question}\n\n"
                    f"Agent answer:\n{candidate_answer}\n\n"
                    "Verdict?"
                ),
            ),
        ]
        resp = await provider.complete(
            model=model_id, messages=msgs, temperature=self.critic_temperature
        )
        text = (resp.content or "").strip()
        if text.upper().startswith("OK"):
            return "OK"
        if text.upper().startswith("REVISE:"):
            return text.split(":", 1)[1].strip() or "(no memo)"
        # Fall back: treat any non-conforming output as no-op.
        return "OK"


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
