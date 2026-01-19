from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import json

import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="ADR (Architecture Decision Record) operations")

__all__ = ["app"]


@app.command("create")
def create(
    *,
    title: str = typer.Option(..., "--title", help="ADR title"),
    product: str = typer.Option(..., "--product", help="Product name under _kano/backlog/products"),
    agent: str = typer.Option(..., "--agent", help="Agent identifier for audit logging"),
    related_item: List[str] = typer.Option(
        [],
        "--related-item",
        help="Repeatable related backlog item IDs (e.g., KABSD-EPIC-0009)",
    ),
    status: str = typer.Option("Proposed", "--status", help="Initial ADR status"),
    backlog_root: Optional[Path] = typer.Option(
        None,
        "--backlog-root",
        help="Path to _kano/backlog (auto-detected if omitted)",
    ),
) -> None:
    """Create a new ADR in the product decisions folder."""

    ensure_core_on_path()
    from kano_backlog_ops.adr import create_adr as ops_create_adr

    try:
        result = ops_create_adr(
            title=title,
            product=product,
            agent=agent,
            related_items=list(related_item) if related_item else None,
            status=status,
            backlog_root=backlog_root,
        )
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        typer.echo(f"❌ {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:  # pragma: no cover
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    typer.echo(f"✓ Created {result.id}: {result.title}")
    typer.echo(f"  Path: {result.path}")



@app.command("fix-uids")
def fix_uids(
    *,
    product: str | None = typer.Option(None, "--product", help="Product name under _kano/backlog/products"),
    backlog_root: Optional[Path] = typer.Option(
        None,
        "--backlog-root",
        help="Path to _kano/backlog (auto-detected if omitted)",
    ),
    agent: str = typer.Option(..., "--agent", help="Agent identifier for audit logging"),
    model: str | None = typer.Option(None, "--model", help="Model name for audit logging"),
    apply: bool = typer.Option(False, "--apply", help="Apply fixes (dry-run by default)"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
) -> None:
    """Backfill missing/invalid ADR UIDs (UUIDv7)."""
    ensure_core_on_path()
    from kano_backlog_ops.adr import backfill_adr_uids as ops_backfill

    try:
        results = ops_backfill(
            product=product,
            backlog_root=backlog_root,
            agent=agent,
            model=model,
            apply=apply,
        )
    except Exception as exc:  # pragma: no cover
        typer.echo(f"? Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = []
        for res in results:
            payload.append(
                {
                    "product": res.product,
                    "checked": res.checked,
                    "updated": res.updated,
                    "actions": [
                        {
                            "path": str(action.path),
                            "old_uid": action.old_uid,
                            "new_uid": action.new_uid,
                            "status": action.status,
                        }
                        for action in res.actions
                    ],
                }
            )
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    for res in results:
        typer.echo(f"# Product: {res.product}")
        typer.echo(f"- checked: {res.checked}")
        typer.echo(f"- updated: {res.updated}")
        typer.echo(f"- actions: {len(res.actions)}")
