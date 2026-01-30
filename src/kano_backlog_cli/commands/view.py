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
        from .config_cmd import _default_auto_export_path, _write_effective_config_artifact
        
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

        # Best-effort: write effective config artifact for downstream tooling.
        # This should not block view refresh.
        # Only write in debug mode (when log.debug is enabled in config)
        try:
            # Check if debug mode is enabled
            # Check both nested and flat key formats for compatibility
            debug_enabled = (
                effective.get("log", {}).get("debug", False) or 
                effective.get("log.debug", False)
            )
            
            if debug_enabled:
                out_path = _default_auto_export_path(ctx, "toml", topic=None, workset_item_id=None)
                _write_effective_config_artifact(
                    ctx=ctx,
                    effective=effective,
                    fmt="toml",
                    out_path=out_path,
                    overwrite=True,
                )
                typer.echo(f"✓ Wrote effective config (debug mode): {out_path}")
            else:
                typer.echo("ℹ️  Skipped effective config export (debug mode disabled)")
        except Exception as e:
            typer.echo(f"⚠️  Could not write effective config artifact: {e}", err=True)

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

