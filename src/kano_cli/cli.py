from __future__ import annotations

import json
from pathlib import Path
import typer

from .util import ensure_core_on_path, resolve_product_root

app = typer.Typer(help="kano: Backlog management CLI (MVP)")


@app.callback()
def _init():
    ensure_core_on_path()


# Subcommands are registered in commands/*.py
from .commands import init as backlog_cmd  # noqa: E402
from .commands import item as item_cmd  # noqa: E402
from .commands import state as state_cmd  # noqa: E402
from .commands import worklog as worklog_cmd  # noqa: E402
from .commands import view as view_cmd  # noqa: E402
from .commands import index as index_cmd  # noqa: E402
from .commands import demo as demo_cmd  # noqa: E402
from .commands.doctor import doctor as doctor_fn  # noqa: E402

app.add_typer(backlog_cmd.app, name="backlog", help="Backlog administration commands")
app.add_typer(backlog_cmd.legacy_app, name="init", help="Initialization helpers (legacy alias)")
app.add_typer(item_cmd.app, name="item", help="Item operations")
app.add_typer(state_cmd.app, name="state", help="State transitions")
app.add_typer(worklog_cmd.app, name="worklog", help="Worklog operations")
app.add_typer(view_cmd.app, name="view", help="View and dashboard operations")
# Nest index and demo under backlog group to match `kano backlog index ...` and `kano backlog demo ...`
backlog_cmd.app.add_typer(index_cmd.app, name="index", help="Index operations")
backlog_cmd.app.add_typer(demo_cmd.app, name="demo", help="Demo data operations")
app.command(name="doctor")(doctor_fn)


def main():
    app()
