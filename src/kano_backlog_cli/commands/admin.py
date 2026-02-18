from __future__ import annotations
from typing import Optional, Union
from pathlib import Path

import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Administrative and setup commands")

__all__ = ["app"]


@app.command("init")
def backlog(
	*,
	product: str = typer.Option(..., "--product", help="Product folder name (e.g., kano-agent-backlog-skill)"),
	agent: str = typer.Option(..., "--agent", help="Agent identifier for audit logging"),
	backlog_root: Optional[Path] = typer.Option(
		None,
		"--backlog-root",
		help="Path to _kano/backlog (auto-detected or created near the repo root)",
	),
	product_name: Optional[str] = typer.Option(
		None,
		"--product-name",
		help="Overrides product.name in config (defaults to product)",
	),
	prefix: Optional[str] = typer.Option(
		None,
		"--prefix",
		help="Overrides product.prefix in config (defaults to derived prefix)",
	),
	persona: str = typer.Option(
		"developer",
		"--persona",
		help="Default persona label recorded in config",
	),
	skill_developer: bool = typer.Option(
		False,
		"--skill-developer/--no-skill-developer",
		help="Set mode.skill_developer flag in config",
	),
	force: bool = typer.Option(
		False,
		"--force",
		help="Overwrite existing scaffold/config if the product directory already exists",
	),
	refresh_views: bool = typer.Option(
		True,
		"--refresh-views/--skip-refresh-views",
		help="Regenerate dashboards after initialization",
	),
	create_guides: bool = typer.Option(
		False,
		"--create-guides/--skip-guides",
		help="Update repo-level AGENTS.md/CLAUDE.md blocks with current instructions",
	),
	seed_demo: bool = typer.Option(
		False,
		"--seed-demo/--no-seed-demo",
		help="Seed the product with demo items after initialization",
	),
) -> None:
	"""Create the canonical backlog scaffold for a product."""

	ensure_core_on_path()
	from kano_backlog_ops.init import init_backlog

	try:
		result = init_backlog(
			product=product,
			backlog_root=backlog_root,
			agent=agent,
			product_name=product_name,
			prefix=prefix,
			persona=persona,
			skill_developer=skill_developer,
			force=force,
			create_guides=create_guides,
			refresh_views=refresh_views,
		)
	except (ValueError, FileExistsError) as exc:
		typer.echo(f"❌ {exc}", err=True)
		raise typer.Exit(1)
	except Exception as exc:  # pragma: no cover - defensive
		typer.echo(f"❌ Unexpected error: {exc}", err=True)
		raise typer.Exit(2)

	typer.echo(f"✓ Backlog initialized at {result.product_root}")
	typer.echo(f"  Config: {result.config_path}")

	if result.created_paths:
		typer.echo("  Created artifacts:")
		for path in result.created_paths:
			typer.echo(f"    • {path}")

	if result.views_refreshed:
		typer.echo(f"  Views refreshed: {len(result.views_refreshed)}")

	if result.guides_updated:
		typer.echo("  Guides updated:")
		for path in result.guides_updated:
			typer.echo(f"    • {path}")

	# Seed demo data if requested
	if seed_demo:
		from kano_backlog_ops.demo import seed_demo as ops_seed_demo
		try:
			demo_result = ops_seed_demo(
				product=product,
				agent=agent,
				backlog_root=result.context.backlog_root,
				count=5,
				force=False,
			)
			typer.echo(f"  Demo items seeded: {len(demo_result.items_created)}")
		except Exception as exc:
			typer.echo(f"⚠️  Demo seeding failed: {exc}", err=True)


@app.command("sync-sequences")
def sync_sequences(
	*,
	product: str = typer.Option(..., "--product", help="Product folder name (e.g., kano-agent-backlog-skill)"),
	backlog_root: Optional[Path] = typer.Option(
		None,
		"--backlog-root",
		help="Path to _kano/backlog (auto-detected or created near the repo root)",
	),
	dry_run: bool = typer.Option(
		False,
		"--dry-run",
		help="Print planned updates without modifying DB",
	),
) -> None:
	"""Initialize DB ID sequences from existing files."""
	ensure_core_on_path()
	from kano_backlog_ops.item_utils import sync_id_sequences

	try:
		result = sync_id_sequences(
			product=product,
			backlog_root=backlog_root,
			dry_run=dry_run,
		)
	except Exception as exc:
		typer.echo(f"❌ Error: {exc}", err=True)
		raise typer.Exit(1)

	if dry_run:
		typer.echo("Dry run - would update:")
	else:
		typer.echo("Updated sequences:")

	for type_code, next_num in result.items():
		typer.echo(f"  {type_code}: {next_num}")



