"""Persona summary and reporting commands."""

from __future__ import annotations

from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Persona activity operations")


@app.command()
def summary(
    product: str = typer.Option(..., "--product", help="Product name"),
    agent: str = typer.Option(..., "--agent", help="Agent/persona identifier"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    output: Path | None = typer.Option(None, "--output", help="Override output path"),
):
    """Generate a persona activity summary from worklog entries."""
    ensure_core_on_path()
    from kano_backlog_ops.persona import generate_summary

    try:
        result = generate_summary(
            product=product,
            agent=agent,
            backlog_root=backlog_root,
            output_path=output,
        )
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Generated persona summary: {result.artifact_path.name}")
    typer.echo(f"  Items analyzed: {result.items_analyzed}")
    typer.echo(f"  Worklog entries: {result.worklog_entries}")
    typer.echo(f"  Saved to: {result.artifact_path}")


@app.command()
def report(
    product: str = typer.Option(..., "--product", help="Product name"),
    agent: str = typer.Option(..., "--agent", help="Agent/persona identifier"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    output: Path | None = typer.Option(None, "--output", help="Override output path"),
):
    """Generate a full persona activity report with state breakdown."""
    ensure_core_on_path()
    from kano_backlog_ops.persona import generate_report

    try:
        result = generate_report(
            product=product,
            agent=agent,
            backlog_root=backlog_root,
            output_path=output,
        )
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Generated persona report: {result.artifact_path.name}")
    typer.echo(f"  Total items: {result.total_items}")
    typer.echo(f"  States:")
    for state, count in sorted(result.items_by_state.items()):
        typer.echo(f"    • {state}: {count}")
    typer.echo(f"  Saved to: {result.artifact_path}")
