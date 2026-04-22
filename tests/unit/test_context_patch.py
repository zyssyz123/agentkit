"""ContextPatch / AgentContext immutability + apply semantics."""

from __future__ import annotations

from dataclasses import replace

import pytest

from aglet.context import AgentContext, ContextPatch, MemoryItem, Message, ParsedInput


def test_context_is_immutable():
    ctx = AgentContext(conversation_id="c1")
    with pytest.raises(Exception):  # frozen dataclass raises FrozenInstanceError
        ctx.conversation_id = "c2"  # type: ignore[misc]


def test_patch_apply_replaces_scalar_field():
    ctx = AgentContext()
    patch = ContextPatch(changes={"parsed_input": ParsedInput(query="hello")})
    new_ctx = patch.apply_to(ctx)
    assert ctx.parsed_input is None
    assert new_ctx.parsed_input is not None and new_ctx.parsed_input.query == "hello"


def test_patch_append_extends_tuple():
    item_a = MemoryItem(content="a", source="t")
    item_b = MemoryItem(content="b", source="t")
    ctx = AgentContext(recalled_memory=(item_a,))
    patch = ContextPatch(changes={"recalled_memory_append": [item_b]})
    out = patch.apply_to(ctx)
    assert out.recalled_memory == (item_a, item_b)


def test_patch_empty_is_noop():
    ctx = AgentContext(history=(Message(role="user", content="x"),))
    out = ContextPatch.empty().apply_to(ctx)
    assert out is ctx


def test_patch_append_on_non_tuple_raises():
    ctx = AgentContext()
    bad = ContextPatch(changes={"raw_input_append": ["x"]})
    with pytest.raises(TypeError):
        bad.apply_to(ctx)


def test_patch_handles_list_to_tuple_coercion():
    item = MemoryItem(content="x", source="t")
    ctx = AgentContext()
    patch = ContextPatch(changes={"recalled_memory": [item, item]})
    out = patch.apply_to(ctx)
    assert isinstance(out.recalled_memory, tuple) and len(out.recalled_memory) == 2


def test_context_helpers_return_new_context():
    ctx = AgentContext()
    new = ctx.append_history(Message(role="user", content="hi"))
    assert ctx.history == ()
    assert len(new.history) == 1
    assert new is not ctx
