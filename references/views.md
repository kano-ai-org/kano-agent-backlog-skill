# Views (Obsidian Dataview)

If you want fewer plugin dependencies, consider Obsidian **Bases** as a plugin-free alternative for table-style dashboards. See `references/bases.md`.

## Tree by parent

Use Dataview or DataviewJS to build parent/child views from `parent` fields.
Avoid encoding hierarchy in folders.
Queries should target `_kano/backlog/items` to include all item subfolders.
Hide `Done`/`Dropped` items in views by default (view-level archive).

## Example: List epics

```dataview
table id, state, priority, iteration
from "_kano/backlog/items"
where type = "Epic" and state != "Done" and state != "Dropped"
sort created asc
```

## Example: Items by iteration

```dataview
table id, type, state, priority
from "_kano/backlog/items"
where iteration != null and state != "Done" and state != "Dropped"
sort iteration asc, priority asc
```

## InProgress view (no Dataview required)

Generate plain Markdown lists (no Dataview required).

`scripts/backlog/view_generate.py` supports two data sources:

- File scan (default file-first behavior)
- SQLite index (when `index.enabled=true` and the DB exists)

When `--source auto` is used, it prefers SQLite when available, otherwise falls back to scanning files.

```bash
python scripts/backlog/view_generate.py --source auto --groups "New,InProgress" --title "InProgress Work" --output _kano/backlog/views/Dashboard_PlainMarkdown_Active.md
python scripts/backlog/view_generate.py --source auto --groups "New" --title "New Work" --output _kano/backlog/views/Dashboard_PlainMarkdown_New.md
python scripts/backlog/view_generate.py --source auto --groups "Done" --title "Done Work" --output _kano/backlog/views/Dashboard_PlainMarkdown_Done.md
```

Or refresh all standard dashboards (and optionally refresh the SQLite index first):

```bash
python scripts/backlog/view_refresh_dashboards.py --backlog-root _kano/backlog --agent <agent-name>
```

Outputs:
- `_kano/backlog/views/Dashboard_PlainMarkdown_Active.md` (New + InProgress/Review/Blocked)
- `_kano/backlog/views/Dashboard_PlainMarkdown_New.md` (New only)
- `_kano/backlog/views/Dashboard_PlainMarkdown_Done.md` (Done + Dropped)

## Demo: DBIndex vs NoDBIndex

If you want to show the difference between:
- **NoDBIndex**: file scan only
- **DBIndex**: query SQLite index (optional, derived)

Generate both variants by running the same view generator with different `--source` values:

```bash
python scripts/backlog/view_generate.py --source files --groups "New,InProgress" --title "InProgress Work (Demo: NoDBIndex)" --output _kano/backlog/views/_demo/Dashboard_Demo_NoDBIndex_Active.md
python scripts/backlog/view_generate.py --source sqlite --groups "New,InProgress" --title "InProgress Work (Demo: DBIndex)" --output _kano/backlog/views/_demo/Dashboard_Demo_DBIndex_Active.md
```

Or use the dedicated generator (preferred):
`python scripts/backlog/view_generate_demo.py --backlog-root _kano/backlog --agent <agent-name>`

If you only want a tag view:

```bash
python scripts/backlog/view_generate_tag.py --backlog-root _kano/backlog --source auto --tags \"versioning,release\" --output _kano/backlog/views/_demo/Dashboard_Demo_Tags_Versioning.md --agent <agent-name>
```
