---
name: project-backlog
description: Local-first backlog workflow for this repo. Use when planning work, creating or updating Epics/Features/UserStories/Tasks/Bugs, writing ADRs, or enforcing the Ready gate before code changes.
metadata:
  short-description: Local backlog system
---

# Project Backlog (local-first)

## Scope

Use this skill to:
- Plan new work by creating backlog items before code changes.
- Maintain Epic -> Feature -> UserStory -> Task/Bug hierarchy via parent links.
- Record decisions with ADRs and link them to items.
- Keep a durable, append-only worklog for project evolution.

## Non-negotiables

- Planning before coding: create/update items and meet the Ready gate before making code changes.
- Worklog is append-only; never rewrite history.
- Update Worklog whenever:
  - a discussion produces a clear decision or direction,
  - an item state changes,
  - scope/approach changes,
  - or an ADR is created/linked.
- Archive by view: hide `Done`/`Dropped` items in views by default; do not move files unless explicitly requested.
- Backlog volume control:
  - Only create items for work that changes code or design decisions.
  - Avoid new items for exploratory discussion; record in existing Worklog instead.
  - Keep Tasks/Bugs sized for a single focused session.
  - Avoid ADRs unless a real architectural trade-off is made.
- Ticketing threshold (agent-decided):
  - Open a new Task/Bug when you will change code/docs/views/scripts.
  - Open an ADR (and link it) when a real trade-off or direction change is decided.
  - Otherwise, record the discussion in an existing Worklog; ask if unsure.
- State ownership: the agent decides when to move items to InProgress or Done; humans observe and can add context.
- Hierarchy is in frontmatter links, not folder nesting; avoid moving files to reflect scope changes.
- Filenames stay stable; use ASCII slugs.
- Never include secrets in backlog files or logs.
- File operations for backlog/skill artifacts must go through skill scripts
  (`scripts/backlog/*` or `scripts/fs/*`) so audit logs capture the action.
- Skill scripts only operate on paths under `_kano/backlog/`; refuse other paths.
- Add Obsidian `[[wikilink]]` references in the body (e.g., a `## Links` section) so Graph/backlinks work; frontmatter alone does not create graph edges.

## ID prefix derivation

- Source of truth: `config/profile.env` -> `PROJECT_NAME`.
- Derivation:
  - Split `PROJECT_NAME` on non-alphanumeric separators and camel-case boundaries.
  - Take the first letter of each segment.
  - If only one letter, take the first letter plus the next consonant (A/E/I/O/U skipped).
  - If still short, use the first two letters.
  - Uppercase the result.
- Example: `PROJECT_NAME=kano-agent-backlog-skill-demo` -> `KABSD`.

## Recommended layout

- `_kano/backlog/_meta/` (schema, conventions, config)
- `_kano/backlog/items/epics/`
- `_kano/backlog/items/features/`
- `_kano/backlog/items/userstories/`
- `_kano/backlog/items/tasks/`
- `_kano/backlog/items/bugs/`
- `_kano/backlog/decisions/` (ADR files)
- `_kano/backlog/views/` (Obsidian Dataview/DataviewJS)

## Item bucket folders (per 100)

- Store items under `_kano/backlog/items/<type>/<bucket>/`.
- Bucket names use 4 digits for the lower bound of each 100 range.
  - Example: `0000`, `0100`, `0200`, `0300`, ...
- Example path:
  - `_kano/backlog/items/tasks/0000/KABSD-TSK-0007_define-secret-provider-validation.md`

## Index/MOC files

- For Epic, create an adjacent index file:
  - `<ID>_<slug>.index.md`
- Index files should render a tree using Dataview/DataviewJS and rely on `parent` links.
- Track epic index files in `_kano/backlog/_meta/indexes.md` (type, item_id, index_file, updated, notes).

## References

- Reference index: `REFERENCE.md`
- Schema and rules: `references/schema.md`
- Templates: `references/templates.md`
- Workflow SOP: `references/workflow.md`
- View patterns: `references/views.md`
- Obsidian Bases (plugin-free): `references/bases.md`

If the backlog structure is missing, propose creation and wait for user approval before writing files.

## Scripts (optional automation)

Backlog scripts:
- `scripts/backlog/create_item.py`: create a new item with ID + bucket (Epic can also create an index file)
- `scripts/backlog/update_state.py`: update `state` + `updated` and append Worklog
- `scripts/backlog/validate_ready.py`: check Ready gate sections
- `scripts/backlog/generate_view.py`: generate plain Markdown views
- `scripts/backlog/test_scripts.py`: smoke tests for the backlog scripts

Filesystem scripts:
- `scripts/fs/cp_file.py`: copy a file inside the repo
- `scripts/fs/mv_file.py`: move a file inside the repo
- `scripts/fs/rm_file.py`: delete a file inside the repo
- `scripts/fs/trash_item.py`: move to trash then optionally delete

Logging scripts:
- `scripts/logging/audit_logger.py`: JSONL audit log writer + redaction
- `scripts/logging/run_with_audit.py`: run a command and append an audit log entry

If the repo keeps its own `_kano/backlog/tools` wrappers, keep arguments consistent with these scripts.

Audit logging requires running these scripts directly; do not perform ad-hoc file
operations outside the script layer when working on backlog/skill artifacts.

## State update helper

- Use `scripts/backlog/update_state.py` (or `_kano/backlog/tools/update_state.py` in the demo repo) to update state + append Worklog.
- Prefer `--action` for common transitions (`start`, `ready`, `review`, `done`, `block`, `drop`).
- When moving to Ready, it validates required sections unless `--force` is set.

