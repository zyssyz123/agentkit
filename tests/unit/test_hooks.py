"""HookManager unit tests."""

from __future__ import annotations

import pytest

from agentkit.context import AgentContext, ContextPatch
from agentkit.hooks import HookManager, _glob_match, _is_valid_pattern


def test_pattern_validation_accepts_canonical_shapes():
    assert _is_valid_pattern("before.tool.invoke")
    assert _is_valid_pattern("after.memory.recall")
    assert _is_valid_pattern("error.planner.plan")
    assert _is_valid_pattern("*.tool.*")
    assert _is_valid_pattern("after.*.invoke")


def test_pattern_validation_rejects_garbage():
    assert not _is_valid_pattern("invalid")
    assert not _is_valid_pattern("two.parts")
    assert not _is_valid_pattern("five.parts.are.too.many")
    assert not _is_valid_pattern("during.tool.invoke")  # phase invalid
    assert not _is_valid_pattern("before..invoke")
    assert not _is_valid_pattern("before.tool.")


def test_glob_match_segments():
    assert _glob_match("before.tool.invoke", "before.tool.invoke")
    assert _glob_match("after.tool.*", "after.tool.invoke")
    assert _glob_match("*.tool.invoke", "after.tool.invoke")
    assert _glob_match("*.*.*", "before.memory.recall")
    assert not _glob_match("before.tool.invoke", "after.tool.invoke")
    assert not _glob_match("before.*.recall", "before.tool.invoke")


@pytest.mark.asyncio
async def test_subscribe_and_fire_returns_patches_in_order():
    hm = HookManager()
    seen: list[str] = []

    async def h1(name, ctx, payload):
        seen.append(f"h1:{name}")
        return ContextPatch(changes={"metadata": {"h1": True}})

    async def h2(name, ctx, payload):
        seen.append(f"h2:{name}")
        return None  # side-effect-only

    hm.subscribe("after.tool.invoke", h1, label="h1")
    hm.subscribe("after.tool.*", h2, label="h2")

    patches = await hm.fire("after", "tool", "invoke", AgentContext(), {})
    assert seen == ["h1:after.tool.invoke", "h2:after.tool.invoke"]
    assert len(patches) == 1 and patches[0].changes == {"metadata": {"h1": True}}


@pytest.mark.asyncio
async def test_fire_with_no_match_returns_empty():
    hm = HookManager()

    async def h(*args, **kwargs):
        raise AssertionError("must not fire")

    hm.subscribe("before.tool.invoke", h)
    out = await hm.fire("before", "memory", "recall", AgentContext(), {})
    assert out == []


@pytest.mark.asyncio
async def test_subscriber_exception_is_swallowed_and_other_subscribers_still_run():
    hm = HookManager()
    survivors: list[str] = []

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    async def good(*args, **kwargs):
        survivors.append("ok")
        return None

    hm.subscribe("*.*.*", boom)
    hm.subscribe("*.*.*", good)
    out = await hm.fire("after", "tool", "invoke", AgentContext(), {})
    assert survivors == ["ok"]
    assert out == []  # boom returned no patch; good returned None


@pytest.mark.asyncio
async def test_unsubscribe_removes_handler():
    hm = HookManager()
    calls: list[str] = []

    async def h(*args, **kwargs):
        calls.append("h")
        return None

    unsub = hm.subscribe("*.*.*", h)
    await hm.fire("after", "tool", "invoke", AgentContext(), {})
    unsub()
    await hm.fire("after", "tool", "invoke", AgentContext(), {})
    assert calls == ["h"]


def test_invalid_pattern_at_subscribe_raises():
    hm = HookManager()

    async def noop(*a, **k):
        return None

    with pytest.raises(ValueError):
        hm.subscribe("garbage", noop)
