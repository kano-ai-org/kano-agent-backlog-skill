"""Sandbox initialization commands."""
from __future__ import annotations
from typing import Optional, Union

from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Sandbox operations")


@app.command()
def init(
    name: str = typer.Argument(..., help="Sandbox name (e.g., 'test-v2', 'experiment-1')"),
    product: str = typer.Option(..., "--product", help="Source product to mirror"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    force: bool = typer.Option(False, "--force/--no-force", help="Recreate sandbox if it exists"),
):
    """Initialize a sandbox environment for safe experimentation."""
    ensure_core_on_path()
    from kano_backlog_ops.sandbox import init_sandbox

    try:
        result = init_sandbox(
            name=name,
            product=product,
            agent=agent,
            backlog_root=backlog_root,
            force=force,
        )
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except FileExistsError as e:
        typer.echo(f"❌ {e}", err=True)
        typer.echo("💡 Use --force to recreate the sandbox.", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Initialized sandbox: {result.sandbox_root.name}")
    typer.echo(f"  Location: {result.sandbox_root}")
    typer.echo(f"  Created {len(result.created_paths)} directories/files")
    typer.echo(f"\n💡 Use this sandbox with: --product {name}")
