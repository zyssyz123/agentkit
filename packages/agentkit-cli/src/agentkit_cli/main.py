"""AgentKit CLI entry point.

Commands:
  init <dir>                        # scaffold a new agent
  run <agent.yaml> --input "..."    # run one turn locally
  elements                          # list registered Elements
  techniques [--element NAME]       # list registered Techniques
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from agentkit.config import load_agent_config
from agentkit.events import EventType
from agentkit.protocols import ELEMENT_NAMES
from agentkit.registry import get_registry
from agentkit.runtime import Runtime

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="AgentKit — pluggable Agent runtime.",
)
console = Console()


# ---------- init ------------------------------------------------------------------------------


SCAFFOLD_AGENT_YAML = """\
schema_version: "1.0"
name: {name}
description: An echo agent built with AgentKit M1.

elements:
  perception:
    techniques:
      - name: passthrough

  memory:
    techniques:
      - name: sliding_window
        config:
          max_messages: 20

  planner:
    techniques:
      - name: echo
        config:
          prefix: "Echo: "
          suffix: ""

  safety:
    techniques:
      - name: budget_only

  output:
    techniques:
      - name: streaming_text
        config:
          chunk_size: 16

  observability:
    techniques:
      - name: console
      - name: jsonl
        config:
          directory: .agentkit/runs

budget:
  max_steps: 5
  max_tokens: 5000
  max_seconds: 30
  max_cost_usd: 0.01

store:
  type: jsonl
  directory: .agentkit/runs
"""


@app.command()
def init(
    directory: Annotated[
        Path, typer.Argument(help="Target directory; created if it does not exist.")
    ],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Agent name; defaults to the directory name."),
    ] = None,
) -> None:
    """Scaffold a new agent project."""
    directory.mkdir(parents=True, exist_ok=True)
    agent_yaml = directory / "agent.yaml"
    if agent_yaml.exists():
        console.print(f"[yellow]agent.yaml already exists at {agent_yaml}; not overwriting.[/]")
        raise typer.Exit(code=1)
    agent_name = name or directory.name
    agent_yaml.write_text(SCAFFOLD_AGENT_YAML.format(name=agent_name), encoding="utf-8")
    console.print(f"[green]Scaffolded[/] [bold]{agent_yaml}[/]")
    console.print(f"\nNext step: [cyan]cd {directory}[/] && [cyan]agentkit run agent.yaml --input \"hello\"[/]")


# ---------- run -------------------------------------------------------------------------------


@app.command()
def run(
    config_path: Annotated[Path, typer.Argument(help="Path to agent.yaml")],
    input_text: Annotated[str, typer.Option("--input", "-i", help="User input text")],
    conversation: Annotated[
        str, typer.Option("--conversation", "-c", help="Conversation id (for multi-turn)")
    ] = "default",
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress event prints from Observability")
    ] = False,
) -> None:
    """Run a single turn against an agent.yaml file."""
    if not config_path.exists():
        console.print(f"[red]agent.yaml not found:[/] {config_path}")
        raise typer.Exit(code=1)

    cfg = load_agent_config(config_path)
    runtime = Runtime.from_config(cfg)

    final_chunks: list[str] = []
    run_id_holder: dict[str, str] = {"id": ""}

    async def _drive() -> None:
        async for ev in runtime.run(input_text, conversation_id=conversation):
            if ev.type == EventType.RUN_STARTED and isinstance(ev.payload, dict):
                run_id_holder["id"] = ev.payload.get("run_id", "")
            if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
                final_chunks.append(ev.payload.get("text", ""))

    try:
        asyncio.run(_drive())
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted by user[/]")
        raise typer.Exit(code=130)

    if quiet:
        sys.stdout.write("".join(final_chunks))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        console.rule("[bold]Output[/]")
        console.print("".join(final_chunks))
        console.rule()
        if run_id_holder["id"]:
            console.print(f"[dim]Run id: {run_id_holder['id']}[/]")


# ---------- elements / techniques -------------------------------------------------------------


@app.command()
def elements() -> None:
    """List Elements known to the registry."""
    registry = get_registry()
    registry.discover_entry_points()
    table = Table(title="AgentKit Elements")
    table.add_column("Element")
    table.add_column("Source")
    builtins = set(ELEMENT_NAMES)
    for name in registry.known_elements():
        table.add_row(name, "built-in" if name in builtins else "third-party")
    console.print(table)


@app.command()
def techniques(
    element: Annotated[
        Optional[str], typer.Option("--element", "-e", help="Filter by element kind")
    ] = None,
) -> None:
    """List registered Techniques."""
    registry = get_registry()
    registry.discover_entry_points()
    rows = registry.list_techniques(element)
    table = Table(title="AgentKit Techniques")
    table.add_column("Element")
    table.add_column("Name")
    for qualified in rows:
        el, _, nm = qualified.partition(".")
        table.add_row(el, nm)
    console.print(table)


if __name__ == "__main__":
    app()
