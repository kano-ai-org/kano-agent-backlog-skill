from __future__ import annotations
from typing import Optional, Union
from pathlib import Path

import typer

from ..util import ensure_core_on_path

app = typer.Typer()


@app.command()
def refresh(
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    backlog_root: Optional[str] = typer.Option(None, "--backlog-root", help="Parent backlog directory (optional, resolved from config if not provided)"),
    product: Optional[str] = typer.Option(None, "--product", help="Product name (optional)"),
    config: Optional[str] = typer.Option(None, "--config", help="Config file path"),
):
    """Refresh all dashboards (views) in the backlog."""
    try:
        ensure_core_on_path()
        from kano_backlog_core.config import ConfigLoader
        from kano_backlog_ops.view import refresh_dashboards as ops_refresh
        
        # Load config to get context and effective config
        # If backlog_root is not provided, resolve it from config
        if backlog_root is None:
            try:
                ctx, effective = ConfigLoader.load_effective_config(
                    Path.cwd(),
                    product=product,
                    agent=agent,
                )
                # ctx.backlog_root points to the product-specific directory
                # e.g., _kano/backlog/products/kano-opencode-quickstart
                # But ops layer expects the parent directory (e.g., _kano/backlog)
                # So we need to extract the parent backlog directory
                product_backlog_path = ctx.backlog_root
                
                # Check if the path ends with products/{product_name}
                if product_backlog_path.parent.name == "products":
                    parent_backlog_path = product_backlog_path.parent.parent
                    typer.echo(f"Resolved parent backlog from config: {parent_backlog_path}")
                else:
                    # Fallback: use the backlog root as-is (old structure)
                    parent_backlog_path = product_backlog_path
                    typer.echo(f"Using backlog root from config: {parent_backlog_path}")
                
                backlog_path = parent_backlog_path
            except Exception as e:
                typer.echo(f"❌ Could not resolve backlog root from config: {e}", err=True)
                typer.echo("Hint: Provide --backlog-root explicitly or ensure .kano/backlog_config.toml exists", err=True)
                raise typer.Exit(1)
        else:
            backlog_path = Path(backlog_root)
            # Load config with the provided backlog root
            try:
                ctx, effective = ConfigLoader.load_effective_config(
                    backlog_path,
                    product=product,
                    agent=agent,
                )
            except Exception as e:
                typer.echo(f"❌ Could not load config: {e}", err=True)
                raise typer.Exit(1)
        
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

