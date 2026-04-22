"""Cross-process serialisation for AgentContext / ContextPatch / ToolResult.

The wire format is intentionally lossy and JSON-friendly. Out-of-process plugins receive
**dict** snapshots, not Python objects — they reply with dicts. The Runtime rebuilds the
full Python types on this side using dedicated helpers.

Goals
-----

* Round-trip the fields a Technique actually needs (raw_input, parsed_input.query,
  history.messages, recalled_memory.contents, scratchpad, plan, available_tools,
  tool_calls, tool_results, budget, conversation_id, user_id, metadata).
* Stay JSON-compatible — every value must be ``json.dumps``-able.
* Keep ContextPatch reconstruction trivial so plugins can return ``{"changes": {...},
  "source_element": "...", "source_technique": "..."}`` and the Runtime applies it.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from agentkit.context import (
    AgentContext,
    ContextPatch,
    MemoryItem,
    Message,
    ParsedInput,
    Plan,
    RawInput,
    Thought,
    ToolCall,
    ToolResult,
    ToolSpec,
)


def context_to_dict(ctx: AgentContext) -> dict[str, Any]:
    """Snapshot an AgentContext as a JSON-serialisable dict (lossy)."""
    return {
        "run_id": ctx.run_id,
        "conversation_id": ctx.conversation_id,
        "user_id": ctx.user_id,
        "raw_input": _safe_asdict(ctx.raw_input),
        "parsed_input": _safe_asdict(ctx.parsed_input) if ctx.parsed_input else None,
        "history": [_safe_asdict(m) for m in ctx.history],
        "recalled_memory": [_safe_asdict(i) for i in ctx.recalled_memory],
        "scratchpad": [_safe_asdict(t) for t in ctx.scratchpad],
        "plan": _safe_asdict(ctx.plan) if ctx.plan else None,
        "available_tools": [_safe_asdict(t) for t in ctx.available_tools],
        "tool_calls": [_safe_asdict(c) for c in ctx.tool_calls],
        "tool_results": [_safe_asdict(r) for r in ctx.tool_results],
        "budget": _safe_asdict(ctx.budget),
        "metadata": dict(ctx.metadata),
    }


def patch_from_dict(data: dict[str, Any]) -> ContextPatch:
    """Inverse of :func:`patch_to_dict` — accept a plugin's response and rebuild."""
    if not isinstance(data, dict):
        raise TypeError(f"ContextPatch dict expected; got {type(data).__name__}")
    return ContextPatch(
        changes=dict(data.get("changes") or {}),
        source_element=str(data.get("source_element", "")),
        source_technique=str(data.get("source_technique", "")),
    )


def patch_to_dict(patch: ContextPatch) -> dict[str, Any]:
    return {
        "changes": dict(patch.changes),
        "source_element": patch.source_element,
        "source_technique": patch.source_technique,
    }


def tool_result_from_dict(data: dict[str, Any]) -> ToolResult:
    return ToolResult(
        call_id=str(data.get("call_id", "")),
        output=data.get("output"),
        error=data.get("error"),
        latency_ms=int(data.get("latency_ms", 0)),
    )


def tool_specs_from_list(items: list[dict[str, Any]]) -> list[ToolSpec]:
    out: list[ToolSpec] = []
    for it in items:
        out.append(
            ToolSpec(
                name=str(it["name"]),
                description=str(it.get("description", "")),
                parameters_schema=dict(
                    it.get("parameters_schema") or {"type": "object", "properties": {}}
                ),
                technique=str(it.get("technique", "")),
            )
        )
    return out


def memory_item_to_dict(item: MemoryItem) -> dict[str, Any]:
    return _safe_asdict(item)


def memory_item_from_dict(data: dict[str, Any]) -> MemoryItem:
    return MemoryItem(
        content=str(data.get("content", "")),
        source=str(data.get("source", "")),
        score=data.get("score"),
        metadata=dict(data.get("metadata") or {}),
    )


# ---------- helpers ---------------------------------------------------------------------------


def _safe_asdict(obj: Any) -> Any:
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_asdict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_safe_asdict(v) for v in obj]
    return repr(obj)


__all__ = [
    "context_to_dict",
    "patch_from_dict",
    "patch_to_dict",
    "tool_result_from_dict",
    "tool_specs_from_list",
    "memory_item_to_dict",
    "memory_item_from_dict",
]
