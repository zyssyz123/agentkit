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
from agentkit.context import Message
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


# ---------- chat (multi-turn REPL) -----------------------------------------------------------


@app.command()
def chat(
    config_path: Annotated[Path, typer.Argument(help="Path to agent.yaml")],
    conversation: Annotated[
        str, typer.Option("--conversation", "-c", help="Conversation id (controls memory scope)")
    ] = "default",
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress event prints from Observability")
    ] = False,
) -> None:
    """Open an interactive multi-turn chat against an agent.yaml file.

    Runs the agent once per user message; conversation history (alternating user / assistant
    turns) is threaded through ``ctx.history`` so the planner sees the full context.
    Type ``/exit`` or hit Ctrl-D to quit, ``/reset`` to clear history.
    """
    if not config_path.exists():
        console.print(f"[red]agent.yaml not found:[/] {config_path}")
        raise typer.Exit(code=1)

    cfg = load_agent_config(config_path)
    runtime = Runtime.from_config(cfg)
    history: list[Message] = []
    console.print(
        f"[bold]agentkit chat[/] — agent=[cyan]{cfg.name}[/], conversation=[cyan]{conversation}[/]\n"
        "[dim]Type /exit to quit, /reset to clear history.[/]"
    )

    async def _one_turn(user_text: str) -> str:
        prior = tuple(history)  # snapshot before recording the new user turn
        collected: list[str] = []
        async for ev in runtime.run(
            user_text,
            conversation_id=conversation,
            history=prior,
        ):
            if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
                collected.append(ev.payload.get("text", ""))
        return "".join(collected)

    while True:
        try:
            line = console.input("[bold cyan]you›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            break
        if line == "/reset":
            history.clear()
            console.print("[yellow]history cleared[/]")
            continue
        try:
            answer = asyncio.run(_one_turn(line))
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]error:[/] {exc}")
            continue
        history.append(Message(role="user", content=line))
        history.append(Message(role="assistant", content=answer))
        if quiet:
            sys.stdout.write(answer + "\n")
            sys.stdout.flush()
        else:
            console.print(f"[bold green]agent›[/] {answer}\n")


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


# ---------- doctor ---------------------------------------------------------------------------


@app.command()
def doctor(
    config_path: Annotated[
        Optional[Path],
        typer.Argument(help="Optional agent.yaml to validate."),
    ] = None,
) -> None:
    """Inspect the local install + (optionally) validate an agent.yaml.

    Prints what's discovered + what each agent.yaml element/technique resolves to
    so you can debug "Unknown technique" errors quickly.
    """
    registry = get_registry()
    registry.discover_entry_points()

    console.print("[bold]agentkit doctor[/]")
    console.print(f"  python : {sys.version.split()[0]}")
    console.print(
        f"  techniques discovered : [green]{len(registry.technique_factories)}[/]"
    )
    console.print(f"  custom Elements registered : {len(registry.elements)}")
    if registry.elements:
        for name in sorted(registry.elements):
            console.print(f"    - [cyan]{name}[/]  ({registry.elements[name].__module__})")

    if config_path is None:
        return

    if not config_path.exists():
        console.print(f"\n[red]agent.yaml not found:[/] {config_path}")
        raise typer.Exit(code=1)

    try:
        cfg = load_agent_config(config_path)
    except Exception as exc:  # noqa: BLE001
        console.print(f"\n[red]Failed to parse {config_path}:[/]\n  {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"\n[bold]Validating[/] {config_path} (agent: [cyan]{cfg.name}[/])")

    problems: list[str] = []
    for element_name, element_cfg in cfg.elements.items():
        for tech_cfg in element_cfg.techniques:
            qualified = f"{element_name}.{tech_cfg.name}"
            if qualified in registry.technique_factories:
                console.print(f"  [green]ok[/]  {qualified}")
            else:
                same_element = registry.list_techniques(element_name)
                hint = (
                    f" (available for '{element_name}': "
                    f"{', '.join(t.split('.', 1)[1] for t in same_element) or '<none>'})"
                )
                problems.append(f"unknown technique '{qualified}'{hint}")
                console.print(f"  [red]missing[/] {qualified}")

    if cfg.providers:
        from agentkit.models import ModelHub

        factories = ModelHub.discover_factories()
        for prov in cfg.providers:
            if prov.type in factories:
                console.print(f"  [green]ok[/]  provider {prov.name} -> {prov.type}")
            else:
                problems.append(
                    f"provider '{prov.name}' wants type '{prov.type}' which is not installed"
                )
                console.print(f"  [red]missing[/] provider type {prov.type}")

    if problems:
        console.print(f"\n[red]{len(problems)} problem(s) found.[/]")
        raise typer.Exit(code=2)
    console.print("\n[green]All elements / techniques / providers resolve cleanly.[/]")


if __name__ == "__main__":
    app()
