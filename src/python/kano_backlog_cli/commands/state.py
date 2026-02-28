from __future__ import annotations
from typing import Optional, Union
import json
from pathlib import Path
import typer

from ..util import ensure_core_on_path, resolve_product_root, find_item_path_by_id, resolve_model

app = typer.Typer()


@app.command()
def transition(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    action: str = typer.Option(..., help="propose|ready|start|review|done|block|drop"),
    agent: str = typer.Option("cli", help="Agent name for audit/worklog"),
    message: str = typer.Option("", help="Optional worklog message"),
    model: Optional[str] = typer.Option(None, help="Model used by agent (e.g., claude-sonnet-4.5, gpt-5.1)"),
    product: Optional[str] = typer.Option(None, help="Product name under _kano/backlog/products"),
    backlog_root_override: Optional[Path] = typer.Option(
        None,
        "--backlog-root-override",
        help="Backlog root override (e.g., _kano/backlog_sandbox/<name>)",
    ),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Transition item state and persist to canonical store."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore
    from kano_backlog_core.state import StateMachine
    from kano_backlog_core.models import StateAction
    from kano_backlog_core.errors import ItemNotFoundError, ValidationError

    product_root = resolve_product_root(product, backlog_root_override=backlog_root_override)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)

    try:
        act = StateAction(action)
    except Exception:
        raise typer.Exit(code=1)

    try:
        resolved_model, _ = resolve_model(model)
        updated = StateMachine.transition(item, act, agent=agent, message=message or None, model=resolved_model)
        store.write(updated)
    except ValidationError as e:
        typer.echo(f"Error: Validation failed: {'; '.join(e.errors)}", err=True)
        raise typer.Exit(code=3)

    if output_format == "json":
        data = updated.model_dump()
        data["file_path"] = str(data.get("file_path"))
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        typer.echo(f"OK: {item_id} transitioned to {updated.state.value}")
