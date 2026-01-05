# Indexing (Optional)

This skill is **file-first**: the source of truth is Markdown files under `_kano/backlog/`.

Indexing is an **optional, rebuildable** layer that exists to make agents and humans faster at:

- finding relevant items quickly (filters, sorting, parent/child traversal),
- producing views/reports reproducibly,
- powering later retrieval workflows (e.g. embeddings/RAG).

The index must never become a write-path requirement for normal operation.

## What is indexed

The SQLite index is derived from:

- Items: `_kano/backlog/items/**/*.md`
- Decisions/ADRs: `_kano/backlog/decisions/**/*.md` (linked via item frontmatter `decisions`)

Schema references:

- `references/indexing_schema.sql`
- `references/indexing_schema.json`

## Artifacts (where generated files live)

Generated artifacts should be treated as **build outputs**:

- Default location: `<backlog-root>/_index/` (e.g. `_kano/backlog/_index/`)
- Test/experiments: `_kano/backlog_sandbox/`

This demo repo gitignores index artifacts:

- `_kano/backlog/_index/`
- `_kano/backlog_sandbox/`

## Config keys (index.*)

Indexing is **disabled by default** (file-first remains the default workflow).

In `_kano/backlog/_config/config.json`:

```json
{
  "index": {
    "enabled": false,
    "backend": "sqlite",
    "path": null,
    "mode": "rebuild"
  }
}
```

- `index.enabled`: feature flag (default `false`)
- `index.backend`: `sqlite` (default) or `postgres` (optional/future)
- `index.path`: DB file path override; `null` uses `<backlog-root>/_index/backlog.sqlite3`
- `index.mode`: `rebuild` or `incremental` (best-effort)

## Build / rebuild workflow (SQLite)

Build the SQLite index from files:

```bash
python scripts/indexing/build_sqlite_index.py --backlog-root _kano/backlog --agent <agent-name> --mode rebuild
```

Incremental run (best-effort):

```bash
python scripts/indexing/build_sqlite_index.py --backlog-root _kano/backlog --agent <agent-name> --mode incremental
```

Safety guarantees:

- The indexer **must not modify** any source Markdown files.
- Deleting the DB is safe; it can always be rebuilt.

## Obsidian views (file-first mode)

File-first dashboards continue to work normally (Dataview or generated Markdown views), because items remain Markdown files.

Optional (planned): generate Markdown dashboards from DB queries to reduce dependence on Obsidian plugins.

If you enable `index.enabled=true`, `scripts/backlog/generate_view.py --source auto` can use the SQLite index
when present, and falls back to file scan when the DB is missing.

## DB-first is out of scope

Using a database as the **source of truth** would require new UI/export tooling and changes to the human-in-the-loop workflow.
This skill intentionally keeps DB usage as an optional, derived index layer.
