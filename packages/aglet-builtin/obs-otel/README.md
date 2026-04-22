# aglet-builtin-obs-otel

> OpenTelemetry observability technique for Aglet.

Part of the [Aglet](https://github.com/zyssyz123/agentkit) pluggable Agent runtime — a framework where every
Element (perception, memory, planner, tool, executor, safety, output, observability,
extensibility) **and** every Technique within an Element is a swappable plugin
distributed as its own PyPI package.

## Install

```bash
pip install aglet-builtin-obs-otel
```

This package registers itself with Aglet's `Registry` at import time via
Python entry points. Once installed, list it with:

```bash
aglet techniques        # if your installed version of aglet-cli is recent
```

## Usage

In your `agent.yaml`:

```yaml
elements:
  # Add the Element / technique block this package contributes.
```

See the [main repo's examples](https://github.com/zyssyz123/agentkit/tree/main/examples) for full configurations.

## License

Apache-2.0
