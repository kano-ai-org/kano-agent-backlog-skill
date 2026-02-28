"""
Workset CLI commands for managing per-item workset caches.

This module provides the `kano-backlog workset` command group for:
- Initializing worksets for backlog items
- Refreshing worksets from canonical files
- Getting next actions from workset plans
- Promoting deliverables to canonical artifacts
- Cleaning up expired worksets
- Listing all worksets
- Detecting ADR candidates in notes

Requirements: 1.1-5.4, 11.2, 12.1-12.4
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Manage per-item workset caches")


@app.command()
def init(
    item: str = typer.Option(..., "--item", help="Item ID, UID, or path"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    ttl_hours: int = typer.Option(72, "--ttl-hours", help="Time-to-live in hours"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Initialize a workset for an item."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import init_workset, ItemNotFoundError, WorksetError

    try:
        result = init_workset(
            item,
            agent=agent,
            ttl_hours=ttl_hours,
        )
    except ItemNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except WorksetError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "workset_path": str(result.workset_path),
            "item_count": result.item_count,
            "created": result.created,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if result.created:
            typer.echo(f"✓ Workset initialized: {result.workset_path}")
        else:
            typer.echo(f"✓ Workset already exists: {result.workset_path}")


@app.command()
def refresh(
    item: str = typer.Option(..., "--item", help="Item ID, UID, or path"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Refresh workset from canonical files."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import (
        refresh_workset,
        WorksetNotFoundError,
        WorksetError,
    )

    try:
        result = refresh_workset(
            item,
            agent=agent,
        )
    except WorksetNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except WorksetError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "workset_path": str(result.workset_path),
            "items_added": result.items_added,
            "items_removed": result.items_removed,
            "items_updated": result.items_updated,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        typer.echo(f"✓ Workset refreshed: {result.workset_path}")
        typer.echo(f"  Updated: {result.items_updated}")


@app.command("next")
def next_action(
    item: str = typer.Option(..., "--item", help="Item ID, UID, or path"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Get next unchecked action from plan."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import (
        get_next_action,
        WorksetNotFoundError,
        WorksetError,
    )

    try:
        result = get_next_action(item)
    except WorksetNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except WorksetError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "step_number": result.step_number,
            "description": result.description,
            "is_complete": result.is_complete,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if result.is_complete:
            typer.echo("✓ All steps complete!")
        else:
            typer.echo(f"Step {result.step_number}: {result.description}")


@app.command()
def promote(
    item: str = typer.Option(..., "--item", help="Item ID, UID, or path"),
    agent: str = typer.Option(..., "--agent", help="Agent identity"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List files without making changes"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Promote deliverables to canonical artifacts."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import (
        promote_deliverables,
        WorksetNotFoundError,
        WorksetError,
    )

    try:
        result = promote_deliverables(
            item,
            agent=agent,
            dry_run=dry_run,
        )
    except WorksetNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except WorksetError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "promoted_files": result.promoted_files,
            "target_path": str(result.target_path) if result.target_path else "",
            "worklog_entry": result.worklog_entry,
            "dry_run": dry_run,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if dry_run:
            typer.echo("Dry run - no changes made")
        
        if not result.promoted_files:
            typer.echo("No deliverables to promote")
        else:
            typer.echo(f"{'Would promote' if dry_run else 'Promoted'} {len(result.promoted_files)} file(s):")
            for f in result.promoted_files:
                typer.echo(f"  - {f}")
            if not dry_run:
                typer.echo(f"Target: {result.target_path}")


@app.command()
def cleanup(
    ttl_hours: int = typer.Option(72, "--ttl-hours", help="Delete worksets older than N hours"),
    agent: Optional[str] = typer.Option(None, "--agent", help="Agent filter (reserved)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List worksets without deleting"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Clean up expired worksets."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import cleanup_worksets, WorksetError

    try:
        result = cleanup_worksets(
            agent=agent,
            ttl_hours=ttl_hours,
            dry_run=dry_run,
        )
    except WorksetError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        payload = {
            "deleted_count": result.deleted_count,
            "deleted_paths": [str(p) for p in result.deleted_paths],
            "space_reclaimed_bytes": result.space_reclaimed_bytes,
            "dry_run": dry_run,
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
    else:
        if dry_run:
            typer.echo("Dry run - no changes made")
        
        if result.deleted_count == 0:
            typer.echo("No expired worksets found")
        else:
            action = "Would delete" if dry_run else "Deleted"
            typer.echo(f"{action} {result.deleted_count} workset(s)")
            
            # Format space reclaimed
            space_kb = result.space_reclaimed_bytes / 1024
            if space_kb < 1024:
                space_str = f"{space_kb:.1f} KB"
            else:
                space_str = f"{space_kb / 1024:.1f} MB"
            typer.echo(f"Space {'would be ' if dry_run else ''}reclaimed: {space_str}")


@app.command("list")
def list_cmd(
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """List all worksets."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import (
        get_workset_cache_root,
        WorksetMetadata,
        _find_backlog_root,
    )
    from datetime import datetime, timezone

    try:
        backlog_root = _find_backlog_root()
        cache_root = get_workset_cache_root(backlog_root)
        items_dir = cache_root / "items"
        
        worksets = []
        if items_dir.exists():
            for workset_dir in items_dir.iterdir():
                if not workset_dir.is_dir():
                    continue
                
                meta_path = workset_dir / "meta.json"
                if not meta_path.exists():
                    continue
                
                try:
                    metadata = WorksetMetadata.load(meta_path)
                    
                    # Calculate age
                    created_at_str = metadata.created_at
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    created_at = datetime.fromisoformat(created_at_str)
                    now = datetime.now(timezone.utc)
                    age = now - created_at
                    age_hours = age.total_seconds() / 3600
                    
                    # Calculate size
                    total_size = 0
                    for file_path in workset_dir.rglob("*"):
                        if file_path.is_file():
                            try:
                                total_size += file_path.stat().st_size
                            except OSError:
                                pass
                    
                    worksets.append({
                        "item_id": metadata.item_id,
                        "agent": metadata.agent,
                        "created_at": metadata.created_at,
                        "refreshed_at": metadata.refreshed_at,
                        "ttl_hours": metadata.ttl_hours,
                        "age_hours": round(age_hours, 1),
                        "size_bytes": total_size,
                        "path": str(workset_dir),
                    })
                except Exception:
                    continue
        
        if output_format == "json":
            typer.echo(json.dumps({"worksets": worksets}, ensure_ascii=False, indent=2))
        else:
            if not worksets:
                typer.echo("No worksets found")
            else:
                typer.echo(f"Found {len(worksets)} workset(s):\n")
                for ws in worksets:
                    size_kb = ws["size_bytes"] / 1024
                    typer.echo(f"  {ws['item_id']}")
                    typer.echo(f"    Agent: {ws['agent']}")
                    typer.echo(f"    Age: {ws['age_hours']:.1f} hours")
                    typer.echo(f"    Size: {size_kb:.1f} KB")
                    typer.echo(f"    TTL: {ws['ttl_hours']} hours")
                    typer.echo("")
    except Exception as exc:
        typer.echo(f"❌ Error listing worksets: {exc}", err=True)
        raise typer.Exit(1)


@app.command("detect-adr")
def detect_adr(
    item: str = typer.Option(..., "--item", help="Item ID, UID, or path"),
    output_format: str = typer.Option("plain", "--format", help="Output format: plain|json"),
):
    """Detect ADR candidates in notes."""
    ensure_core_on_path()
    from kano_backlog_ops.workset import (
        detect_adr_candidates,
        WorksetNotFoundError,
        WorksetError,
    )

    try:
        candidates = detect_adr_candidates(item)
    except WorksetNotFoundError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except WorksetError as exc:
        typer.echo(f"❌ {exc.message}", err=True)
        if exc.suggestion:
            typer.echo(f"   Suggestion: {exc.suggestion}", err=True)
        raise typer.Exit(1)
    except NotImplementedError:
        typer.echo("❌ detect_adr_candidates not yet implemented", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"❌ Unexpected error: {exc}", err=True)
        raise typer.Exit(2)

    if output_format == "json":
        typer.echo(json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2))
    else:
        if not candidates:
            typer.echo("No ADR candidates found in notes")
        else:
            typer.echo(f"Found {len(candidates)} ADR candidate(s):\n")
            for i, candidate in enumerate(candidates, 1):
                typer.echo(f"  {i}. {candidate.get('suggested_title', 'Untitled')}")
                typer.echo(f"     Text: {candidate.get('text', '')[:80]}...")
                typer.echo("")
