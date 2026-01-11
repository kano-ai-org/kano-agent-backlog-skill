# Reference Index

The `references/` folder is intentionally split into multiple small files so an agent (or a human) can load only what’s needed.

## Files under `references/`

- `schema.md`: item types, states, naming rules, Ready gate
- `templates.md`: work item + ADR templates
- `workflow.md`: SOP for planning/decisions/worklog
- `views.md`: view patterns (Dataview + plain Markdown generators)
- `bases.md`: Obsidian Bases notes (plugin-free table-style views)
- `logging.md`: audit log schema, redaction, rotation defaults
- `processes.md`: process profile schema and examples
- `indexing.md`: optional indexing layer (artifacts, config, rebuild workflow)
- `context_graph.md`: context graph + Graph-assisted retrieval (weak graph)
- `indexing_schema.sql`: optional DB index schema (SQLite-first)
- `indexing_schema.json`: DB schema description (machine-readable)

## Kano CLI (automation surface)

`scripts/` now ships a single entrypoint (`scripts/kano`). Subcommands map 1:1 to the ops layer:

- `kano doctor`: verify Python prerequisites and backlog initialization
- `kano backlog init`: scaffold a product backlog (directories, `_config/config.json`, dashboards)
- `kano item read|validate`: inspect canonical records
- `kano item create`: create items with Ready-gate aware defaults (alias `create-v2` for compatibility)
- `kano item update-state`: state transitions + worklog append + optional dashboard refresh
- `kano state transition`: declarative workflow actions (`start`, `ready`, `review`, `done`, `block`, `drop`)
- `kano worklog append`: structured worklog writes with agent/model attribution
- `kano view refresh`: regenerate dashboards (Active/New/Done) and, in future, persona summaries/reports

Upcoming CLI work will add demo generators, persona reporters, and filesystem helpers—no new standalone scripts will be added under `scripts/`.

## Related (demo repo convention)

In the demo host repo, the backlog lives under `_kano/backlog/`:

- Items: `_kano/backlog/items/**`
- Decisions/ADRs: `_kano/backlog/decisions/**`
- Views: `_kano/backlog/views/**`
- Tools: `_kano/backlog/tools/**`

## Versioning

- Versioning policy: `VERSIONING.md` (Git tags `vX.Y.Z`)

## Templates (optional)

- `templates/AGENTS.block.md`: snippet for Codex-style agent instructions (append/update into repo-root `AGENTS.md`)
- `templates/CLAUDE.block.md`: snippet for Claude-style instructions (append/update into repo-root `CLAUDE.md`)


