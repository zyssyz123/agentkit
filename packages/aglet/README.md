# aglet

> The pluggable Agent runtime: protocols, runtime, event bus, plugin loader.

`aglet` is the core of [the Aglet project](https://github.com/zyssyz123/agentkit) — a
framework where every Agent capability is a swappable plugin distributed as its own
PyPI package.

## What's inside

* The 9 first-class **Element** protocols (perception / memory / planner / tool /
  executor / safety / output / observability / extensibility) plus the
  `ModelProvider` plugin point.
* An immutable `AgentContext` + `ContextPatch` event-sourcing model.
* The default canonical Loop (`Runtime.run` / `Runtime.resume`) with built-in
  Hook system, Budget enforcement, three routing strategies, and four plugin
  runtimes (in-process, subprocess, HTTP, MCP).
* A YAML config loader and a `Registry` that auto-discovers third-party
  Techniques via Python entry points (`aglet.techniques`, `aglet.models`,
  `aglet.elements`).

## Install

`aglet` alone is enough to **build** an agent in Python; install built-in
Techniques separately to actually **run** something useful.

```bash
pip install aglet                                          # core only
pip install aglet-cli aglet-builtin-planner-echo \
            aglet-builtin-perception-passthrough \
            aglet-builtin-output-streaming-text \
            aglet-builtin-memory-sliding-window \
            aglet-builtin-obs-console                      # smallest runnable agent
```

Then:

```bash
aglet init my-agent && cd my-agent
aglet run agent.yaml --input "hello"
```

## Status

Alpha (`0.1.0a1`) — the protocols are still subject to backwards-incompatible
change before `1.0`. Interfaces are documented in the
[architecture doc](https://github.com/zyssyz123/agentkit/blob/main/docs/architecture.md).

## License

Apache-2.0
