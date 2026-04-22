"""Budget unit tests."""

from __future__ import annotations

import time

from aglet.budget import Budget


def test_zero_means_unlimited_for_each_dimension():
    b = Budget(max_steps=0, max_tokens=0, max_cost_usd=0.0, max_seconds=0)
    assert not b.exceeded()
    # Even after consuming tokens, zero-limited dimensions stay unlimited.
    b = b.consume(steps=1000, tokens=1_000_000, cost_usd=999.99)
    assert not b.exceeded()


def test_positive_step_limit_triggers_when_reached():
    b = Budget(max_steps=2, max_tokens=0, max_cost_usd=0.0, max_seconds=0)
    assert not b.exceeded()
    b = b.consume(steps=1)
    assert not b.exceeded()
    b = b.consume(steps=1)
    assert b.exceeded()


def test_consume_is_immutable_and_additive():
    b = Budget(max_steps=10, max_tokens=100)
    b2 = b.consume(steps=2, tokens=30)
    assert (b.used_steps, b.used_tokens) == (0, 0)
    assert (b2.used_steps, b2.used_tokens) == (2, 30)


def test_wall_clock_limit():
    b = Budget(max_steps=0, max_tokens=0, max_cost_usd=0.0, max_seconds=0.05)
    time.sleep(0.06)
    assert b.exceeded()
