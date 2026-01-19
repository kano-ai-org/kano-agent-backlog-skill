"""CLI commands for schema validation and fixing."""

from __future__ import annotations
from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Schema validation and fixing")


@app.command("check")
def check_schema(
    product: str | None = typer.Option(None, "--product", help="Product name (check all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
):
    """Check for missing required fields in backlog items."""
    ensure_core_on_path()
    from kano_backlog_ops.schema_fix import validate_schema
    
    results = validate_schema(product=product, backlog_root=backlog_root)
    
    total_checked = 0
    total_issues = 0
    
    for result in results:
        total_checked += result.checked
        total_issues += len(result.issues)
        
        if result.issues:
            typer.echo(f"\n❌ {result.product}: {len(result.issues)} items with missing fields")
            for issue in result.issues:
                typer.echo(f"\n  {issue.item_id} ({issue.path.name})")
                for missing in issue.missing_fields:
                    typer.echo(f"    - {missing.field}: {missing.expected_type}")
        else:
            typer.echo(f"✓ {result.product}: all {result.checked} items have required fields")
    
    typer.echo(f"\nTotal: {total_checked} items checked, {total_issues} with issues")
    
    if total_issues:
        raise typer.Exit(1)


@app.command("fix")
def fix_schema(
    product: str | None = typer.Option(None, "--product", help="Product name (fix all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    agent: str = typer.Option(..., "--agent", help="Agent name for worklog"),
    model: str | None = typer.Option(None, "--model", help="Model name for worklog"),
    apply: bool = typer.Option(False, "--apply", help="Apply fixes (dry-run by default)"),
):
    """Fix missing required fields in backlog items."""
    ensure_core_on_path()
    from kano_backlog_ops.schema_fix import fix_schema as fix_schema_op
    
    results = fix_schema_op(
        product=product,
        backlog_root=backlog_root,
        agent=agent,
        model=model,
        apply=apply,
    )
    
    total_checked = 0
    total_issues = 0
    total_fixed = 0
    
    for result in results:
        total_checked += result.checked
        total_issues += len(result.issues)
        total_fixed += result.fixed
        
        if result.issues:
            status = "Fixed" if apply else "Would fix"
            typer.echo(f"\n{status} {result.product}: {len(result.issues)} items")
            for issue in result.issues:
                typer.echo(f"  {issue.item_id}: {', '.join(m.field for m in issue.missing_fields)}")
        else:
            typer.echo(f"✓ {result.product}: all {result.checked} items OK")
    
    typer.echo(f"\nTotal: {total_checked} checked, {total_issues} issues, {total_fixed} {'fixed' if apply else 'would fix'}")
    
    if not apply and total_issues:
        typer.echo("\n⚠️  Dry-run mode. Use --apply to write changes.")
