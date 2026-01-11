from __future__ import annotations

import json
from typing import List

import typer

from ..util import ensure_core_on_path, resolve_product_root, find_item_path_by_id

app = typer.Typer()


def _parse_tags(raw: str) -> List[str]:
    """Normalize a comma-separated tag list."""
    return [tag.strip() for tag in raw.split(",") if tag.strip()] if raw else []


@app.command()
def read(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    product: str | None = typer.Option(None, help="Product name under _kano/backlog/products"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Read a backlog item from the canonical store."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore

    product_root = resolve_product_root(product)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)

    if output_format == "json":
        data = item.model_dump()
        data["file_path"] = str(data.get("file_path"))
        typer.echo(json.dumps(data, ensure_ascii=False))
    else:
        typer.echo(f"ID: {item.id}\nTitle: {item.title}\nState: {item.state.value}\nOwner: {item.owner}")


@app.command()
def validate(
    item_id: str = typer.Argument(..., help="Display ID, e.g., KABSD-TSK-0001"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Validate a work item against the Ready gate."""
    ensure_core_on_path()
    from kano_backlog_core.canonical import CanonicalStore

    product_root = resolve_product_root(product)
    store = CanonicalStore(product_root)
    item_path = find_item_path_by_id(store.items_root, item_id)
    item = store.read(item_path)

    ready_fields = ["context", "goal", "approach", "acceptance_criteria", "risks"]
    gaps = [field for field in ready_fields if not getattr(item, field, None)]
    is_ready = len(gaps) == 0

    if output_format == "json":
        result = {"id": item.id, "is_ready": is_ready, "gaps": gaps}
        typer.echo(json.dumps(result, ensure_ascii=False))
    else:
        if is_ready:
            typer.echo(f"✓ {item.id} is READY")
        else:
            typer.echo(f"❌ {item.id} is NOT READY")
            typer.echo("Missing fields:")
            for field in gaps:
                typer.echo(f"  - {field}")


def _run_create_command(
    *,
    item_type: str,
    title: str,
    parent: str | None,
    priority: str,
    area: str,
    iteration: str | None,
    tags: str,
    agent: str,
    product: str | None,
    output_format: str,
) -> None:
    """Invoke the ops-layer create implementation and handle formatting."""
    ensure_core_on_path()
    from kano_backlog_core.models import ItemType
    from kano_backlog_ops.workitem import create_item as ops_create_item

    type_map = {
        "epic": ItemType.EPIC,
        "feature": ItemType.FEATURE,
        "userstory": ItemType.USER_STORY,
        "task": ItemType.TASK,
        "bug": ItemType.BUG,
    }

    type_key = item_type.strip().lower()
    if type_key not in type_map:
        typer.echo("❌ Invalid item type. Use: epic|feature|userstory|task|bug", err=True)
        raise typer.Exit(1)

    tag_list = _parse_tags(tags)

    try:
        result = ops_create_item(
            item_type=type_map[type_key],
            title=title,
            product=product,
            agent=agent,
            parent=parent,
            priority=priority,
            area=area,
            iteration=iteration,
            tags=tag_list,
        )
    except FileNotFoundError as exc:
        typer.echo(f"❌ {exc}", err=True)
        raise typer.Exit(1)
    except ValueError as exc:
        typer.echo(f"❌ {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "id": result.id,
            "uid": result.uid,
            "path": str(result.path),
            "type": result.type.value,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Created: {result.id}")
        typer.echo(f"  Path: {result.path.name}")
        typer.echo(f"  Type: {result.type.value}")


@app.command()
def create(
    item_type: str = typer.Option(..., "--type", help="epic|feature|userstory|task|bug"),
    title: str = typer.Option(..., "--title", help="Work item title"),
    parent: str | None = typer.Option(None, "--parent", help="Parent item ID (optional)"),
    priority: str = typer.Option("P2", "--priority", help="Priority (P0-P4, default: P2)"),
    area: str = typer.Option("general", "--area", help="Area tag"),
    iteration: str | None = typer.Option(None, "--iteration", help="Iteration name"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Create a new backlog work item (ops-backed implementation)."""
    _run_create_command(
        item_type=item_type,
        title=title,
        parent=parent,
        priority=priority,
        area=area,
        iteration=iteration,
        tags=tags,
        agent=agent,
        product=product,
        output_format=output_format,
    )


@app.command(name="create-v2")
def create_v2(
    item_type: str = typer.Option(..., "--type", help="epic|feature|userstory|task|bug"),
    title: str = typer.Option(..., "--title", help="Work item title"),
    parent: str | None = typer.Option(None, "--parent", help="Parent item ID (optional)"),
    priority: str = typer.Option("P2", "--priority", help="Priority (P0-P4, default: P2)"),
    area: str = typer.Option("general", "--area", help="Area tag"),
    iteration: str | None = typer.Option(None, "--iteration", help="Iteration name"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Compatibility alias for the ops-backed create command."""
    _run_create_command(
        item_type=item_type,
        title=title,
        parent=parent,
        priority=priority,
        area=area,
        iteration=iteration,
        tags=tags,
        agent=agent,
        product=product,
        output_format=output_format,
    )


@app.command(name="update-state")
def update_state_command(
    item_ref: str = typer.Argument(..., help="Item ID, UID, or path"),
    state: str = typer.Option(..., "--state", help="Target state (New|Proposed|Ready|InProgress|Review|Done|Blocked|Dropped)"),
    agent: str = typer.Option(..., "--agent", help="Agent name (for audit trail)"),
    message: str = typer.Option("", "--message", help="Worklog message"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    sync_parent: bool = typer.Option(True, "--sync-parent/--no-sync-parent", help="Sync parent state forward"),
    refresh_dashboards: bool = typer.Option(True, "--refresh/--no-refresh", help="Refresh dashboards after update"),
    output_format: str = typer.Option("plain", "--format", help="plain|json"),
):
    """Update work item state via the ops layer."""
    ensure_core_on_path()
    from kano_backlog_core.models import ItemState
    from kano_backlog_ops.workitem import update_state as ops_update_state

    try:
        item_state = ItemState(state.upper() if state.lower() == "new" else state.title())
    except ValueError:
        typer.echo(
            "❌ Invalid state. Use: New, Proposed, Ready, InProgress, Review, Done, Blocked, Dropped",
            err=True,
        )
        raise typer.Exit(1)

    try:
        result = ops_update_state(
            item_ref=item_ref,
            new_state=item_state,
            agent=agent,
            message=message or None,
            product=product,
            sync_parent=sync_parent,
            refresh_dashboards=refresh_dashboards,
        )
    except RuntimeError as exc:
        typer.echo(f"❌ {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "id": result.id,
            "old_state": result.old_state.value,
            "new_state": result.new_state.value,
            "worklog_appended": result.worklog_appended,
            "parent_synced": result.parent_synced,
            "dashboards_refreshed": result.dashboards_refreshed,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Updated {result.id}: {result.old_state.value} → {result.new_state.value}")
        if result.worklog_appended and message:
            typer.echo(f"  Worklog: {message}")
        if result.parent_synced:
            typer.echo("  Parent state synced")
        if result.dashboards_refreshed:
            typer.echo("  Dashboards refreshed")