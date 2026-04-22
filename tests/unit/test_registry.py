"""Registry unit tests."""

from __future__ import annotations

import pytest

from agentkit.registry import Registry


def test_register_and_get_technique_factory():
    reg = Registry()

    def factory(config=None):
        return ("planner", config)

    reg.register_technique("planner", "myplan", factory)
    out = reg.get_technique_factory("planner", "myplan")(config={"k": 1})
    assert out == ("planner", {"k": 1})


def test_get_unknown_technique_raises_clear_error():
    reg = Registry()
    with pytest.raises(KeyError, match="planner.does_not_exist"):
        reg.get_technique_factory("planner", "does_not_exist")


def test_list_techniques_filtered_by_element():
    reg = Registry()
    reg.register_technique("memory", "a", lambda config=None: None)
    reg.register_technique("memory", "b", lambda config=None: None)
    reg.register_technique("planner", "c", lambda config=None: None)
    assert reg.list_techniques("memory") == ["memory.a", "memory.b"]
    assert reg.list_techniques() == ["memory.a", "memory.b", "planner.c"]


def test_known_elements_includes_builtins_first():
    reg = Registry()
    reg.register_element("compliance", object)
    names = reg.known_elements()
    assert names[:9] == [
        "perception",
        "memory",
        "planner",
        "tool",
        "executor",
        "safety",
        "output",
        "observability",
        "extensibility",
    ]
    assert "compliance" in names


def test_re_registering_technique_emits_warning_but_overrides(caplog):
    reg = Registry()
    reg.register_technique("memory", "a", lambda c=None: 1)
    reg.register_technique("memory", "a", lambda c=None: 2)
    assert reg.get_technique_factory("memory", "a")() == 2
