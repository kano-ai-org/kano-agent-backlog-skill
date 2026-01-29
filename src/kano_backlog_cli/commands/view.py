from __future__ import annotations
from typing import Optional, Union
from pathlib import Path

import typer

from ..util import ensure_core_on_path

app = typer.Typer()


@app.command()
def refresh(
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    backlog_root: str = typer.Option("_kano/backlog", "--backlog-root", help="Backlog root directory"),
    product: Optional[str] = typer.Option(None, "--product", help="Product name (optional)"),
    config: Optional[str] = typer.Option(None, "--config", help="Config file path"),
):
    """Refresh all dashboards (views) in the backlog."""
    try:
        ensure_core_on_path()
        from kano_backlog_core.config import ConfigLoader
        from kano_backlog_ops.view import refresh_dashboards as ops_refresh
        from .config_cmd import _default_auto_export_path, _write_effective_config_artifact
        
        backlog_path = Path(backlog_root)
        if not backlog_path.exists():
            typer.echo(f"❌ Backlog root not found: {backlog_path}", err=True)
            raise typer.Exit(1)
        
        # Call ops layer
        typer.echo("Refreshing views...")

        # Best-effort: write effective config artifact for downstream tooling.
        # This should not block view refresh.
        try:
            ctx, effective = ConfigLoader.load_effective_config(
                backlog_path,
                product=product,
                agent=agent,
            )
            out_path = _default_auto_export_path(ctx, "toml", topic=None, workset_item_id=None)
            _write_effective_config_artifact(
                ctx=ctx,
                effective=effective,
                fmt="toml",
                out_path=out_path,
                overwrite=True,
            )
            typer.echo(f"✓ Wrote effective config: {out_path}")
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

