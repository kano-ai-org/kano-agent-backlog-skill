from __future__ import annotations

import json
from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Link maintenance helpers")


@app.command("fix")
def fix_links(
    product: str | None = typer.Option(None, "--product", help="Product name (fix all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    include_views: bool = typer.Option(False, "--include-views", help="Scan views/ markdown (derived output)"),
    ignore_target: list[str] | None = typer.Option(
        None,
        "--ignore-target",
        help="Glob pattern for targets to ignore (repeatable)",
    ),
    remap_root: list[str] | None = typer.Option(
        None,
        "--remap-root",
        help="Root remap rule '<from>=<to>' (repeatable)",
    ),
    resolve_id: bool = typer.Option(
        False,
        "--resolve-id",
        help="Resolve ID-only targets to concrete files when possible",
    ),
    apply: bool = typer.Option(False, "--apply", help="Apply changes to files"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Fix markdown links and wikilinks using remap/resolve strategies."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import fix_links as fix_links_op

    ignore_target = ignore_target or []
    remap_rules: list[tuple[str, str]] = []
    for raw in remap_root or []:
        if "=" not in raw:
            raise typer.BadParameter("remap-root must be '<from>=<to>'")
        from_root, to_root = raw.split("=", 1)
        from_root = from_root.strip()
        to_root = to_root.strip()
        if not from_root or not to_root:
            raise typer.BadParameter("remap-root must include both <from> and <to>")
        remap_rules.append((from_root, to_root))

    results = fix_links_op(
        product=product,
        backlog_root=backlog_root,
        include_views=include_views,
        ignore_targets=ignore_target,
        remap_roots=remap_rules,
        resolve_ids=resolve_id,
        apply=apply,
    )

    if output_format == "json":
        payload = []
        for res in results:
            payload.append(
                {
                    "product": res.product,
                    "checked_files": res.checked_files,
                    "updated_files": res.updated_files,
                    "changes": [
                        {
                            "source_path": str(change.source_path),
                            "line": change.line,
                            "column": change.column,
                            "link_type": change.link_type,
                            "original": change.original,
                            "updated": change.updated,
                            "reason": change.reason,
                        }
                        for change in res.changes
                    ],
                }
            )
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    for res in results:
        typer.echo(f"# Product: {res.product}")
        typer.echo(f"- checked_files: {res.checked_files}")
        typer.echo(f"- updated_files: {res.updated_files}")
        typer.echo(f"- changes: {len(res.changes)}")
        if res.changes:
            for change in res.changes:
                typer.echo(
                    f"  - {change.source_path}:{change.line}:{change.column} "
                    f"[{change.link_type}] {change.original} -> {change.updated} ({change.reason})"
                )
        else:
            typer.echo("  - OK: no changes needed")
        typer.echo("")


@app.command("restore-from-vcs")
def restore_from_vcs(
    product: str | None = typer.Option(None, "--product", help="Product name (restore all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    include_views: bool = typer.Option(False, "--include-views", help="Scan views/ markdown (derived output)"),
    ignore_target: list[str] | None = typer.Option(
        None,
        "--ignore-target",
        help="Glob pattern for targets to ignore (repeatable)",
    ),
    remap_root: list[str] | None = typer.Option(
        None,
        "--remap-root",
        help="Root remap rule '<from>=<to>' (repeatable)",
    ),
    apply: bool = typer.Option(False, "--apply", help="Write restored files to working tree"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Restore missing link targets from VCS history when possible."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import restore_links_from_vcs

    ignore_target = ignore_target or []
    remap_rules: list[tuple[str, str]] = []
    for raw in remap_root or []:
        if "=" not in raw:
            raise typer.BadParameter("remap-root must be '<from>=<to>'")
        from_root, to_root = raw.split("=", 1)
        from_root = from_root.strip()
        to_root = to_root.strip()
        if not from_root or not to_root:
            raise typer.BadParameter("remap-root must include both <from> and <to>")
        remap_rules.append((from_root, to_root))

    results = restore_links_from_vcs(
        product=product,
        backlog_root=backlog_root,
        include_views=include_views,
        ignore_targets=ignore_target,
        remap_roots=remap_rules,
        apply=apply,
    )

    if output_format == "json":
        payload = []
        for res in results:
            payload.append(
                {
                    "product": res.product,
                    "checked_files": res.checked_files,
                    "actions": [
                        {
                            "source_path": str(action.source_path),
                            "target": action.target,
                            "status": action.status,
                            "candidates": action.candidates,
                            "restored_path": action.restored_path,
                        }
                        for action in res.actions
                    ],
                }
            )
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    for res in results:
        typer.echo(f"# Product: {res.product}")
        typer.echo(f"- checked_files: {res.checked_files}")
        typer.echo(f"- actions: {len(res.actions)}")
        if res.actions:
            for action in res.actions:
                candidates = ", ".join(action.candidates) if action.candidates else "-"
                typer.echo(
                    f"  - {action.source_path} target={action.target} status={action.status} "
                    f"restored={action.restored_path or '-'} candidates={candidates}"
                )
        else:
            typer.echo("  - OK: no missing targets detected")
        typer.echo("")


@app.command("remap-id")
def remap_id(
    item_ref: str = typer.Argument(..., help="Item ID, UID, or path to remap"),
    new_id: str | None = typer.Option(None, "--new-id", help="Explicit new ID (optional)"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    agent: str = typer.Option(..., "--agent", help="Agent name for audit/worklog"),
    model: str | None = typer.Option(None, "--model", help="Model used by agent"),
    update_refs: bool = typer.Option(True, "--update-refs/--no-update-refs", help="Update references across backlog"),
    apply: bool = typer.Option(False, "--apply", help="Write remapped files to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Remap an item ID and optionally update references across the backlog."""
    ensure_core_on_path()
    from kano_backlog_ops.workitem import remap_item_id

    result = remap_item_id(
        item_ref,
        agent=agent,
        model=model,
        product=product,
        backlog_root=backlog_root,
        new_id=new_id,
        update_refs=update_refs,
        apply=apply,
    )

    if output_format == "json":
        payload = {
            "old_id": result.old_id,
            "new_id": result.new_id,
            "old_path": str(result.old_path),
            "new_path": str(result.new_path),
            "updated_files": result.updated_files,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Remap ID: {result.old_id} -> {result.new_id}")
    typer.echo(f"- old_path: {result.old_path}")
    typer.echo(f"- new_path: {result.new_path}")
    typer.echo(f"- updated_files: {result.updated_files}")


@app.command("remap-ref")
def remap_ref(
    path: Path = typer.Argument(..., help="Path to reference file to remap (e.g., ADR)"),
    prefix: str = typer.Option("ADR", "--prefix", help="Reference prefix (default: ADR)"),
    product: str | None = typer.Option(None, "--product", help="Product name"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    update_refs: bool = typer.Option(True, "--update-refs/--no-update-refs", help="Update references across backlog"),
    apply: bool = typer.Option(False, "--apply", help="Write remapped files to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Remap a reference ID (e.g., ADR-0004) and update links across the product."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import remap_reference_id

    result = remap_reference_id(
        path,
        product=product,
        backlog_root=backlog_root,
        prefix=prefix,
        update_refs=update_refs,
        apply=apply,
    )

    if output_format == "json":
        payload = {
            "old_id": result.old_id,
            "new_id": result.new_id,
            "old_path": str(result.old_path),
            "new_path": str(result.new_path),
            "updated_files": result.updated_files,
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Remap Ref: {result.old_id} -> {result.new_id}")
    typer.echo(f"- old_path: {result.old_path}")
    typer.echo(f"- new_path: {result.new_path}")
    typer.echo(f"- updated_files: {result.updated_files}")


@app.command("normalize-ids")
def normalize_ids(
    product: str | None = typer.Option(None, "--product", help="Product name"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    agent: str = typer.Option(..., "--agent", help="Agent name for audit/worklog"),
    model: str | None = typer.Option(None, "--model", help="Model used by agent"),
    apply: bool = typer.Option(False, "--apply", help="Write remapped files to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Normalize duplicate IDs using UID/content checks."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import normalize_duplicate_ids

    results = normalize_duplicate_ids(
        product=product,
        backlog_root=backlog_root,
        agent=agent,
        model=model,
        apply=apply,
    )

    if output_format == "json":
        payload = []
        for res in results:
            payload.append(
                {
                    "product": res.product,
                    "checked": res.checked,
                    "duplicates": res.duplicates,
                    "conflicts": [
                        {
                            "id": conflict.id,
                            "uid": conflict.uid,
                            "paths": conflict.paths,
                            "hashes": conflict.hashes,
                        }
                        for conflict in res.conflicts
                    ],
                    "remaps": [
                        {
                            "old_id": remap.old_id,
                            "new_id": remap.new_id,
                            "uid": remap.uid,
                            "old_path": str(remap.old_path),
                            "new_path": str(remap.new_path),
                            "status": remap.status,
                        }
                        for remap in res.remaps
                    ],
                }
            )
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    for res in results:
        typer.echo(f"# Product: {res.product}")
        typer.echo(f"- checked: {res.checked}")
        typer.echo(f"- duplicates: {res.duplicates}")
        typer.echo(f"- conflicts: {len(res.conflicts)}")
        for conflict in res.conflicts:
            typer.echo(f"  - conflict id={conflict.id} uid={conflict.uid}")
            for path in conflict.paths:
                typer.echo(f"    - {path}")
        typer.echo(f"- remaps: {len(res.remaps)}")
        for remap in res.remaps:
            typer.echo(
                f"  - {remap.old_id} -> {remap.new_id} status={remap.status} "
                f"path={remap.old_path} new_path={remap.new_path}"
            )
        typer.echo("")

@app.command("replace-id")
def replace_id(
    old_id: str = typer.Argument(..., help="Old ID to replace"),
    new_id: str = typer.Argument(..., help="New ID to insert"),
    path: list[Path] = typer.Option(..., "--path", help="Markdown file path to update (repeatable)"),
    skip_worklog: bool = typer.Option(True, "--skip-worklog/--no-skip-worklog", help="Skip Worklog section edits"),
    apply: bool = typer.Option(False, "--apply", help="Write changes to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Replace an ID token in specific files."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import replace_id_in_files

    updated = replace_id_in_files(
        path,
        old_id=old_id,
        new_id=new_id,
        skip_worklog=skip_worklog,
        apply=apply,
    )

    if output_format == "json":
        payload = {"old_id": old_id, "new_id": new_id, "updated_files": updated}
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Replace ID: {old_id} -> {new_id}")
    typer.echo(f"- updated_files: {updated}")


@app.command("replace-target")
def replace_target(
    old_id: str = typer.Argument(..., help="Old ID to replace in link targets"),
    new_path: Path = typer.Argument(..., help="New target path to link to"),
    path: list[Path] = typer.Option(..., "--path", help="Markdown file path to update (repeatable)"),
    apply: bool = typer.Option(False, "--apply", help="Write changes to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Replace link targets that reference an ID with a new resolved path."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import replace_link_targets

    updated = replace_link_targets(
        path,
        old_id=old_id,
        new_path=new_path,
        apply=apply,
    )

    if output_format == "json":
        payload = {"old_id": old_id, "new_path": str(new_path), "updated_files": updated}
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"# Replace Target: {old_id} -> {new_path}")
    typer.echo(f"- updated_files: {updated}")
