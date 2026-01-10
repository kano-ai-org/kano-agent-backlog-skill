from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from ..util import ensure_core_on_path, resolve_product_root

app = typer.Typer()


@app.command()
def refresh(
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    backlog_root: str = typer.Option("_kano/backlog", "--backlog-root", help="Backlog root directory"),
    product: str | None = typer.Option(None, "--product", help="Product name (optional)"),
    config: str | None = typer.Option(None, "--config", help="Config file path"),
):
    """Refresh all dashboards (views) in the backlog."""
    try:
        # Import ops layer
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # Add src/ to path
        from kano_backlog_ops.view import refresh_dashboards as ops_refresh
        
        backlog_path = Path(backlog_root)
        if not backlog_path.exists():
            typer.echo(f"❌ Backlog root not found: {backlog_path}", err=True)
            raise typer.Exit(1)
        
        # Call ops layer
        typer.echo("Refreshing views...")
        config_path = Path(config) if config else None
        result = ops_refresh(
            product=product,
            agent=agent,
            backlog_root=backlog_path,
            config_path=config_path,
        )
        
        # Report results
        typer.echo(f"✓ Refreshed {len(result.views_refreshed)} dashboards")
        if result.summaries_refreshed:
            typer.echo(f"  + {len(result.summaries_refreshed)} summaries")
        if result.reports_refreshed:
            typer.echo(f"  + {len(result.reports_refreshed)} reports")
        
    except RuntimeError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(2)

