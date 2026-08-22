# Reference Index

The `references/` folder is intentionally split into multiple small files so an agent (or a human) can load only what’s needed.

## Files under `references/`

- `schema.md`: item types, states, naming rules, Ready gate
- `templates.md`: work item + ADR templates
- `workflow.md`: SOP for planning/decisions/worklog
- `views.md`: custom Obsidian Markdown and Dataview patterns
- `bases.md`: Obsidian Bases notes (plugin-free table-style views)
- `logging.md`: audit log schema, redaction, rotation defaults
- `processes.md`: process profile schema and examples
- `indexing.md`: optional indexing layer (artifacts, config, rebuild workflow)
- `context_graph.md`: context graph + Graph-assisted retrieval (weak graph)
- `indexing_schema.sql`: optional DB index schema (SQLite-first)
- `indexing_schema.json`: DB schema description (machine-readable)

## Kano CLI (automation surface)

`scripts/kob` is the native CLI entrypoint. Subcommands map to the ops layer:

### Core commands
- `kob doctor`: verify native prerequisites and backlog initialization
- `kob admin init`: scaffold product directories and project configuration
- `kob view list`: discover hand-authored custom Markdown views
- `kob gui`: open Backboard, the maintained backlog review surface

### Item operations
- `kob item read|validate`: inspect canonical records
- `kob item create`: create items
- `kob item set-ready`: set Ready-gate body sections (Context/Goal/Approach/Acceptance/Risks)
- `kob item update-state`: state transitions and worklog append

### State and worklog
- `kano state transition`: declarative workflow actions (`start`, `ready`, `review`, `done`, `block`, `drop`)
- `kano worklog append`: structured worklog writes with agent/model attribution

### Backlog administration (nested under `backlog`)
- `kano backlog index build|refresh`: build/refresh SQLite index from markdown items
- `kano backlog demo seed`: seed demo data (1 epic → 1 feature → 3 tasks) for testing
- `kano backlog persona summary|report`: generate persona activity summaries/reports
- `kano backlog sandbox init`: scaffold isolated sandbox environments for experimentation
- `kano config show|validate|migrate-json|export|init`: inspect/validate/migrate/export config (TOML-first; `product.*` required)

No new standalone scripts will be added under `scripts/`; all operations flow through the unified CLI.

## Related (demo repo convention)

In the demo host repo, the backlog lives under `_kano/backlog/`:

- Items: `_kano/backlog/items/**`
- Decisions/ADRs: `_kano/backlog/decisions/**`
- Views: `_kano/backlog/views/**`
- Tools: `_kano/backlog/tools/**`
- Product configs: `_kano/backlog/products/<product>/_config/config.toml` (`product.name`, `product.prefix`)

## Versioning

- Versioning policy: `VERSIONING.md` (Git tags `vX.Y.Z`)

## Templates (optional)

- `templates/AGENTS.block.md`: snippet for Codex-style agent instructions (append/update into repo-root `AGENTS.md`)
- `templates/CLAUDE.block.md`: snippet for Claude-style instructions (append/update into repo-root `CLAUDE.md`)


