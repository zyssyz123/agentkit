"""JSONL ContextStore — durable, human-readable per-run trace files.

Writes a single ``<run_id>.jsonl`` under the configured directory. Each line is a JSON
object: ``{"kind": "patch"|"event", ...}``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import anyio

from aglet.context import AgentContext, ContextPatch
from aglet.events import Event


class JsonlContextStore:
    def __init__(self, directory: str | Path = ".aglet/runs") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.directory / f"{run_id}.jsonl"

    async def _write_line(self, run_id: str, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, default=_json_default, ensure_ascii=False)
        path = self._path(run_id)
        # anyio.to_thread keeps file I/O off the event loop.
        await anyio.to_thread.run_sync(_append_line, path, line)

    async def append_patch(self, run_id: str, patch: ContextPatch) -> None:
        await self._write_line(
            run_id,
            {
                "kind": "patch",
                "ts": patch.ts.isoformat(),
                "element": patch.source_element,
                "technique": patch.source_technique,
                "changes": patch.changes,
            },
        )

    async def append_event(self, run_id: str, event: Event) -> None:
        await self._write_line(run_id, {"kind": "event", **event.to_dict()})

    async def load_patches(self, run_id: str) -> list[ContextPatch]:
        path = self._path(run_id)
        if not path.exists():
            return []
        out: list[ContextPatch] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("kind") != "patch":
                continue
            out.append(
                ContextPatch(
                    changes=obj.get("changes", {}),
                    source_element=obj.get("element", ""),
                    source_technique=obj.get("technique", ""),
                    ts=datetime.fromisoformat(obj["ts"]),
                )
            )
        return out

    async def load_events(self, run_id: str) -> list[Event]:
        # We persist events as opaque dicts; resume() uses them only for status
        # detection (e.g. "did the run complete?"). Returning the raw dicts cast
        # to Event is overkill — return a thin wrapper list.
        path = self._path(run_id)
        if not path.exists():
            return []
        from aglet.events import EventType

        out: list[Event] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("kind") != "event":
                continue
            try:
                etype = EventType(obj["type"])
            except (KeyError, ValueError):
                continue
            out.append(
                Event(
                    type=etype,
                    element=obj.get("element", ""),
                    technique=obj.get("technique", ""),
                    payload=obj.get("payload"),
                    ts=datetime.fromisoformat(obj["ts"]),
                    span_id=obj.get("span_id", ""),
                    parent_span_id=obj.get("parent_span_id"),
                )
            )
        return out

    async def rebuild(self, run_id: str, base: AgentContext) -> AgentContext:
        ctx = base
        for patch in await self.load_patches(run_id):
            ctx = patch.apply_to(ctx)
        return ctx

    async def list_runs(self) -> list[str]:
        if not self.directory.exists():
            return []
        return sorted(
            p.stem for p in self.directory.glob("*.jsonl") if not p.name.endswith(".events.jsonl")
        )

    async def has_run(self, run_id: str) -> bool:
        return self._path(run_id).exists()


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return repr(obj)
