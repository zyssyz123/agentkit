"""Aglet CLI entry point.

Commands:
  init <dir>                        # scaffold a new agent
  run <agent.yaml> --input "..."    # run one turn locally
  chat <agent.yaml>                 # interactive multi-turn REPL
  elements                          # list registered Elements
  techniques [--element NAME]       # list registered Techniques
  doctor [agent.yaml]               # diagnose install + validate config
  plugin install <pypi|git>         # install an external plugin via uv pip
  plugin list                       # list installed aglet plugins
  plugin remove <pypi-name>         # uninstall a plugin
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from aglet.config import load_agent_config
from aglet.context import Message
from aglet.events import EventType
from aglet.protocols import ELEMENT_NAMES
from aglet.registry import get_registry
from aglet.runtime import Runtime

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Aglet — pluggable Agent runtime.",
)
console = Console()


# ---------- init ------------------------------------------------------------------------------


SCAFFOLD_AGENT_YAML = """\
schema_version: "1.0"
name: {name}
description: >
  Echo agent scaffolded by `aglet init`. Uses only the minimum set of
  Techniques listed in the README quickstart, so it runs straight out of
  `pip install --pre aglet aglet-cli aglet-builtin-*` without pulling any
  extra packages.

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

budget:
  max_steps: 5
  max_tokens: 5000
  max_seconds: 30
  max_cost_usd: 0.01

# The default JSONL trace store writes .aglet/runs/<run_id>.jsonl next to your
# agent — uncomment and install `aglet-builtin-obs-jsonl` to also stream every
# event into a separate per-run .events.jsonl file.
store:
  type: jsonl
  directory: .aglet/runs
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
    console.print(f"\nNext step: [cyan]cd {directory}[/] && [cyan]aglet run agent.yaml --input \"hello\"[/]")


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
        f"[bold]aglet chat[/] — agent=[cyan]{cfg.name}[/], conversation=[cyan]{conversation}[/]\n"
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
    table = Table(title="Aglet Elements")
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
    table = Table(title="Aglet Techniques")
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

    console.print("[bold]aglet doctor[/]")
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

    # --- sanity: the canonical Loop depends on these two Elements. ---
    from aglet.runtime import _RECOMMENDED_ELEMENTS, _REQUIRED_ELEMENTS

    for name in _REQUIRED_ELEMENTS:
        el = cfg.elements.get(name)
        if el is None or not el.techniques:
            problems.append(
                f"missing required element {name!r} (canonical Loop would emit nothing)"
            )
            console.print(f"  [red]error[/]   element [bold]{name}[/] has zero techniques")
    for name in _RECOMMENDED_ELEMENTS:
        el = cfg.elements.get(name)
        if el is None or not el.techniques:
            console.print(f"  [yellow]warn[/]   element [bold]{name}[/] has zero techniques")

    for element_name, element_cfg in cfg.elements.items():
        for tech_cfg in element_cfg.techniques:
            qualified = f"{element_name}.{tech_cfg.name}"
            if qualified in registry.technique_factories:
                console.print(f"  [green]ok[/]     {qualified}")
            else:
                same_element = registry.list_techniques(element_name)
                hint = (
                    f" (available for '{element_name}': "
                    f"{', '.join(t.split('.', 1)[1] for t in same_element) or '<none>'})"
                )
                problems.append(f"unknown technique '{qualified}'{hint}")
                console.print(f"  [red]missing[/] {qualified}")

    if cfg.providers:
        from aglet.models import ModelHub

        factories = ModelHub.discover_factories()
        for prov in cfg.providers:
            if prov.type in factories:
                console.print(f"  [green]ok[/]     provider {prov.name} -> {prov.type}")
            else:
                problems.append(
                    f"provider '{prov.name}' wants type '{prov.type}' which is not installed"
                )
                console.print(f"  [red]missing[/] provider type {prov.type}")

    if problems:
        console.print(f"\n[red]{len(problems)} problem(s) found.[/]")
        raise typer.Exit(code=2)
    console.print("\n[green]All elements / techniques / providers resolve cleanly.[/]")


# ---------- resume / runs ---------------------------------------------------------------------


@app.command()
def resume(
    config_path: Annotated[Path, typer.Argument(help="Path to agent.yaml")],
    run_id: Annotated[str, typer.Argument(help="run_id to resume from")],
    quiet: Annotated[bool, typer.Option("--quiet", "-q")] = False,
) -> None:
    """Resume a previously-checkpointed run.

    The store is consulted for the patch sequence captured under run_id; the
    AgentContext is rebuilt and the canonical Loop is re-entered. If the original
    run already completed, ``run.completed`` is replayed without re-running.
    """
    if not config_path.exists():
        console.print(f"[red]agent.yaml not found:[/] {config_path}")
        raise typer.Exit(code=1)

    cfg = load_agent_config(config_path)
    runtime = Runtime.from_config(cfg)

    final_chunks: list[str] = []
    resumed_completed = False

    async def _drive() -> None:
        nonlocal resumed_completed
        async for ev in runtime.resume(run_id):
            if ev.type == EventType.OUTPUT_CHUNK and isinstance(ev.payload, dict):
                final_chunks.append(ev.payload.get("text", ""))
            if ev.type == EventType.RUN_COMPLETED and isinstance(ev.payload, dict):
                if ev.payload.get("resumed"):
                    resumed_completed = True

    try:
        asyncio.run(_drive())
    except KeyError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1) from exc

    if quiet:
        sys.stdout.write("".join(final_chunks))
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        console.rule("[bold]Output (resumed)[/]")
        if resumed_completed:
            console.print(
                "[yellow]Run was already completed; replayed terminal event without re-running.[/]"
            )
        console.print("".join(final_chunks))
        console.rule()


@app.command(name="runs")
def runs(
    config_path: Annotated[
        Optional[Path], typer.Argument(help="Path to agent.yaml (used to find the store)")
    ] = None,
) -> None:
    """List run_ids previously checkpointed by an agent's store."""
    cfg = load_agent_config(config_path) if config_path else None
    if cfg is None or cfg.store.type != "jsonl":
        console.print(
            "[yellow]This command currently lists JSONL stores only. "
            "Pass an agent.yaml whose `store.type: jsonl`.[/]"
        )
        raise typer.Exit(code=1)
    from aglet.store import JsonlContextStore

    store = JsonlContextStore(cfg.store.directory)

    run_ids = asyncio.run(store.list_runs())
    table = Table(title=f"Checkpointed runs in {cfg.store.directory}")
    table.add_column("run_id")
    for rid in run_ids:
        table.add_row(rid)
    console.print(table)


# ---------- plugin install / list / remove ---------------------------------------------------


plugin_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Install / list / remove external Aglet plugins (PyPI or git).",
)
app.add_typer(plugin_app, name="plugin")


def _pip_command() -> list[str]:
    """Return a pip-equivalent command, preferring uv pip when available."""
    if shutil.which("uv"):
        return ["uv", "pip"]
    return [sys.executable, "-m", "pip"]


@plugin_app.command("install")
def plugin_install(
    target: Annotated[
        str,
        typer.Argument(
            help="PyPI distribution name, local path, or git+https URL",
        ),
    ],
) -> None:
    """Install an external Aglet plugin (e.g. ``aglet-builtin-model-litellm``,
    ``./my-plugin``, ``git+https://github.com/user/repo.git``)."""
    cmd = [*_pip_command(), "install", target]
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]install failed (exit {exc.returncode}).[/]")
        raise typer.Exit(code=exc.returncode) from exc

    # Re-discover so the freshly installed entry-points become visible immediately.
    registry = get_registry()
    before = set(registry.technique_factories)
    registry.discover_entry_points()
    new = sorted(set(registry.technique_factories) - before)
    if new:
        console.print(
            f"\n[green]Installed[/] [bold]{target}[/].  Newly registered Techniques:"
        )
        for n in new:
            console.print(f"  - {n}")
    else:
        console.print(
            f"\n[green]Installed[/] [bold]{target}[/], but no new Techniques registered. "
            "Did the plugin declare entry-points under 'aglet.techniques' / 'aglet.models' / 'aglet.elements'?"
        )


@plugin_app.command("list")
def plugin_list() -> None:
    """List installed PyPI distributions that publish at least one Aglet entry-point."""
    table = Table(title="Installed Aglet plugins")
    table.add_column("Distribution")
    table.add_column("Version")
    table.add_column("Entry-points contributed")

    rows: dict[str, dict] = {}
    for group in ("aglet.techniques", "aglet.models", "aglet.elements"):
        try:
            eps = importlib_metadata.entry_points(group=group)
        except TypeError:
            eps = importlib_metadata.entry_points().get(group, [])  # type: ignore[assignment]
        for ep in eps:
            dist = getattr(ep, "dist", None)
            dist_name = dist.metadata["Name"] if dist is not None else "<unknown>"
            row = rows.setdefault(
                dist_name,
                {
                    "version": dist.version if dist is not None else "?",
                    "groups": {},
                },
            )
            row["groups"].setdefault(group, []).append(ep.name)

    for name in sorted(rows):
        info = rows[name]
        contributed = []
        for group, names in sorted(info["groups"].items()):
            short = group.split(".", 1)[1]
            contributed.append(f"[cyan]{short}[/]: {', '.join(sorted(names))}")
        table.add_row(name, info["version"], "\n".join(contributed))
    console.print(table)


@plugin_app.command("remove")
def plugin_remove(
    name: Annotated[str, typer.Argument(help="PyPI distribution name to uninstall")],
) -> None:
    """Uninstall an Aglet plugin distribution."""
    cmd = [*_pip_command(), "uninstall", "-y", name] if "uv" in _pip_command()[0] else [
        *_pip_command(),
        "uninstall",
        "-y",
        name,
    ]
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]uninstall failed (exit {exc.returncode}).[/]")
        raise typer.Exit(code=exc.returncode) from exc
    console.print(f"[green]Uninstalled[/] {name}.")


# ---------- marketplace ----------------------------------------------------------------------


marketplace_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Discover and install curated Aglet plugins.",
)
app.add_typer(marketplace_app, name="marketplace")

DEFAULT_MARKETPLACE_URL = (
    "https://raw.githubusercontent.com/zyssyz123/agentkit/main/docs/marketplace.json"
)


def _fetch_marketplace(url: str) -> dict:
    """Fetch the marketplace JSON via stdlib so we don't take a hard dep on a
    particular httpx version."""
    import json
    from urllib.request import Request, urlopen

    req = Request(url, headers={"User-Agent": "aglet-cli"})
    with urlopen(req, timeout=15.0) as r:  # noqa: S310 — URL is user-provided or our default
        return json.loads(r.read().decode())


@marketplace_app.command("list")
def marketplace_list(
    url: Annotated[
        str, typer.Option("--url", help="Marketplace index URL")
    ] = DEFAULT_MARKETPLACE_URL,
) -> None:
    """Pretty-print every plugin in the marketplace index."""
    try:
        data = _fetch_marketplace(url)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not fetch marketplace:[/] {exc}")
        raise typer.Exit(code=1) from exc
    plugins = data.get("plugins", [])
    table = Table(title=f"Aglet marketplace — {len(plugins)} plugins")
    table.add_column("Package")
    table.add_column("Element", style="cyan")
    table.add_column("Kind")
    table.add_column("Version")
    table.add_column("Description", overflow="fold")
    for p in sorted(plugins, key=lambda x: (x.get("element") or "~", x.get("name", ""))):
        table.add_row(
            p["name"],
            p.get("element") or "[dim]—[/]",
            p.get("kind", "?"),
            p.get("version", "?"),
            p.get("description", ""),
        )
    console.print(table)


@marketplace_app.command("search")
def marketplace_search(
    query: Annotated[str, typer.Argument(help="Substring or keyword to filter by")],
    element: Annotated[
        Optional[str], typer.Option("--element", "-e", help="Filter by Element kind")
    ] = None,
    url: Annotated[str, typer.Option("--url")] = DEFAULT_MARKETPLACE_URL,
) -> None:
    """Search the marketplace index by package name, description, or keyword."""
    try:
        data = _fetch_marketplace(url)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not fetch marketplace:[/] {exc}")
        raise typer.Exit(code=1) from exc

    q = query.lower()
    hits = []
    for p in data.get("plugins", []):
        if element and p.get("element") != element:
            continue
        haystack = " ".join(
            [
                p.get("name", ""),
                p.get("description", ""),
                p.get("element") or "",
                p.get("technique") or "",
                " ".join(p.get("keywords", [])),
            ]
        ).lower()
        if q in haystack:
            hits.append(p)

    if not hits:
        console.print(f"[yellow]No results for {query!r}.[/]")
        return

    table = Table(title=f"Search results for {query!r}")
    table.add_column("Package")
    table.add_column("Element", style="cyan")
    table.add_column("Description", overflow="fold")
    for p in hits:
        table.add_row(p["name"], p.get("element") or "—", p.get("description", ""))
    console.print(table)
    console.print(
        f"\n[dim]Install with[/] [bold]aglet marketplace install <package>[/]"
    )


@marketplace_app.command("install")
def marketplace_install(
    name: Annotated[str, typer.Argument(help="Package name from the marketplace")],
    url: Annotated[str, typer.Option("--url")] = DEFAULT_MARKETPLACE_URL,
) -> None:
    """Install a marketplace plugin (shells out to `pip install --pre`)."""
    try:
        data = _fetch_marketplace(url)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not fetch marketplace:[/] {exc}")
        raise typer.Exit(code=1) from exc

    names = {p["name"]: p for p in data.get("plugins", [])}
    if name not in names:
        console.print(
            f"[red]Package {name!r} is not in the marketplace index.[/] "
            f"To install any PyPI package anyway, use [bold]aglet plugin install {name}[/]."
        )
        raise typer.Exit(code=1)

    cmd = [*_pip_command(), "install", "--pre", name]
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]install failed (exit {exc.returncode}).[/]")
        raise typer.Exit(code=exc.returncode) from exc

    registry = get_registry()
    before = set(registry.technique_factories)
    registry.discover_entry_points()
    new = sorted(set(registry.technique_factories) - before)
    if new:
        console.print(f"\n[green]Installed[/] [bold]{name}[/]. New techniques:")
        for n in new:
            console.print(f"  - {n}")
    else:
        console.print(f"\n[green]Installed[/] [bold]{name}[/].")


if __name__ == "__main__":
    app()
