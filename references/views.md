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

Generate plain Markdown lists (no Dataview required):

```bash
bash _kano/backlog/tools/generate_active_view.sh
bash _kano/backlog/tools/generate_new_view.sh
bash _kano/backlog/tools/generate_done_view.sh
```

Outputs:
- `_kano/backlog/views/Dashboard_PlainMarkdown_Active.md` (New + InProgress/Review/Blocked)
- `_kano/backlog/views/Dashboard_PlainMarkdown_New.md` (New only)
- `_kano/backlog/views/Dashboard_PlainMarkdown_Done.md` (Done + Dropped)
