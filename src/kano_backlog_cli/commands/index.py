from __future__ import annotations

from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="SQLite index operations")


@app.command()
def build(
    product: str | None = typer.Option(None, "--product", help="Product name (builds all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    force: bool = typer.Option(False, "--force/--no-force", help="Rebuild even if index exists"),
):
    """Build the SQLite index from markdown items."""
    ensure_core_on_path()
    from kano_backlog_ops.index import build_index

    try:
        result = build_index(product=product, backlog_root=backlog_root, force=force)
    except FileExistsError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Built index: {result.index_path}")
    typer.echo(f"  Items: {result.items_indexed}")
    if result.links_indexed:
        typer.echo(f"  Links: {result.links_indexed}")
    typer.echo(f"  Time: {result.build_time_ms:.1f} ms")


@app.command()
def refresh(
    product: str | None = typer.Option(None, "--product", help="Product name (refresh all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
):
    """Refresh the SQLite index (MVP: full rebuild)."""
    ensure_core_on_path()
    from kano_backlog_ops.index import refresh_index

    try:
        result = refresh_index(product=product, backlog_root=backlog_root)
    except FileNotFoundError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:  # pragma: no cover - defensive
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Refreshed index: {result.index_path}")
    typer.echo(f"  Items added: {result.items_added}")
    if result.items_updated or result.items_removed:
        typer.echo(f"  Updated: {result.items_updated}, Removed: {result.items_removed}")
    typer.echo(f"  Time: {result.refresh_time_ms:.1f} ms")
