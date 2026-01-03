# Views (Obsidian Dataview)

## Tree by parent

Use Dataview or DataviewJS to build parent/child views from `parent` fields.
Avoid encoding hierarchy in folders.
Queries should target `.kano/backlog/items` to include all item subfolders.
Hide `Done`/`Dropped` items in views by default (view-level archive).

## Example: List epics

```dataview
table id, state, priority, iteration
from ".kano/backlog/items"
where type = "Epic" and state != "Done" and state != "Dropped"
sort created asc
```

## Example: Items by iteration

```dataview
table id, type, state, priority
from ".kano/backlog/items"
where iteration != null and state != "Done" and state != "Dropped"
sort iteration asc, priority asc
```

## Active view (no Dataview required)

Generate plain Markdown lists (no Dataview required):

```bash
bash .kano/backlog/tools/generate_active_view.sh
bash .kano/backlog/tools/generate_new_view.sh
```

Outputs:
- `.kano/backlog/views/Active.md` (New + InProgress)
- `.kano/backlog/views/New.md` (New only)
