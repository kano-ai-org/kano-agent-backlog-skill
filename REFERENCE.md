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
- `indexing_schema.sql`: optional DB index schema (SQLite-first)
- `indexing_schema.json`: DB schema description (machine-readable)

## Scripts (optional automation)

Backlog scripts:
- `scripts/backlog/bootstrap_init_backlog.py`: initialize `_kano/backlog` scaffold (folders + `_meta/indexes.md` + backlog `README.md`); respects `process.profile` / `process.path` for item folders
- `scripts/backlog/bootstrap_init_project.py`: first-run bootstrap (scaffold + baseline config + dashboards + optional agent guides)
- `scripts/backlog/process_linter.py`: validate item folders against active process profile (optionally create missing)
- `scripts/backlog/workitem_create.py`: create a backlog work item from template (ID + bucket + optional Epic index)
- `scripts/backlog/workitem_update_state.py`: update `state` + `updated` and append Worklog
- `scripts/backlog/workitem_validate_ready.py`: check Ready gate sections
- `scripts/backlog/view_generate.py`: generate plain Markdown views
- `scripts/backlog/view_refresh_dashboards.py`: rebuild SQLite index (optional) and refresh standard dashboards
- `scripts/backlog/view_generate_tag.py`: generate a Markdown view for items by tag (DBIndex or file scan)
- `scripts/backlog/view_generate_demo.py`: generate DBIndex vs NoDBIndex demo views
- `scripts/backlog/version_show.py`: show skill version/build info (VERSION/CHANGELOG pointers)
- `scripts/backlog/workitem_generate_index.py`: generate item index (MOC) with task state labels (Epic/Feature/UserStory)
- `scripts/backlog/bootstrap_seed_demo.py`: seed demo Epic/Feature/UserStory/Task/Bug items (tagged `demo-seed`) and plain Markdown views
- `scripts/backlog/tests_smoke.py`: smoke tests for the backlog scripts

Grouped CLI wrappers (optional aliases, same behavior):
- `scripts/backlog/cli/workitem_create.py` -> `scripts/backlog/workitem_create.py`
- `scripts/backlog/cli/workitem_update_state.py` -> `scripts/backlog/workitem_update_state.py`
- `scripts/backlog/cli/workitem_validate_ready.py` -> `scripts/backlog/workitem_validate_ready.py`
- `scripts/backlog/cli/workitem_generate_index.py` -> `scripts/backlog/workitem_generate_index.py`
- `scripts/backlog/cli/workitem_resolve_ref.py` -> `scripts/backlog/workitem_resolve_ref.py`
- `scripts/backlog/cli/view_generate.py` -> `scripts/backlog/view_generate.py`
- `scripts/backlog/cli/view_refresh_dashboards.py` -> `scripts/backlog/view_refresh_dashboards.py`
- `scripts/backlog/cli/view_generate_tag.py` -> `scripts/backlog/view_generate_tag.py`
- `scripts/backlog/cli/view_generate_demo.py` -> `scripts/backlog/view_generate_demo.py`
- `scripts/backlog/cli/bootstrap_init_backlog.py` -> `scripts/backlog/bootstrap_init_backlog.py`
- `scripts/backlog/cli/bootstrap_init_project.py` -> `scripts/backlog/bootstrap_init_project.py`

Indexing scripts:
- `scripts/indexing/build_sqlite_index.py`: build a rebuildable SQLite index for file-first backlog items
- `scripts/indexing/query_sqlite_index.py`: read-only query helper for the SQLite index (presets + safe --sql)
- `scripts/indexing/render_db_view.py`: render debug/report views from SQLite (canonical dashboards use `scripts/backlog/view_generate.py --source auto`)

Filesystem scripts:
- `scripts/fs/cp_file.py`: copy a file inside the repo (requires `--agent`; auto-refresh dashboards by default)
- `scripts/fs/mv_file.py`: move a file inside the repo (requires `--agent`; auto-refresh dashboards by default)
- `scripts/fs/rm_file.py`: delete a file inside the repo (requires `--agent`; auto-refresh dashboards by default)
- `scripts/fs/trash_item.py`: move to trash then optionally delete (requires `--agent`; auto-refresh dashboards by default)

Logging scripts:
- `scripts/logging/audit_logger.py`: JSONL audit log writer + redaction
- `scripts/logging/audit_runner.py`: helper to wrap skill scripts with audit logging
- `scripts/logging/run_with_audit.py`: run a command and append an audit log entry

Shared helpers:
- `scripts/common/config_loader.py`: load config from `_kano/backlog/_config/config.json`
- `scripts/common/validate_config.py`: validate config file structure and types

Config keys used by scripts:
- `project.name`, `project.prefix`: defaults for ID prefix derivation
- `views.auto_refresh`: auto-run `scripts/backlog/view_refresh_dashboards.py` after item changes (default: true)

Test scripts:
- `scripts/tests/validate_userstories.py`: validate user story expectations

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


