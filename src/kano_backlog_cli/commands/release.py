from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..util import ensure_core_on_path


app = typer.Typer(help="Release verification workflows")


@app.command("check")
def check(
    version: str = typer.Option(..., "--version", help="Target release version (e.g., 0.0.2)"),
    topic: str = typer.Option(..., "--topic", help="Topic name to store reports under"),
    agent: str = typer.Option(..., "--agent", help="Agent identity for audit trail"),
    product: str = typer.Option(
        "kano-agent-backlog-skill",
        "--product",
        help="Source product name for sandbox init",
    ),
    sandbox_name: str = typer.Option(
        "release-0-0-2-smoke",
        "--sandbox",
        help="Sandbox name used for Phase 2 checks",
    ),
    phase: str = typer.Option(
        "all",
        "--phase",
        help="Which phase to run: phase1|phase2|all",
    ),
):
    """Run release checks and write reports to the given topic."""

    ensure_core_on_path()
    from kano_backlog_ops.release_check import run_phase1, run_phase2, format_report_md
    from kano_backlog_ops.topic import _find_backlog_root, get_topic_path, pin_document

    backlog_root = _find_backlog_root()
    topic_path = get_topic_path(topic, backlog_root)
    publish_dir = topic_path / "publish"
    publish_dir.mkdir(parents=True, exist_ok=True)

    phase_norm = phase.strip().lower()
    if phase_norm not in {"phase1", "phase2", "all"}:
        raise typer.BadParameter("phase must be one of: phase1, phase2, all")

    wrote_any = False

    if phase_norm in {"phase1", "all"}:
        report = run_phase1(version=version)
        out_path = publish_dir / f"release_check_{version}_phase1.md"
        out_path.write_text(format_report_md(report), encoding="utf-8")
        # Pin for discoverability (stored relative to workspace root).
        pin_document(topic, str(out_path.relative_to(backlog_root.parent.parent)).replace("\\", "/"), backlog_root=backlog_root)
        typer.echo(f"OK: wrote {out_path}")
        wrote_any = True

    if phase_norm in {"phase2", "all"}:
        report = run_phase2(
            version=version,
            sandbox_name=sandbox_name,
            product=product,
            agent=agent,
            artifact_dir=publish_dir,
        )
        out_path = publish_dir / f"release_check_{version}_phase2.md"
        out_path.write_text(format_report_md(report), encoding="utf-8")
        pin_document(topic, str(out_path.relative_to(backlog_root.parent.parent)).replace("\\", "/"), backlog_root=backlog_root)
        typer.echo(f"OK: wrote {out_path}")
        wrote_any = True

    if not wrote_any:
        typer.echo("No phases executed")
