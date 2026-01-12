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
from .commands import admin as admin_cmd  # noqa: E402
from .commands import workitem as workitem_cmd  # noqa: E402
from .commands import state as state_cmd  # noqa: E402
from .commands import worklog as worklog_cmd  # noqa: E402
from .commands import view as view_cmd  # noqa: E402
from .commands import index as index_cmd  # noqa: E402
from .commands import demo as demo_cmd  # noqa: E402
from .commands import persona as persona_cmd  # noqa: E402
from .commands import sandbox as sandbox_cmd  # noqa: E402
from .commands import validate as validate_cmd  # noqa: E402
from .commands import adr as adr_cmd  # noqa: E402
from .commands import workset as workset_cmd  # noqa: E402
from .commands import topic as topic_cmd  # noqa: E402
from .commands.doctor import doctor as doctor_fn  # noqa: E402

app.add_typer(admin_cmd.app, name="admin", help="Administrative and setup commands")
app.add_typer(workitem_cmd.app, name="workitem", help="Work item operations")
app.add_typer(state_cmd.app, name="state", help="State transitions")
app.add_typer(worklog_cmd.app, name="worklog", help="Worklog operations")
app.add_typer(view_cmd.app, name="view", help="View and dashboard operations")
app.add_typer(workset_cmd.app, name="workset", help="Workset cache operations")
app.add_typer(topic_cmd.app, name="topic", help="Topic context operations")
# Nest index, demo, persona, and sandbox under admin group
admin_cmd.app.add_typer(index_cmd.app, name="index", help="Index operations")
admin_cmd.app.add_typer(demo_cmd.app, name="demo", help="Demo data operations")
admin_cmd.app.add_typer(persona_cmd.app, name="persona", help="Persona activity operations")
admin_cmd.app.add_typer(sandbox_cmd.app, name="sandbox", help="Sandbox environment operations")
admin_cmd.app.add_typer(validate_cmd.app, name="validate", help="Backlog validation helpers")
admin_cmd.app.add_typer(adr_cmd.app, name="adr", help="ADR operations")
app.command(name="doctor")(doctor_fn)


def main():
    app()
