"""Routing strategy unit tests."""

from __future__ import annotations

import pytest

from aglet.context import ContextPatch
from aglet.routing import (
    AllStrategy,
    FirstMatchStrategy,
    ParallelMergeStrategy,
    get_strategy,
)


class _Tech:
    def __init__(self, name: str, patch: ContextPatch | None) -> None:
        self.name = name
        self._patch = patch
        self.calls = 0

    async def call(self) -> ContextPatch | None:
        self.calls += 1
        return self._patch


@pytest.mark.asyncio
async def test_all_invokes_every_technique_and_merges_in_order():
    a = _Tech("a", ContextPatch(changes={"recalled_memory_append": ["A"]}))
    b = _Tech("b", ContextPatch(changes={"recalled_memory_append": ["B"]}))

    async def invoke(t):
        return await t.call()

    out = await AllStrategy().dispatch([a, b], invoke)
    assert isinstance(out, ContextPatch)
    assert out.changes["recalled_memory_append"] == ["A", "B"]
    assert (a.calls, b.calls) == (1, 1)


@pytest.mark.asyncio
async def test_first_match_short_circuits_on_non_empty_patch():
    empty = _Tech("a", ContextPatch.empty())
    hit = _Tech("b", ContextPatch(changes={"parsed_input": "x"}))
    skipped = _Tech("c", ContextPatch(changes={"parsed_input": "should_not_run"}))

    async def invoke(t):
        return await t.call()

    out = await FirstMatchStrategy().dispatch([empty, hit, skipped], invoke)
    assert out.changes["parsed_input"] == "x"
    assert (empty.calls, hit.calls, skipped.calls) == (1, 1, 0)


@pytest.mark.asyncio
async def test_parallel_merge_invokes_all_concurrently_and_merges():
    a = _Tech("a", ContextPatch(changes={"scratchpad_append": ["A"]}))
    b = _Tech("b", ContextPatch(changes={"scratchpad_append": ["B"]}))

    async def invoke(t):
        return await t.call()

    out = await ParallelMergeStrategy().dispatch([a, b], invoke)
    assert sorted(out.changes["scratchpad_append"]) == ["A", "B"]
    assert (a.calls, b.calls) == (1, 1)


def test_get_strategy_unknown_raises():
    with pytest.raises(ValueError, match="Unknown routing strategy"):
        get_strategy("does_not_exist")


def test_get_strategy_returns_singleton_per_name():
    assert get_strategy("all") is get_strategy("all")
