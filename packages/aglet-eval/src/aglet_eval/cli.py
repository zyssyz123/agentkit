"""``aglet-eval`` CLI: run a suite.yaml and print a pretty report."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from aglet_eval.harness import EvalReport, load_suite, run_suite_sync

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Run a declarative Aglet eval suite.",
)
console = Console()


@app.command()
def run(
    suite_path: Annotated[Path, typer.Argument(help="Path to suite.yaml")],
    junit: Annotated[
        Path | None,
        typer.Option("--junit", help="Write a JUnit XML report to this path"),
    ] = None,
    fail_under: Annotated[
        float, typer.Option("--fail-under", help="Exit non-zero if pass rate < this")
    ] = 0.0,
) -> None:
    """Execute every case in the suite and report results."""
    if not suite_path.exists():
        console.print(f"[red]suite not found:[/] {suite_path}")
        raise typer.Exit(code=1)
    suite = load_suite(suite_path)
    console.print(
        f"[bold]Running[/] {len(suite.cases)} case(s) against [cyan]{suite.agent_path}[/]"
    )
    report = run_suite_sync(suite)
    _print_report(report)

    if junit:
        junit.parent.mkdir(parents=True, exist_ok=True)
        junit.write_text(_to_junit(report), encoding="utf-8")
        console.print(f"\n[dim]Wrote JUnit XML to {junit}[/]")

    if report.pass_rate < fail_under:
        console.print(
            f"[red]Pass rate {report.pass_rate*100:.1f}% < threshold {fail_under*100:.1f}%[/]"
        )
        raise typer.Exit(code=2)


def _print_report(report: EvalReport) -> None:
    table = Table(title="Aglet eval results")
    table.add_column("Case")
    table.add_column("Outcome")
    table.add_column("Latency (s)")
    table.add_column("Tool calls")
    table.add_column("Steps")
    table.add_column("Failures", overflow="fold")
    for r in report.results:
        outcome = "[green]PASS[/]" if r.passed else "[red]FAIL[/]"
        table.add_row(
            r.case.name,
            outcome,
            f"{r.latency_seconds:.2f}",
            str(r.tool_calls),
            str(r.used_steps),
            "\n".join(r.failures) if r.failures else "—",
        )
    console.print(table)
    console.print(
        f"\n[bold]Summary[/]: {report.passed}/{report.total} passed "
        f"({report.pass_rate*100:.1f}%) — p95 latency {report.p95_latency:.2f}s, "
        f"total cost ${report.total_cost_usd:.4f}"
    )


def _to_junit(report: EvalReport) -> str:
    from xml.sax.saxutils import escape

    cases_xml: list[str] = []
    for r in report.results:
        if r.passed:
            cases_xml.append(
                f'    <testcase classname="aglet-eval" name="{escape(r.case.name)}" '
                f'time="{r.latency_seconds:.2f}" />'
            )
        else:
            failure_msg = escape(" | ".join(r.failures))
            cases_xml.append(
                f'    <testcase classname="aglet-eval" name="{escape(r.case.name)}" '
                f'time="{r.latency_seconds:.2f}">\n'
                f'      <failure message="{failure_msg}" />\n'
                f"    </testcase>"
            )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<testsuite name="aglet-eval" tests="{report.total}" '
        f'failures="{report.total - report.passed}">\n'
        + "\n".join(cases_xml)
        + "\n</testsuite>\n"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
