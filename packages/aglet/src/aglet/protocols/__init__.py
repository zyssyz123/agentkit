"""The 9 Element protocols. Techniques implement these via :class:`typing.Protocol`.

Element name -> Protocol class:

    perception      -> PerceptionTechnique
    memory          -> MemoryTechnique
    planner         -> PlannerTechnique
    tool            -> ToolTechnique
    executor        -> ExecutorTechnique
    safety          -> SafetyTechnique
    output          -> OutputTechnique
    observability   -> ObservabilityTechnique
    extensibility   -> ExtensibilityTechnique
"""

from aglet.protocols.base import (
    BootContext,
    Component,
    ELEMENT_NAMES,
    ElementProtocol,
    HealthStatus,
    TechniqueProtocol,
)
from aglet.protocols.executor import ExecutorTechnique, ToolHost
from aglet.protocols.extensibility import ExtensibilityTechnique
from aglet.protocols.memory import MemoryTechnique
from aglet.protocols.observability import ObservabilityTechnique
from aglet.protocols.output import OutputChunk, OutputTechnique
from aglet.protocols.perception import PerceptionTechnique
from aglet.protocols.planner import PlannerTechnique
from aglet.protocols.safety import SafetyTechnique
from aglet.protocols.tool import ToolTechnique

__all__ = [
    "BootContext",
    "Component",
    "ELEMENT_NAMES",
    "ElementProtocol",
    "ExecutorTechnique",
    "ExtensibilityTechnique",
    "HealthStatus",
    "MemoryTechnique",
    "ObservabilityTechnique",
    "OutputChunk",
    "OutputTechnique",
    "PerceptionTechnique",
    "PlannerTechnique",
    "SafetyTechnique",
    "TechniqueProtocol",
    "ToolHost",
    "ToolTechnique",
]
