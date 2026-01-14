"""
CLI commands for changelog generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from kano_backlog_ops.changelog import (
    generate_changelog_from_backlog,
    merge_unreleased_to_version,
)

app = typer.Typer(help="Changelog generation from backlog")


@app.command(name="generate")
def generate(
    version: str = typer.Option(..., "--version", help="Version string (e.g., 0.0.1)"),
    product: Optional[str] = typer.Option(None, "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root path"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    date_str: Optional[str] = typer.Option(None, "--date", help="Release date (YYYY-MM-DD, default: today)"),
):
    """
    Generate changelog section from Done backlog items.

    Example:
        kano-backlog changelog generate --version 0.0.1 --product kano-agent-backlog-skill
    """
    try:
        result = generate_changelog_from_backlog(
            version=version,
            product=product,
            backlog_root=backlog_root,
            date_str=date_str,
        )

        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result.content, encoding="utf-8")
            typer.echo(f"✅ Generated changelog for v{version} with {result.item_count} items → {output}")
        else:
            typer.echo(result.content)

    except Exception as e:
        typer.secho(f"❌ Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


@app.command(name="merge-unreleased")
def merge_unreleased(
    version: str = typer.Option(..., "--version", help="Version to merge into (e.g., 0.0.1)"),
    changelog: Path = typer.Option(Path("CHANGELOG.md"), "--changelog", help="Path to CHANGELOG.md"),
    date_str: Optional[str] = typer.Option(None, "--date", help="Release date (YYYY-MM-DD, default: today)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing"),
):
    """
    Merge [Unreleased] section into specified version in CHANGELOG.md.

    Example:
        kano-backlog changelog merge-unreleased --version 0.0.1
        kano-backlog changelog merge-unreleased --version 0.0.1 --dry-run
    """
    try:
        # Resolve changelog path relative to current directory or skill root
        if not changelog.is_absolute():
            # Try to find skill root
            cwd = Path.cwd()
            for candidate in [cwd, *cwd.parents]:
                possible = candidate / "skills" / "kano-agent-backlog-skill" / changelog
                if possible.exists():
                    changelog = possible
                    break
            else:
                # Use as-is relative to cwd
                changelog = cwd / changelog

        updated_content = merge_unreleased_to_version(
            changelog_path=changelog,
            version=version,
            date_str=date_str,
        )

        if dry_run:
            typer.echo("🔍 Dry run - Preview of changes:\n")
            typer.echo(updated_content)
        else:
            changelog.write_text(updated_content, encoding="utf-8")
            typer.echo(f"✅ Merged [Unreleased] into [{version}] in {changelog}")

    except Exception as e:
        typer.secho(f"❌ Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
