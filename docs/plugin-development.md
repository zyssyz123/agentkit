# Plugin development guide

Aglet is pluggable on two independent axes:

1. **Technique layer** — implement a new concrete technique under an existing
   Element kind. *Most* community contributions will live here.
2. **Element layer** — contribute a wholly new kind of Element the framework
   doesn't know about yet (e.g. `compliance`, `intent`, `consent`).

Both axes are distributed as standalone PyPI packages. Aglet auto-discovers
them via Python `entry_points`; no core changes or PRs required.

---

## Quick comparison

|                          | New Technique                                | Brand-new Element                                              |
| ------------------------ | -------------------------------------------- | -------------------------------------------------------------- |
| Changes to `aglet` core  | **None**                                     | **None**                                                       |
| Protocol definition      | Reuse the existing one (e.g. `MemoryTechnique`) | Define your own (a `typing.Protocol`)                       |
| Entry-point group(s)     | `aglet.techniques` only                      | `aglet.elements` + `aglet.techniques`                         |
| How the Runtime picks it up | `ElementHost` dispatches to your class automatically | Runtime creates a generic `ElementHost` under `hub.custom[...]`; you typically invoke it via a hook or a custom wrapper |

---

## Scenario 1 — A new Technique inside an existing Element

Example: `memory.entity` — a Memory technique that tracks named entities
across a conversation. Full working source under
`examples/third-party-memory-entity/`.

### 1. Scaffold the package

You can generate the skeleton with the CLI:

```bash
aglet plugin new my-entity-memory --element memory --technique entity
```

This creates:

```
my-entity-memory/
├── pyproject.toml
└── src/
    └── my_entity_memory/
        └── __init__.py
```

### 2. Implement the technique

Your class must speak the Element's **existing** protocol. For
`memory` that means `async def recall(ctx, query) -> ContextPatch` and
`async def store(ctx, item) -> ContextPatch`:

```python
from aglet.context import AgentContext, ContextPatch, MemoryItem

class EntityMemory:
    name = "entity"
    element = "memory"
    version = "0.1.0"
    capabilities = frozenset({"recall", "store"})

    def __init__(self, config: dict | None = None) -> None:
        self._store: dict[str, list[str]] = {}

    async def setup(self, ctx) -> None: ...
    async def teardown(self) -> None: ...
    async def health(self):
        from aglet.protocols import HealthStatus
        return HealthStatus(healthy=True)

    async def recall(self, ctx: AgentContext, query: str) -> ContextPatch:
        # Return a ContextPatch that appends MemoryItem(s) you want the
        # planner to see via ctx.recalled_memory.
        items = [MemoryItem(content="…", source=f"{self.element}.{self.name}")]
        return ContextPatch(
            changes={"recalled_memory_append": items},
            source_element=self.element,
            source_technique=self.name,
        )

    async def store(self, ctx: AgentContext, item: MemoryItem) -> ContextPatch:
        # Persist whatever you want; return ContextPatch.empty() for no-ops.
        return ContextPatch.empty(self.element, self.name)
```

### 3. Declare the entry point

`pyproject.toml`:

```toml
[project]
name = "my-entity-memory"
version = "0.1.0"
dependencies = ["aglet>=0.1.0a4"]

[project.entry-points."aglet.techniques"]
"memory.entity" = "my_entity_memory:EntityMemory"
```

### 4. Install and use

```bash
aglet plugin install /path/to/my-entity-memory   # wraps pip install
aglet techniques --element memory                 # → `entity` appears
```

`agent.yaml`:

```yaml
elements:
  memory:
    techniques:
      - { name: sliding_window }
      - name: entity
        config: { top_k: 5 }
    routing: parallel_merge
```

That's it. Run `aglet run agent.yaml --input "…"` and your memory
technique is live.

---

## Scenario 2 — A brand-new Element kind

Example: `intent` — classify user messages into typed labels, surface the
result as `ctx.metadata["intent"]`. Full working source under
`examples/third-party-intent-element/`.

### 1. Scaffold

```bash
aglet plugin new my-intent-plugin \
    --element intent --technique keyword --new-element
```

The `--new-element` flag tells the scaffolder to add a second
entry-point group (`aglet.elements`) so your Element kind is registered
alongside the built-in 9.

### 2. Declare the Element protocol

Any `typing.Protocol` subclass works. Pick the method shape that makes
sense for your domain:

```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from aglet.context import AgentContext

@dataclass(frozen=True)
class IntentLabel:
    name: str
    confidence: float = 1.0

@runtime_checkable
class IntentProtocol(Protocol):
    element_kind: str = "intent"
    async def classify(self, ctx: AgentContext) -> IntentLabel: ...
```

### 3. Implement one Technique

```python
from aglet.context import ContextPatch

class KeywordIntent:
    name = "keyword"
    element = "intent"
    version = "0.1.0"
    capabilities = frozenset({"classify"})

    def __init__(self, config: dict | None = None) -> None:
        cfg = config or {}
        self._rules = cfg.get("rules", [])
        self._default = cfg.get("default", "unknown")

    async def setup(self, ctx): ...
    async def teardown(self): ...
    async def health(self):
        from aglet.protocols import HealthStatus
        return HealthStatus(healthy=True)

    async def classify(self, ctx) -> IntentLabel:
        text = (ctx.raw_input.text or "").lower()
        for rule in self._rules:
            if any(kw in text for kw in rule["keywords"]):
                return IntentLabel(name=rule["label"])
        return IntentLabel(name=self._default, confidence=0.5)

    # Bridge into the canonical Loop via a hook — the Runtime does not
    # call `classify` itself, because it doesn't know about your Element.
    async def on_lifecycle(self, event_name, ctx, payload):
        if event_name.startswith("after.perception.parse"):
            label = await self.classify(ctx)
            return ContextPatch(
                changes={"metadata": {**ctx.metadata, "intent": {"name": label.name}}},
                source_element="intent",
                source_technique=self.name,
            )
        return None
```

### 4. Declare both entry points

```toml
[project.entry-points."aglet.elements"]
intent = "my_intent_plugin:IntentProtocol"

[project.entry-points."aglet.techniques"]
"intent.keyword" = "my_intent_plugin:KeywordIntent"
```

### 5. Install and wire it up

```bash
aglet plugin install /path/to/my-intent-plugin
aglet elements         # → `intent (third-party)` appears
```

`agent.yaml`:

```yaml
elements:
  intent:
    techniques:
      - name: keyword
        config:
          rules:
            - keywords: [debug, error, traceback]
              label: debug
            - keywords: [summarise, summary]
              label: summarise
          default: chit_chat

hooks:
  - on: after.perception.parse
    technique: intent.keyword
    config:
      rules:
        - keywords: [debug, error, traceback]
          label: debug
        - keywords: [summarise, summary]
          label: summarise
      default: chit_chat
```

Every turn, `ctx.metadata["intent"]` now carries the classified label,
available to downstream planners / memory techniques / output formatters.

### 6. Bridging strategies

The canonical Runtime Loop only knows how to drive the built-in 9
Elements. For a brand-new Element you typically use one of:

| Strategy                             | When to use                                                                                       |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ |
| **Hook** (as above)                  | You want the Element to fire at a specific lifecycle point (`before/after.*.*`). Simplest path. |
| **Custom Runtime**                   | You want your Element to be a peer of `planner` / `executor` with its own call-site in the loop. |
| **Helper inside an existing Technique** | Your Element is used directly by, say, a custom Planner technique that knows to call it.      |

---

## Debugging & publishing

### Verify local install

```bash
aglet plugin install .             # or: pip install -e .
aglet doctor path/to/agent.yaml    # lists green `ok` for each wired technique
aglet run path/to/agent.yaml --input "…"
```

### Run the conformance suite

The shipped tests at `tests/conformance/` are parametrised over every
registered Technique. Copy that suite into your own repo (or import it)
to smoke-test protocol compliance on every PR.

### Publish to PyPI

Every aglet plugin is an ordinary Python distribution — `uv build` and
`twine upload dist/*`. Once published:

```bash
pip install --pre your-aglet-plugin
```

is all your users need.

### Add to the curated marketplace

Open a PR against `docs/marketplace.json` in the main repo with one
entry for your plugin. The `aglet marketplace search` CLI picks it up
the moment it lands.

---

## Reference

- `aglet.context.ContextPatch` — what every technique method must return.
- `aglet.protocols` — each Element's expected method shape.
- `examples/third-party-element-demo/` — compliance Element (`scan(text)`).
- `examples/third-party-intent-element/` — intent Element + keyword technique.
- `examples/third-party-memory-entity/` — memory technique under existing Element.
- `tests/integration/test_third_party_element.py` — end-to-end validation that
  the whole pluggability story works.
