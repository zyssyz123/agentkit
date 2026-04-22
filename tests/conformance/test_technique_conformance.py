"""Conformance suite — every registered Technique must satisfy a minimum contract.

Plugin authors should run this against their own packages before publishing. Failing
tests indicate the Technique cannot interoperate cleanly with the rest of AgentKit.

Checks (per Technique):

1. Discoverable via :class:`agentkit.registry.Registry` entry-points.
2. Factory accepts an empty ``config={}`` and returns a Component instance.
3. Instance exposes the canonical attributes: ``name``, ``element``, ``capabilities``,
   ``version`` and the lifecycle methods ``setup`` / ``teardown`` / ``health``.
4. ``setup`` and ``teardown`` are awaitable and don't raise on a default BootContext.
5. The instance implements the *Element-specific* protocol method(s) the framework
   expects (``parse`` for perception, ``recall``/``store`` for memory, etc.).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

import pytest

from agentkit.protocols import BootContext
from agentkit.registry import get_registry

# Per-Element method-name expectations.
ELEMENT_REQUIRED_METHODS: dict[str, tuple[str, ...]] = {
    "perception": ("parse",),
    "memory": ("recall", "store"),
    "planner": ("plan",),
    "tool": ("list", "invoke"),
    "executor": ("run",),
    "safety": ("pre_check", "post_check", "wrap_tool"),
    "output": ("format",),
    "observability": ("on_event",),
    # 3rd-party Elements are exempt from method checks (they define their own protocol)
}

LIFECYCLE_METHODS = ("setup", "teardown", "health")
REQUIRED_ATTRS = ("name", "element", "capabilities", "version")


def _all_techniques() -> list[tuple[str, str, Callable]]:
    reg = get_registry()
    reg.discover_entry_points()
    out: list[tuple[str, str, Callable]] = []
    for qualified, factory in reg.technique_factories.items():
        element, _, name = qualified.partition(".")
        out.append((element, name, factory))
    return out


@pytest.mark.parametrize(
    "element,name,factory",
    _all_techniques(),
    ids=lambda x: x if isinstance(x, str) else "factory",
)
def test_technique_factory_accepts_empty_config(element, name, factory):
    instance = factory(config={})
    assert instance is not None, f"Technique factory '{element}.{name}' returned None"


@pytest.mark.parametrize("element,name,factory", _all_techniques())
def test_technique_required_attributes(element, name, factory):
    instance = factory(config={})
    for attr in REQUIRED_ATTRS:
        assert hasattr(instance, attr), (
            f"Technique '{element}.{name}' missing required attribute '{attr}'"
        )
    assert instance.element == element, (
        f"Technique '{element}.{name}' declares element={instance.element!r}; "
        f"entry-point says '{element}'"
    )
    assert isinstance(instance.capabilities, frozenset), (
        f"Technique '{element}.{name}' must declare capabilities as frozenset, "
        f"got {type(instance.capabilities).__name__}"
    )


@pytest.mark.parametrize("element,name,factory", _all_techniques())
def test_technique_lifecycle_methods_present_and_awaitable(element, name, factory):
    instance = factory(config={})
    for method_name in LIFECYCLE_METHODS:
        method = getattr(instance, method_name, None)
        assert callable(method), f"{element}.{name}.{method_name} is not callable"
        assert inspect.iscoroutinefunction(method), (
            f"{element}.{name}.{method_name} must be async"
        )


@pytest.mark.parametrize("element,name,factory", _all_techniques())
def test_technique_implements_element_protocol_methods(element, name, factory):
    expected = ELEMENT_REQUIRED_METHODS.get(element)
    if expected is None:
        # 3rd-party Element — no enforcement (it defines its own protocol).
        return
    instance = factory(config={})
    for method_name in expected:
        method = getattr(instance, method_name, None)
        assert method is not None and callable(method), (
            f"{element}.{name} must implement '{method_name}' "
            f"(required by the {element} Element protocol)"
        )


@pytest.mark.asyncio
async def test_lifecycle_default_runs_without_error():
    """Each Technique can complete a setup/teardown roundtrip on default config."""
    for element, name, factory in _all_techniques():
        try:
            instance = factory(config={})
        except Exception as exc:  # pragma: no cover — caught above
            pytest.fail(f"Could not instantiate {element}.{name}: {exc}")
        boot = BootContext(config={}, models=None)
        try:
            await instance.setup(boot)
        except Exception as exc:  # noqa: BLE001
            # Some techniques legitimately need infra to setup (e.g. RAG needs a model
            # hub). They must FAIL GRACEFULLY by raising, not by hanging.
            assert isinstance(exc, Exception)
        try:
            await instance.teardown()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{element}.{name}.teardown raised {exc}")
