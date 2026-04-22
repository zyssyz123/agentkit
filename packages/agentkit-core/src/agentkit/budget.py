"""Run-level budget tracking.

The Runtime enforces budgets unconditionally — they are the only safety guarantee
that no plugin can disable. Every step checks `Budget.exceeded()`; on overflow the
loop raises `BudgetExceededError` and the Output Element formats a graceful partial
result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace


class BudgetExceededError(RuntimeError):
    """Raised by the Runtime when the run's Budget is exhausted."""


@dataclass(frozen=True)
class Budget:
    """Hard limits enforced by the Runtime; replaces — not merges — on update."""

    max_steps: int = 20
    max_tokens: int = 50_000
    max_seconds: float = 120.0
    max_cost_usd: float = 0.50

    used_steps: int = 0
    used_tokens: int = 0
    used_cost_usd: float = 0.0
    started_at: float = field(default_factory=time.monotonic)

    def remaining_seconds(self) -> float:
        if self.max_seconds <= 0:
            return float("inf")
        return max(0.0, self.max_seconds - (time.monotonic() - self.started_at))

    def exceeded(self) -> bool:
        """Return True iff any *positive* limit has been reached.

        A limit set to ``0`` (or negative) means **unlimited** for that dimension —
        useful when callers don't care about cost / tokens but still want to bound
        steps and wall-clock time.
        """
        if self.max_steps > 0 and self.used_steps >= self.max_steps:
            return True
        if self.max_tokens > 0 and self.used_tokens >= self.max_tokens:
            return True
        if self.max_cost_usd > 0 and self.used_cost_usd >= self.max_cost_usd:
            return True
        if self.max_seconds > 0 and self.remaining_seconds() <= 0:
            return True
        return False

    def consume(
        self,
        *,
        steps: int = 0,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> Budget:
        """Return a new Budget with usage advanced (immutable)."""
        return replace(
            self,
            used_steps=self.used_steps + steps,
            used_tokens=self.used_tokens + tokens,
            used_cost_usd=self.used_cost_usd + cost_usd,
        )
