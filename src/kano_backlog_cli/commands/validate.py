from __future__ import annotations

import json
from pathlib import Path
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Validation helpers")


def _find_skill_root() -> Path | None:
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "skills" / "kano-agent-backlog-skill"
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


@app.command("uids")
def validate_uids(
    product: str | None = typer.Option(None, "--product", help="Product name (validate all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
):
    """Validate that all backlog items use UUIDv7 UIDs."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import validate_uids as validate_uids_op

    results = validate_uids_op(product=product, backlog_root=backlog_root)

    total_checked = 0
    total_violations = 0
    for res in results:
        total_checked += res.checked
        total_violations += len(res.violations)
        if res.violations:
            typer.echo(f"❌ {res.product}: {len(res.violations)} UID violations")
            for v in res.violations:
                typer.echo(f"  - {v.path}: {v.uid} ({v.reason})")
        else:
            typer.echo(f"✓ {res.product}: all {res.checked} items have UUIDv7 UIDs")

    if total_violations:
        raise typer.Exit(1)
    typer.echo(f"All products clean. Items checked: {total_checked}")


@app.command("repo-layout")
def validate_repo_layout() -> None:
    """Validate the skill repo layout (guards against legacy package regressions)."""
    skill_root = _find_skill_root()
    if skill_root is None:
        typer.echo("✓ Skill root not found from cwd; skipping repo-layout checks")
        raise typer.Exit(0)

    legacy_cli_root = skill_root / "src" / "kano_cli"
    legacy_py_files = list(legacy_cli_root.rglob("*.py")) if legacy_cli_root.exists() else []
    if legacy_py_files:
        typer.echo("❌ Legacy CLI package detected under src/kano_cli")
        for path in legacy_py_files[:10]:
            typer.echo(f"  - {path}")
        if len(legacy_py_files) > 10:
            typer.echo(f"  ... and {len(legacy_py_files) - 10} more")
        typer.echo("Fix: move CLI code under src/kano_backlog_cli and remove src/kano_cli")
        raise typer.Exit(1)

    typer.echo("✓ Repo layout OK (no legacy src/kano_cli python files)")



@app.command("links")
def validate_links(
    product: str | None = typer.Option(None, "--product", help="Product name (validate all if omitted)"),
    backlog_root: Path | None = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    include_views: bool = typer.Option(False, "--include-views", help="Scan views/ markdown (derived output)"),
    ignore_target: list[str] | None = typer.Option(
        None,
        "--ignore-target",
        help="Glob pattern for targets to ignore (repeatable)",
    ),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Validate markdown links and wikilinks within backlog content."""
    ensure_core_on_path()
    from kano_backlog_ops.validate import validate_links as validate_links_op

    ignore_target = ignore_target or []
    results = validate_links_op(
        product=product,
        backlog_root=backlog_root,
        include_views=include_views,
        ignore_targets=ignore_target,
    )

    if output_format == "json":
        payload = []
        for res in results:
            payload.append(
                {
                    "product": res.product,
                    "checked_files": res.checked_files,
                    "issues": [
                        {
                            "source_path": str(issue.source_path),
                            "line": issue.line,
                            "column": issue.column,
                            "link_type": issue.link_type,
                            "link_text": issue.link_text,
                            "target": issue.target,
                        }
                        for issue in res.issues
                    ],
                }
            )
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    total_issues = 0
    for res in results:
        total_issues += len(res.issues)
        typer.echo(f"# Product: {res.product}")
        typer.echo(f"- checked_files: {res.checked_files}")
        typer.echo(f"- issues: {len(res.issues)}")
        if res.issues:
            for issue in res.issues:
                typer.echo(
                    f"  - {issue.source_path}:{issue.line}:{issue.column} "
                    f"[{issue.link_type}] target={issue.target} text={issue.link_text}"
                )
        else:
            typer.echo("  - OK: no broken links detected")
        typer.echo("")

    if total_issues:
        raise typer.Exit(1)
