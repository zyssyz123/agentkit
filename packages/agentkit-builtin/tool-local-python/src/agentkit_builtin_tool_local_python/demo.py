"""Demo callables that any agent can wire up via the local_python Tool Technique."""

from __future__ import annotations


def echo(text: str = "") -> str:
    """Return the input verbatim."""
    return text


def now_iso() -> str:
    """Return the current UTC timestamp as ISO-8601."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
