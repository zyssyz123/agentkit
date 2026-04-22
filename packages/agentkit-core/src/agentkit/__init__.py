"""AgentKit core public API.

Two-dimensional pluggable Agent runtime: every Element (Perception, Memory, Planner, Tool,
Executor, Safety, Output, Observability, Extensibility) and every Technique within an Element
is loadable via Python entry points.
"""

from agentkit.budget import Budget, BudgetExceededError
from agentkit.config import (
    AgentConfig,
    ElementConfig,
    ProviderConfig,
    TechniqueConfig,
    load_agent_config,
)
from agentkit.context import (
    AgentContext,
    ContextPatch,
    Message,
    ParsedInput,
    Plan,
    RawInput,
    Thought,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from agentkit.events import Event, EventBus, EventType
from agentkit.hooks import HookCallable, HookManager
from agentkit.hub import ElementHost, ElementHub, RoutingStrategy
from agentkit.loader import InProcessRuntime, PluginLoader
from agentkit.models import (
    ModelChunk,
    ModelHub,
    ModelMessage,
    ModelProvider,
    ModelResponse,
    ModelToolCall,
)
from agentkit.registry import Registry, get_registry
from agentkit.runtime import Runtime
from agentkit.store import ContextStore, InMemoryContextStore, JsonlContextStore

__all__ = [
    # Context
    "AgentContext",
    "ContextPatch",
    "Message",
    "ParsedInput",
    "Plan",
    "RawInput",
    "Thought",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    # Budget
    "Budget",
    "BudgetExceededError",
    # Events
    "Event",
    "EventBus",
    "EventType",
    # Hooks
    "HookCallable",
    "HookManager",
    # Runtime
    "Runtime",
    "ElementHub",
    "ElementHost",
    "RoutingStrategy",
    # Loader
    "InProcessRuntime",
    "PluginLoader",
    "Registry",
    "get_registry",
    # Store
    "ContextStore",
    "InMemoryContextStore",
    "JsonlContextStore",
    # Config
    "AgentConfig",
    "ElementConfig",
    "ProviderConfig",
    "TechniqueConfig",
    "load_agent_config",
    # Models
    "ModelChunk",
    "ModelHub",
    "ModelMessage",
    "ModelProvider",
    "ModelResponse",
    "ModelToolCall",
]

__version__ = "0.1.0"
