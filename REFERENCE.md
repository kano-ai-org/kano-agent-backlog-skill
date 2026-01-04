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

## Scripts (optional automation)

Backlog scripts:
- `scripts/backlog/init_backlog.py`: initialize `_kano/backlog` scaffold
- `scripts/backlog/create_item.py`: create a new item from template (ID + bucket + optional Epic index)
- `scripts/backlog/update_state.py`: update `state` + `updated` and append Worklog
- `scripts/backlog/validate_ready.py`: check Ready gate sections
- `scripts/backlog/generate_view.py`: generate plain Markdown views
- `scripts/backlog/generate_epic_index.py`: generate item index (MOC) with task state labels (Epic/Feature/UserStory)
- `scripts/backlog/seed_demo.py`: seed demo items and views
- `scripts/backlog/test_scripts.py`: smoke tests for the backlog scripts

Filesystem scripts:
- `scripts/fs/cp_file.py`: copy a file inside the repo
- `scripts/fs/mv_file.py`: move a file inside the repo
- `scripts/fs/rm_file.py`: delete a file inside the repo
- `scripts/fs/trash_item.py`: move to trash then optionally delete

Logging scripts:
- `scripts/logging/audit_logger.py`: JSONL audit log writer + redaction
- `scripts/logging/audit_runner.py`: helper to wrap skill scripts with audit logging
- `scripts/logging/run_with_audit.py`: run a command and append an audit log entry

Shared helpers:
- `scripts/common/config_loader.py`: load config from `_kano/backlog/_config/config.json`

Test scripts:
- `scripts/tests/validate_userstories.py`: validate user story expectations

## Related (demo repo convention)

In the demo host repo, the backlog lives under `_kano/backlog/`:

- Items: `_kano/backlog/items/**`
- Decisions/ADRs: `_kano/backlog/decisions/**`
- Views: `_kano/backlog/views/**`
- Tools: `_kano/backlog/tools/**`


