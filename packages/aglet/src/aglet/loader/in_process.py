"""In-process plugin runtime + a thin PluginLoader facade.

In M1 the loader simply triggers entry-point discovery and (optionally) imports a list of
dotted-path modules from the agent config. Subprocess / HTTP / MCP loaders land in M3.
"""

from __future__ import annotations

import logging
from typing import Any

from aglet.registry import Registry, get_registry

log = logging.getLogger(__name__)


class InProcessRuntime:
    """Trivial runtime: components live in the parent Python process.

    Concrete responsibilities boil down to instantiating Technique factories with their
    YAML config dict; the Hub does the rest.
    """

    name = "in_process"

    def instantiate(self, factory: Any, config: dict[str, Any]) -> Any:
        """Call a Technique factory with the user-provided config dict.

        Factories may be classes (``Cls(config=...)``) or callables (``factory(config=...)``).
        We try keyword-form first, then positional, then no-arg.
        """
        try:
            return factory(config=config)
        except TypeError:
            try:
                return factory(config)
            except TypeError:
                return factory()


class PluginLoader:
    """Discover and prepare plugins for a Runtime."""

    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry or get_registry()
        self.runtime = InProcessRuntime()

    def discover(self) -> int:
        """Trigger entry-point discovery; return count newly registered."""
        added = self.registry.discover_entry_points()
        log.info("Discovered %d Aglet components via entry points", added)
        return added

    def import_modules(self, modules: list[str]) -> int:
        """Side-effect-import dotted paths so their @register decorators fire."""
        return self.registry.import_paths(modules)
