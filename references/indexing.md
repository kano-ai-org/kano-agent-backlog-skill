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

- Default location: `<product-root>/.cache/` (e.g. `_kano/backlog/products/<product>/.cache/`)
- Test/experiments: `_kano/backlog_sandbox/`

This demo repo gitignores index artifacts:

- `_kano/backlog/products/*/.cache/`
- `_kano/backlog_sandbox/`

## Config keys (index.*)

Indexing is **disabled by default** (file-first remains the default workflow).

In `_kano/backlog/products/<product>/_config/config.toml`:

```toml
[index]
enabled = false
backend = "sqlite"
path = null
mode = "rebuild"
```

- `index.enabled`: feature flag (default `false`)
- `index.backend`: `sqlite` (default) or `postgres` (optional/future)
- `index.path`: DB file path override; `null` uses `<product-root>/.cache/index.sqlite3`
- `index.mode`: `rebuild` or `incremental` (best-effort)

## Build / rebuild workflow (SQLite)

Build the SQLite index from files:

```bash
# Build index for specific product
kano-backlog admin index build --product <product-name>

# Build all product indexes
kano-backlog admin index build

# Force rebuild even if exists
kano-backlog admin index build --product <product-name> --force

# Build with vector index
kano-backlog admin index build --product <product-name> --vectors
```

Refresh (incremental update):

```bash
# Refresh specific product
kano-backlog admin index refresh --product <product-name>

# Refresh all products
kano-backlog admin index refresh
```

Check index status:

```bash
# Status for specific product
kano-backlog admin index status --product <product-name>

# Status for all products
kano-backlog admin index status
```

Safety guarantees:

- The indexer **must not modify** any source Markdown files.
- Deleting the DB is safe; it can always be rebuilt.

## Vector Search Integration

The index system integrates with the embedding pipeline for semantic search:

```bash
# Build vector index alongside SQLite index
kano-backlog admin index build --product <product-name> --vectors

# Search using vector similarity
kano-backlog search query "your search text" --product <product-name>

# Check embedding status
kano-backlog embedding status --product <product-name>
```

## Obsidian views (file-first mode)

File-first dashboards continue to work normally (Dataview or generated Markdown views), because items remain Markdown files.

Optional (planned): generate Markdown dashboards from DB queries to reduce dependence on Obsidian plugins.

If you enable `index.enabled=true`, `kano-backlog view refresh --source auto` can use the SQLite index
when present, and falls back to file scan when the DB is missing.

## Context graph (Graph-assisted retrieval)

A **context graph** is a derived, structured view of how artifacts relate (items, ADRs, dependencies, refs).
It enables **Graph-assisted retrieval**: retrieve seed nodes via FTS/embeddings, then expand via graph edges (k-hop)
to assemble a higher-quality context pack.

- Concept/spec: `references/context_graph.md`

## DB-first is out of scope

Using a database as the **source of truth** would require new UI/export tooling and changes to the human-in-the-loop workflow.
This skill intentionally keeps DB usage as an optional, derived index layer.
