# AgentKit

> Make every Agent capability a swappable plugin.

A pluggable Agent runtime with two-dimensional extensibility:

- **Element layer** — 9 first-class concerns (Perception, Memory, Planner, Tool, Executor, Safety, Output, Observability, Extensibility); third parties can introduce entirely new Elements.
- **Technique layer** — every Element hosts N concrete implementations selected via YAML; ship as PyPI / git packages.

A single declarative `agent.yaml` boots a complete, observable, extensible Agent.

## Quick start (M1 skeleton)

```bash
# from a checkout of this monorepo
uv sync

# scaffold a new agent
uv run agentkit init my-agent
cd my-agent

# run it
uv run agentkit run agent.yaml --input "Hello, AgentKit!"
```

Inspect the run trace:

```bash
ls .agentkit/runs/
```

## Repository layout

```
packages/
  agentkit-core/        # protocols + runtime + event bus + loader
  agentkit-cli/         # Typer-based CLI
  agentkit-builtin/*    # one PyPI package per built-in technique
examples/
  echo-agent/           # M1 end-to-end example
docs/
  architecture.md       # full PRD + TDD (mirror of Confluence page)
```

## Status

M1 (skeleton). See `docs/architecture.md` for the full design and roadmap.

## License

Apache 2.0
