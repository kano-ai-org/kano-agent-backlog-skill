from __future__ import annotations

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
