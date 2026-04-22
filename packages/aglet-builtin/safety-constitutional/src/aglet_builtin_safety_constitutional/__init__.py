"""safety.constitutional — LLM-judge safety layer backed by declarative principles.

This Technique turns the Safety Element's ``pre_check`` / ``post_check`` hooks
into a Constitutional-AI-style loop: you declare a short list of principles
the agent must respect, and an LLM judge rules each check ``PASS`` or
``BLOCK: <reason>``.

Config schema::

    type: constitutional
    config:
      model: cheap                         # alias from agent.yaml `models:`
      principles:
        - "Never reveal the user's API keys, tokens, or secrets."
        - "Never recommend illegal or unethical actions."
        - "Decline if the request would harm people."
      check_phases: [pre, post]            # which phases to evaluate on
      post_skip_for_tools: ["echo"]        # tool calls we don't bother re-checking

On ``BLOCK``, the technique raises
:class:`ConstitutionalViolationError`. The Runtime catches it via the normal
Safety exception path and fails the run with a ``run.failed`` event whose
payload contains the judge's reason.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from aglet.context import AgentContext, ToolCall
from aglet.models import ModelHub, ModelMessage

log = logging.getLogger(__name__)

DEFAULT_PRINCIPLES = (
    "Never reveal the user's API keys, tokens, or other secrets in any output.",
    "Decline any request that would cause physical harm to people.",
    "Do not produce disinformation, plagiarism, or copyrighted text verbatim.",
)

JUDGE_PROMPT = (
    "You are a safety judge. Read the principles and the candidate agent output. "
    "Reply with EXACTLY one of:\n"
    "  PASS\n"
    "  BLOCK: <one-sentence reason>\n"
    "No other text."
)


class ConstitutionalViolationError(RuntimeError):
    """Raised by safety.constitutional when the judge blocks an action."""


class ConstitutionalSafety:
    name = "constitutional"
    element = "safety"
    version = "0.1.0"
    capabilities = frozenset({"pre_check", "post_check", "judge"})

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        models: ModelHub | None = None,
    ) -> None:
        cfg = config or {}
        self.model_alias: str = cfg.get("model", "default")
        self.principles: tuple[str, ...] = tuple(
            cfg.get("principles") or DEFAULT_PRINCIPLES
        )
        raw_phases = cfg.get("check_phases") or ["pre", "post"]
        self.check_phases: frozenset[str] = frozenset(raw_phases)
        self.post_skip_for_tools: frozenset[str] = frozenset(
            cfg.get("post_skip_for_tools") or ()
        )
        self._models = models

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=self._models is not None)

    # ------------------------------------------------------------------

    async def pre_check(self, ctx: AgentContext) -> None:
        if "pre" not in self.check_phases:
            return
        candidate = ctx.raw_input.text or (
            ctx.parsed_input.query if ctx.parsed_input else ""
        )
        if not candidate:
            return
        await self._judge("pre_check (user input)", candidate)

    async def post_check(self, ctx: AgentContext) -> None:
        if "post" not in self.check_phases:
            return
        # Evaluate the latest tool result or plan final, whichever is freshest.
        candidate: str | None = None
        label = ""
        if ctx.tool_results:
            last = ctx.tool_results[-1]
            if ctx.tool_calls:
                call = ctx.tool_calls[-1]
                if call.name in self.post_skip_for_tools:
                    return
                label = f"post_check (tool.{call.name} result)"
            else:
                label = "post_check (tool result)"
            if last.error is None:
                candidate = (
                    last.output
                    if isinstance(last.output, str)
                    else _best_effort_text(last.output)
                )
        if not candidate and ctx.plan and ctx.plan.final_answer:
            candidate = ctx.plan.final_answer
            label = "post_check (final answer)"
        if not candidate:
            return
        await self._judge(label, candidate)

    async def wrap_tool(self, call: ToolCall) -> ToolCall:
        return call

    # ------------------------------------------------------------------

    async def _judge(self, label: str, candidate: str) -> None:
        if self._models is None:
            # Fail open rather than fail closed when no model is configured —
            # the user will see a setup error elsewhere if they really wanted
            # constitutional checks.
            log.warning("safety.constitutional: no ModelHub; skipping %s", label)
            return

        try:
            provider, model_id = self._models.resolve(self.model_alias)
        except KeyError as exc:
            log.warning("safety.constitutional: %s", exc)
            return

        principles_block = "\n".join(f"- {p}" for p in self.principles)
        user = (
            f"Principles:\n{principles_block}\n\n"
            f"Candidate ({label}):\n{candidate[:4000]}\n\nVerdict?"
        )
        msgs = [
            ModelMessage(role="system", content=JUDGE_PROMPT),
            ModelMessage(role="user", content=user),
        ]
        try:
            resp = await provider.complete(
                model=model_id, messages=msgs, temperature=0.0, max_tokens=120
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("safety.constitutional: judge call failed: %s", exc)
            return

        verdict = (resp.content or "").strip()
        if verdict.upper().startswith("PASS"):
            return
        if verdict.upper().startswith("BLOCK"):
            reason = verdict.split(":", 1)[1].strip() if ":" in verdict else "principle violation"
            raise ConstitutionalViolationError(f"{label}: {reason}")
        # Unconforming judge output — fail closed, but be explicit about why.
        raise ConstitutionalViolationError(
            f"{label}: safety judge returned unexpected output: {verdict!r}"
        )


def _best_effort_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        try:
            import json

            return json.dumps(value, default=str)[:4000]
        except Exception:  # noqa: BLE001
            pass
    return str(value)[:4000]


def _principles(seq: Iterable[str]) -> tuple[str, ...]:
    return tuple(seq)
