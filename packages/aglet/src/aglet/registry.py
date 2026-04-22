"""Process-global registry of Elements and Techniques.

Techniques publish themselves in two ways:

1. **Python entry points** (preferred for distribution): a plugin's ``pyproject.toml`` exposes
   ``[project.entry-points."aglet.techniques"]`` mapping ``<element>.<name>`` to a
   ``module:Factory`` callable returning an instance.
2. **Direct registration**: tests or the in-process loader can call :meth:`register_technique`
   programmatically.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import metadata
from typing import Any

from aglet.protocols import ELEMENT_NAMES

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP_TECHNIQUES = "aglet.techniques"
ENTRY_POINT_GROUP_ELEMENTS = "aglet.elements"


@dataclass
class Registry:
    """Holds Element protocols and Technique factories keyed by qualified name."""

    elements: dict[str, type] = field(default_factory=dict)
    technique_factories: dict[str, Callable[..., Any]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Element registration

    def register_element(self, name: str, protocol_cls: type) -> None:
        if name in self.elements and self.elements[name] is not protocol_cls:
            log.warning("Element %s re-registered with different protocol; overriding", name)
        self.elements[name] = protocol_cls

    # ------------------------------------------------------------------
    # Technique registration

    def register_technique(
        self, element: str, name: str, factory: Callable[..., Any]
    ) -> None:
        qualified = f"{element}.{name}"
        if qualified in self.technique_factories:
            log.warning("Technique %s already registered; overriding", qualified)
        self.technique_factories[qualified] = factory

    def get_technique_factory(self, element: str, name: str) -> Callable[..., Any]:
        qualified = f"{element}.{name}"
        if qualified not in self.technique_factories:
            raise KeyError(
                f"No Technique '{qualified}' registered. "
                f"Available: {sorted(self.technique_factories)}"
            )
        return self.technique_factories[qualified]

    def list_techniques(self, element: str | None = None) -> list[str]:
        all_names = sorted(self.technique_factories)
        if element is None:
            return all_names
        prefix = f"{element}."
        return [n for n in all_names if n.startswith(prefix)]

    # ------------------------------------------------------------------
    # Entry-point discovery

    def discover_entry_points(self) -> int:
        """Discover Techniques + Elements published via Python entry points.

        Returns the total number of components newly registered.
        """
        added = 0
        # Techniques
        try:
            eps = metadata.entry_points(group=ENTRY_POINT_GROUP_TECHNIQUES)
        except TypeError:  # py < 3.10 style
            eps = metadata.entry_points().get(ENTRY_POINT_GROUP_TECHNIQUES, [])  # type: ignore[assignment]
        for ep in eps:
            try:
                element, name = ep.name.split(".", 1)
            except ValueError:
                log.warning("Skipping entry point %s: name must be '<element>.<name>'", ep.name)
                continue
            try:
                factory = ep.load()
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to load technique entry point %s: %s", ep.name, exc)
                continue
            self.register_technique(element, name, factory)
            added += 1

        # Elements (third-party can introduce wholly new Elements)
        try:
            elements_eps = metadata.entry_points(group=ENTRY_POINT_GROUP_ELEMENTS)
        except TypeError:
            elements_eps = metadata.entry_points().get(  # type: ignore[assignment]
                ENTRY_POINT_GROUP_ELEMENTS, []
            )
        for ep in elements_eps:
            try:
                proto = ep.load()
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to load element entry point %s: %s", ep.name, exc)
                continue
            self.register_element(ep.name, proto)
            added += 1
        return added

    def import_paths(self, paths: list[str]) -> int:
        """Import dotted paths to side-effect-register their components.

        Useful when a plugin opts out of entry points (e.g. local dev).
        Returns count of paths successfully imported.
        """
        ok = 0
        for path in paths:
            try:
                importlib.import_module(path)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to import plugin module %s: %s", path, exc)
        return ok

    # ------------------------------------------------------------------
    # Helpers

    def known_elements(self) -> list[str]:
        builtins = list(ELEMENT_NAMES)
        extras = sorted(set(self.elements) - set(builtins))
        return [*builtins, *extras]


# ---------- module-level singleton ------------------------------------------------------------

_GLOBAL_REGISTRY: Registry | None = None


def get_registry() -> Registry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = Registry()
    return _GLOBAL_REGISTRY


def reset_registry() -> None:
    """Test helper — drop the global registry."""
    global _GLOBAL_REGISTRY
    _GLOBAL_REGISTRY = None
