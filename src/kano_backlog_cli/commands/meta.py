from __future__ import annotations
from typing import Optional, Union
from pathlib import Path
import json
import typer

from ..util import ensure_core_on_path

app = typer.Typer(help="Meta file helpers")


@app.command("add-ticketing-guidance")
def add_ticketing_guidance(
    product: str = typer.Option(..., "--product", help="Product name"),
    backlog_root: Optional[Path] = typer.Option(None, "--backlog-root", help="Backlog root (_kano/backlog)"),
    agent: str = typer.Option(..., "--agent", help="Agent name for audit"),
    model: Optional[str] = typer.Option(None, "--model", help="Model used by agent"),
    apply: bool = typer.Option(False, "--apply", help="Write changes to disk"),
    output_format: str = typer.Option("markdown", "--format", help="Output format: markdown|json"),
):
    """Append ticketing guidance section to _meta/conventions.md."""
    ensure_core_on_path()
    from kano_backlog_ops.meta import add_ticketing_guidance as op_add

    result = op_add(
        product=product,
        backlog_root=backlog_root,
        agent=agent,
        model=model,
        apply=apply,
    )

    if output_format == "json":
        payload = {
            "product": result.product,
            "status": result.status,
            "path": str(result.path),
        }
        typer.echo(json.dumps(payload, ensure_ascii=True, indent=2))
        return

    typer.echo(f"OK: ticketing guidance {result.status}")
    typer.echo(f"  Path: {result.path}")
