"""Common Component / Element / Technique base protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

ELEMENT_NAMES: tuple[str, ...] = (
    "perception",
    "memory",
    "planner",
    "tool",
    "executor",
    "safety",
    "output",
    "observability",
    "extensibility",
)


@dataclass(frozen=True)
class BootContext:
    """Passed to a Component's setup() — gives it config + access to a logger / event bus."""

    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthStatus:
    healthy: bool
    detail: str = ""


@runtime_checkable
class Component(Protocol):
    """Common base for both Elements (protocol declarations) and Techniques (implementations)."""

    name: str
    version: str

    async def setup(self, ctx: BootContext) -> None: ...

    async def teardown(self) -> None: ...

    async def health(self) -> HealthStatus: ...


@runtime_checkable
class ElementProtocol(Protocol):
    """Marker for an Element protocol class. The Registry uses this to verify that
    a 3rd-party-contributed Element has a meaningful protocol attribute."""

    element_kind: str


@runtime_checkable
class TechniqueProtocol(Protocol):
    """Marker for a Technique implementation."""

    name: str
    element: str  # which Element kind this Technique belongs to (e.g. "memory")
    capabilities: frozenset[str]
