---
name: kano-agent-backlog-skill
description: Local-first backlog workflow for this repo. Use when planning work, creating or updating Epics/Features/UserStories/Tasks/Bugs, writing ADRs, or enforcing the Ready gate before code changes.
metadata:
  short-description: Local backlog system
---

# Project Backlog (local-first)

## Scope

Use this skill to:
- Plan new work by creating backlog items before code changes.
- Maintain work item hierarchy via parent links as defined by the active process profile.
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
- State semantics: Proposed = needs discovery/confirmation; Planned = approved but not started; Ready gate applies before start.
- Hierarchy is in frontmatter links, not folder nesting; avoid moving files to reflect scope changes.
- Filenames stay stable; use ASCII slugs.
- Never include secrets in backlog files or logs.
- Agent Identity: In Worklog and audit logs, use your own identity (e.g., `[agent=antigravity]`), never copy `[agent=codex]` blindly.
- Worklog-writing scripts require an explicit `--agent` value; there is no default.
- **Agent Identity Protocol**: Supply `--agent <ID>` with your real product name (e.g., `cursor`, `copilot`, `windsurf`, `antigravity`).
  - **Forbidden (Placeholders)**: `auto`, `user`, `assistant`, `<AGENT_NAME>`, `$AGENT_NAME`.
- File operations for backlog/skill artifacts must go through skill scripts
  (`scripts/backlog/*` or `scripts/fs/*`) so audit logs capture the action.
  - Mutating `scripts/fs/*` operations also require `--agent` and will auto-refresh dashboards by default.
- Skill scripts only operate on paths under `_kano/backlog/` or `_kano/backlog_sandbox/`;
  refuse other paths.
- Dashboard freshness:
  - By default, mutating scripts (`workitem_create.py`, `workitem_update_state.py`, and `scripts/fs/*`) will auto-run
    `scripts/backlog/view_refresh_dashboards.py` after they change files/items.
  - Control this with `_kano/backlog/_config/config.json` -> `views.auto_refresh` (default: `true`).
  - Per-invocation override: pass `--no-refresh` to skip.
- `workitem_update_state.py` auto-syncs parent states forward-only by default; use `--no-sync-parent`
  for manual re-plans where parent state should stay put.
- Add Obsidian `[[wikilink]]` references in the body (e.g., a `## Links` section) so Graph/backlinks work; frontmatter alone does not create graph edges.

## Owner & Agent Assignment

- **Initial Owner**: When a human or agent creates a new work item, that creator becomes the initial owner (recorded in frontmatter `owner` field).
- **Owner Transfer**: If an agent (other than the initial owner) decides to work on an item, the agent should:
  1. Ask the human (user) whether to reassign ownership to the current agent.
  2. If approved, update the `owner` field to the current agent's identity (e.g., `copilot`, `cursor`, `antigravity`).
  3. Append a Worklog entry recording the reassignment: `[timestamp] [agent=<current>] Transferred ownership from <previous_owner>; beginning work.`
- **Agent Identity**: Use your real product name/identity in the owner field and Worklog entries; never use placeholders.

## First-run bootstrap (enable the backlog system)

When this skill is present but the backlog scaffold is missing (no `_kano/backlog/` or no `_kano/backlog/_config/config.json`):

1) Ask the user whether to enable the backlog system for this repo.
2) If approved, run the initializer:
   - `python scripts/backlog/bootstrap_init_project.py --agent <agent-name> --backlog-root _kano/backlog`

What it does:
- Creates `_kano/backlog/` scaffold (items/decisions/views + `_meta/indexes.md`)
- Writes baseline config to `_kano/backlog/_config/config.json` and sets `project.name`/`project.prefix`
- Refreshes canonical dashboards (`views/Dashboard_PlainMarkdown_*.md`)
- Optionally writes/updates agent guide files at repo root (templates):
  - `--write-guides create` (creates `AGENTS.md` / `CLAUDE.md` if missing, with the marked block)
  - `--write-guides append` (appends the marked block into existing files)
  - `--write-guides update` (updates the marked block if it already exists)

If the user declines, do not create any files; continue with read-only guidance.

## ID prefix derivation

- Preferred source of truth: `_kano/backlog/_config/config.json` -> `project.name` / `project.prefix`.
- Legacy fallback: `config/profile.env` -> `PROJECT_NAME`.
- Derivation:
  - Split `PROJECT_NAME` on non-alphanumeric separators and camel-case boundaries.
  - Take the first letter of each segment.
  - If only one letter, take the first letter plus the next consonant (A/E/I/O/U skipped).
  - If still short, use the first two letters.
  - Uppercase the result.
- Example: `PROJECT_NAME=kano-agent-backlog-skill-demo` -> `KABSD`.

## Recommended layout

Folder names should mirror the work item types in the active process profile.
Defaults shown below are for the built-in profiles.

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

- For top-level items (e.g., Epic in built-in profiles), create an adjacent index file:
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
- `scripts/backlog/bootstrap_init_backlog.py`: initialize `_kano/backlog` scaffold
- `scripts/backlog/bootstrap_init_project.py`: first-run bootstrap (scaffold + config + dashboards + optional guide templates)
- `scripts/backlog/workitem_create.py`: create a new backlog work item with ID + bucket (Epic can also create an index file)
- `scripts/backlog/workitem_update_state.py`: update `state` + `updated` and append Worklog
- `scripts/backlog/workitem_validate_ready.py`: check Ready gate sections
- `scripts/backlog/view_generate.py`: generate plain Markdown views
- `scripts/backlog/view_refresh_dashboards.py`: rebuild index (optional) and refresh standard dashboards
- `scripts/backlog/view_generate_demo.py`: generate DBIndex/NoDBIndex demo views
- `scripts/backlog/view_generate_tag.py`: generate tag-filtered views
- `scripts/backlog/workitem_generate_index.py`: generate item index (MOC) with task state labels (Epic/Feature/UserStory)
- `scripts/backlog/workitem_resolve_ref.py`: resolve id/uid references (with disambiguation)
- `scripts/backlog/workitem_collision_report.py`: report duplicate display IDs
- `scripts/backlog/workitem_attach_artifact.py`: copy artifacts and link them to items
- `scripts/backlog/migration_add_uid.py`: add uid fields to existing items
- `scripts/backlog/bootstrap_seed_demo.py`: seed demo items and views
- `scripts/backlog/version_show.py`: show skill version metadata
- `scripts/backlog/tests_smoke.py`: smoke tests for the backlog scripts

Filesystem scripts:
- `scripts/fs/cp_file.py`: copy a file inside the repo
- `scripts/fs/mv_file.py`: move a file inside the repo
- `scripts/fs/rm_file.py`: delete a file inside the repo
- `scripts/fs/trash_item.py`: move to trash then optionally delete

Logging scripts:
- `scripts/logging/audit_logger.py`: JSONL audit log writer + redaction
- `scripts/logging/run_with_audit.py`: run a command and append an audit log entry

Audit logging requires running these scripts directly; do not perform ad-hoc file
operations outside the script layer when working on backlog/skill artifacts.

## State update helper

- Use `scripts/backlog/workitem_update_state.py` to update state + append Worklog.
- Prefer `--action` for common transitions (`start`, `ready`, `review`, `done`, `block`, `drop`).
- When moving to Ready, it validates required sections unless `--force` is set.

