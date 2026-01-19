from __future__ import annotations

import json
from pathlib import Path
import typer

from .util import configure_stdio, ensure_core_on_path, resolve_product_root

app = typer.Typer(help="kano: Backlog management CLI (MVP)")


@app.callback()
def _init():
    configure_stdio()
    ensure_core_on_path()


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
from .commands import links as links_cmd  # noqa: E402
from .commands import items as items_cmd  # noqa: E402
from .commands import adr as adr_cmd  # noqa: E402
from .commands import schema as schema_cmd  # noqa: E402
from .commands import meta as meta_cmd  # noqa: E402
from .commands import workset as workset_cmd  # noqa: E402
from .commands import topic as topic_cmd  # noqa: E402
from .commands import config_cmd as config_cmd  # noqa: E402
from .commands import snapshot as snapshot_cmd  # noqa: E402
from .commands import changelog as changelog_cmd  # noqa: E402
from .commands import benchmark as benchmark_cmd  # noqa: E402
from .commands.doctor import doctor as doctor_fn  # noqa: E402

app.add_typer(admin_cmd.app, name="admin", help="Administrative and setup commands")
app.add_typer(workitem_cmd.app, name="workitem", help="Work item operations")
app.add_typer(workitem_cmd.app, name="item", help="Work item operations (alias)")
app.add_typer(state_cmd.app, name="state", help="State transitions")
app.add_typer(worklog_cmd.app, name="worklog", help="Worklog operations")
app.add_typer(view_cmd.app, name="view", help="View and dashboard operations")
app.add_typer(snapshot_cmd.app, name="snapshot", help="Snapshot and evidence operations")
app.add_typer(workset_cmd.app, name="workset", help="Workset cache operations")
app.add_typer(topic_cmd.app, name="topic", help="Topic context operations")
app.add_typer(config_cmd.app, name="config", help="Config inspection and validation")
app.add_typer(changelog_cmd.app, name="changelog", help="Changelog generation from backlog")
app.add_typer(benchmark_cmd.app, name="benchmark", help="Deterministic benchmark harness")
# Nest index, demo, persona, and sandbox under admin group
admin_cmd.app.add_typer(index_cmd.app, name="index", help="Index operations")
admin_cmd.app.add_typer(demo_cmd.app, name="demo", help="Demo data operations")
admin_cmd.app.add_typer(persona_cmd.app, name="persona", help="Persona activity operations")
admin_cmd.app.add_typer(sandbox_cmd.app, name="sandbox", help="Sandbox environment operations")
admin_cmd.app.add_typer(validate_cmd.app, name="validate", help="Backlog validation helpers")
admin_cmd.app.add_typer(links_cmd.app, name="links", help="Link maintenance helpers")
admin_cmd.app.add_typer(items_cmd.app, name="items", help="Item maintenance helpers")
admin_cmd.app.add_typer(adr_cmd.app, name="adr", help="ADR operations")
admin_cmd.app.add_typer(schema_cmd.app, name="schema", help="Schema validation and fixing")
admin_cmd.app.add_typer(meta_cmd.app, name="meta", help="Meta file helpers")
app.command(name="doctor")(doctor_fn)


def main():
    app()
