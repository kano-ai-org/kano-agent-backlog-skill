"""Demo data seeding commands."""
from __future__ import annotations
from typing import Optional, Union

from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Demo data operations")


@app.command()
def seed(
    product: str = typer.Option(..., "--product", help="Product name to seed"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    count: int = typer.Option(5, "--count", help="Number of demo items to create (default: 5)"),
    force: bool = typer.Option(False, "--force/--no-force", help="Recreate demo items if they exist"),
):
    """Seed a product with reproducible demo items for testing."""
    ensure_core_on_path()
    from kano_backlog_ops.demo import seed_demo

    try:
        result = seed_demo(
            product=product,
            agent=agent,
            backlog_root=backlog_root,
            count=count,
            force=force,
        )
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except FileExistsError as e:
        typer.echo(f"❌ {e}", err=True)
        typer.echo("💡 Use --force to recreate demo items.", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Seeded demo data in {result.product_root.name}")
    typer.echo(f"  Created {len(result.items_created)} items:")
    for item_result in result.items_created:
        typer.echo(f"    • {item_result.id} ({item_result.type.value}): {item_result.path.name}")
    if result.skipped:
        typer.echo(f"  Cleaned up {result.skipped} existing demo items")
