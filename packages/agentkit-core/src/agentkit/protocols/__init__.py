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

from agentkit.protocols.base import (
    BootContext,
    Component,
    ELEMENT_NAMES,
    ElementProtocol,
    HealthStatus,
    TechniqueProtocol,
)
from agentkit.protocols.executor import ExecutorTechnique, ToolHost
from agentkit.protocols.extensibility import ExtensibilityTechnique
from agentkit.protocols.memory import MemoryTechnique
from agentkit.protocols.observability import ObservabilityTechnique
from agentkit.protocols.output import OutputChunk, OutputTechnique
from agentkit.protocols.perception import PerceptionTechnique
from agentkit.protocols.planner import PlannerTechnique
from agentkit.protocols.safety import SafetyTechnique
from agentkit.protocols.tool import ToolTechnique

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
