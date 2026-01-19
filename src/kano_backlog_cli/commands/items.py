from __future__ import annotations

from pathlib import Path
import json
import typer

from kano_backlog_cli.util import ensure_core_on_path

app = typer.Typer(help="Item maintenance helpers")


@app.command("trash")
def trash(
    item_ref: str = typer.Argument(..., help="Item ID, UID, or path to trash"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    agent: str = typer.Option(..., "--agent", help="Agent name for audit/worklog"),
    model: str | None = typer.Option(None, "--model", help="Model used by agent"),
    reason: str | None = typer.Option(None, "--reason", help="Reason for trashing"),
    apply: bool = typer.Option(False, "--apply", help="Write changes to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Move an item file to a per-product _trash folder."""
    ensure_core_on_path()
    from kano_backlog_ops.workitem import trash_item

    result = trash_item(
        item_ref,
        agent=agent,
        reason=reason,
        model=model,
        product=product,
        backlog_root=backlog_root,
        apply=apply,
    )

    if output_format == "json":
        payload = {
            "item_ref": result.item_ref,
            "status": result.status,
            "source_path": str(result.source_path),
            "trashed_path": str(result.trashed_path),
            "reason": result.reason,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Trash item: {result.item_ref}")
    typer.echo(f"- status: {result.status}")
    typer.echo(f"- source_path: {result.source_path}")
    typer.echo(f"- trashed_path: {result.trashed_path}")
    if result.reason:
        typer.echo(f"- reason: {result.reason}")


@app.command("set-parent")
def set_parent(
    item_ref: str = typer.Argument(..., help="Item ID, UID, or path to update"),
    parent: str | None = typer.Option(None, "--parent", help="Parent item ID"),
    clear: bool = typer.Option(False, "--clear", help="Clear parent reference"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    agent: str = typer.Option(..., "--agent", help="Agent name for audit/worklog"),
    model: str | None = typer.Option(None, "--model", help="Model used by agent"),
    apply: bool = typer.Option(False, "--apply", help="Write changes to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Update a work item's parent field."""
    ensure_core_on_path()
    from kano_backlog_ops.workitem import update_parent

    if clear and parent:
        raise typer.BadParameter("Use --clear or --parent, not both.")
    if not clear and not parent:
        raise typer.BadParameter("Provide --parent or --clear.")

    result = update_parent(
        item_ref,
        parent=None if clear else parent,
        agent=agent,
        model=model,
        product=product,
        backlog_root=backlog_root,
        apply=apply,
    )

    if output_format == "json":
        payload = {
            "item_ref": result.item_ref,
            "status": result.status,
            "path": str(result.path),
            "old_parent": result.old_parent,
            "new_parent": result.new_parent,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Set parent: {result.item_ref}")
    typer.echo(f"- status: {result.status}")
    typer.echo(f"- path: {result.path}")
    typer.echo(f"- old_parent: {result.old_parent}")
    typer.echo(f"- new_parent: {result.new_parent}")
