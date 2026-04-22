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
        return max(0.0, self.max_seconds - (time.monotonic() - self.started_at))

    def exceeded(self) -> bool:
        return (
            self.used_steps >= self.max_steps
            or self.used_tokens >= self.max_tokens
            or self.used_cost_usd >= self.max_cost_usd
            or self.remaining_seconds() <= 0
        )

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
