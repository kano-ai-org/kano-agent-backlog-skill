from __future__ import annotations

import json
from pathlib import Path
import typer

from ..util import ensure_core_on_path, resolve_product_root, find_item_path_by_id

app = typer.Typer()


@app.command()
def transition(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    action: str = typer.Option(..., help="propose|ready|start|review|done|block|drop"),
    agent: str = typer.Option("cli", help="Agent name for audit/worklog"),
    message: str = typer.Option("", help="Optional worklog message"),
    product: str | None = typer.Option(None, help="Product name under _kano/backlog/products"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Transition item state and persist to canonical store."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore
    from kano_backlog_core.state import StateMachine
    from kano_backlog_core.models import StateAction
    from kano_backlog_core.errors import ItemNotFoundError, ValidationError

    product_root = resolve_product_root(product)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)

    try:
        act = StateAction(action)
    except Exception:
        raise typer.Exit(code=1)

    try:
        updated = StateMachine.transition(item, act, agent=agent, message=message or None)
        store.write(updated)
    except ValidationError as e:
        typer.echo(f"Error: Validation failed: {'; '.join(e.errors)}", err=True)
        raise typer.Exit(code=3)

    if output_format == "json":
        data = updated.model_dump()
        data["file_path"] = str(data.get("file_path"))
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        typer.echo(f"✓ {item_id} transitioned to {updated.state.value}")
