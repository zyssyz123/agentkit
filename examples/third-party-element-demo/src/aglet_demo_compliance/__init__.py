"""Third-party plugin demo: a wholly new ``compliance`` Element + a Technique.

Demonstrates that Aglet's "double pluggability" really works:

* A 3rd party defines a brand-new Element protocol (``compliance``) with its own
  method shape — here, ``scan(text) -> list[Finding]``.
* The same plugin contributes one Technique (``compliance.cn_pii_scanner``).
* Users wire it into agent.yaml under ``elements.compliance.techniques`` exactly
  the same way they wire any built-in Element.

The Runtime auto-creates a generic ElementHost for unknown Elements and exposes it
under ``hub.custom["compliance"]``; the rest works because every Component speaks
the same Component / Technique protocol.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from aglet.context import AgentContext, ContextPatch


# ---------- Element protocol -----------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    kind: str
    span: tuple[int, int]
    sample: str


@runtime_checkable
class ComplianceProtocol(Protocol):
    """Brand-new Element protocol contributed by a third party."""

    element_kind: str

    async def scan(self, text: str) -> list[Finding]: ...


# ---------- Technique ------------------------------------------------------------------------


_CN_ID_CARD = re.compile(r"\b\d{15}(?:\d{2}[\dXx])?\b")
_CN_PHONE = re.compile(r"\b1[3-9]\d{9}\b")
_EMAIL = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b")


class CnPiiScanner:
    """Lightweight regex scanner for CN ID cards / phones / emails."""

    name = "cn_pii_scanner"
    element = "compliance"
    version = "0.1.0"
    capabilities = frozenset({"scan"})

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.fail_on_finding: bool = bool(cfg.get("fail_on_finding", False))
        self.scan_field: str = cfg.get("scan_field", "raw_input")  # "raw_input" | "final_answer"

    async def setup(self, ctx) -> None:  # noqa: ARG002
        return None

    async def teardown(self) -> None:
        return None

    async def health(self):
        from aglet.protocols import HealthStatus

        return HealthStatus(healthy=True)

    async def scan(self, text: str) -> list[Finding]:
        findings: list[Finding] = []
        for kind, pattern in (
            ("cn_id_card", _CN_ID_CARD),
            ("cn_phone", _CN_PHONE),
            ("email", _EMAIL),
        ):
            for match in pattern.finditer(text):
                findings.append(
                    Finding(kind=kind, span=match.span(), sample=match.group(0))
                )
        return findings

    # The Element protocol's surface is `scan(text) -> list[Finding]`. To make this
    # technique useful inside the canonical Loop without writing a custom Runtime, we
    # also expose a ``review(ctx)`` method that the example agent.yaml triggers via the
    # generic ElementHost.invoke pathway. This double role illustrates that a Technique
    # can speak both its Element's protocol AND any extra hook surface the user wants.
    async def review(self, ctx: AgentContext) -> ContextPatch:
        text = ctx.raw_input.text if self.scan_field == "raw_input" else (
            ctx.plan.final_answer if ctx.plan and ctx.plan.final_answer else ""
        )
        findings = await self.scan(text)
        return ContextPatch(
            changes={"metadata": {**ctx.metadata, "compliance_findings": [f.__dict__ for f in findings]}},
            source_element=self.element,
            source_technique=self.name,
        )
