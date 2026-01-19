from __future__ import annotations

import json
from pathlib import Path
import typer

from ..util import ensure_core_on_path, resolve_product_root, find_item_path_by_id, resolve_model

app = typer.Typer()


@app.command()
def append(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    message: str = typer.Option(..., help="Worklog message to append"),
    agent: str = typer.Option("cli", help="Agent name for audit/worklog"),
    model: str | None = typer.Option(None, help="Model used by agent (e.g., claude-sonnet-4.5, gpt-5.1)"),
    product: str | None = typer.Option(None, help="Product name under _kano/backlog/products"),
    backlog_root_override: Path | None = typer.Option(
        None,
        "--backlog-root-override",
        help="Backlog root override (e.g., _kano/backlog_sandbox/<name>)",
    ),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Append a worklog entry to an item and persist."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore
    from kano_backlog_core.audit import AuditLog

    product_root = resolve_product_root(product, backlog_root_override=backlog_root_override)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)

    resolved_model, _ = resolve_model(model)

    AuditLog.append_worklog(item, message, agent=agent, model=resolved_model)
    store.write(item)

    if output_format == "json":
        data = item.model_dump()
        data["file_path"] = str(data.get("file_path"))
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        typer.echo(f"OK: Appended worklog to {item_id}")
