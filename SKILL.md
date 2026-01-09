---
name: kano-agent-backlog-skill
description: Local-first backlog workflow. Use when planning work, creating/updating backlog items, writing ADRs, enforcing Ready gate, generating views, or maintaining derived indexes (SQLite/FTS/embeddings).
metadata:
  short-description: Local backlog system
---

# Kano Agent Backlog Skill (local-first)

## Scope

Use this skill to:
- Plan new work by creating backlog items before code changes.
- Maintain hierarchy and relationships via `parent` links, as defined by the active process profile.
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
- Bug vs Task triage (when fixing behavior):
  - If you are correcting a behavior that was previously marked `Done` and the behavior violates the original intent/acceptance (defect or regression), open a **Bug** and link it to the original item.
  - If the change is a new requirement/scope change beyond the original acceptance, open a **Task/UserStory** (or Feature) instead, and link it for traceability.
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
- Skill scripts only operate on paths under `_kano/backlog/` or `_kano/backlog_sandbox/`;
  refuse other paths.
- After modifying backlog items, refresh the plain Markdown views immediately using
  `scripts/backlog/view_generate.py` so the demo dashboards stay current.
- `scripts/backlog/workitem_update_state.py` auto-syncs parent states forward-only by default; use `--no-sync-parent`
  for manual re-plans where parent state should stay put.
- Add Obsidian `[[wikilink]]` references in the body (e.g., a `## Links` section) so Graph/backlinks work; frontmatter alone does not create graph edges.

## ID prefix derivation

- Source of truth:
  - Product config: `_kano/backlog/products/<product>/_config/config.json` (`project.name`, `project.prefix`), or
  - Repo config (single-product): `_kano/backlog/_config/config.json` (`project.name`, `project.prefix`).
- Derivation:
  - Split `project.name` on non-alphanumeric separators and camel-case boundaries.
  - Take the first letter of each segment.
  - If only one letter, take the first letter plus the next consonant (A/E/I/O/U skipped).
  - If still short, use the first two letters.
  - Uppercase the result.
- Example: `project.name=kano-agent-backlog-skill-demo` -> `KABSD`.

## Recommended layout

This skill supports both single-product and multi-product layouts:

- Single-product (repo-level): `_kano/backlog/`
- Multi-product (monorepo): `_kano/backlog/products/<product>/`

Within each backlog root:
- `_meta/` (schema, conventions)
- `items/<type>/<bucket>/` (work items)
- `decisions/` (ADR files)
- `views/` (dashboards / generated Markdown)

## Item bucket folders (per 100)

- Store items under `_kano/backlog/items/<type>/<bucket>/`.
- Bucket names use 4 digits for the lower bound of each 100 range.
  - Example: `0000`, `0100`, `0200`, `0300`, ...
- Example path:
  - `_kano/backlog/items/task/0000/KABSD-TSK-0007_define-secret-provider-validation.md`

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
- Context Graph + Graph-assisted retrieval: `references/context_graph.md`

If the backlog structure is missing, propose creation and wait for user approval before writing files.

## Scripts (optional automation)

Backlog scripts:
- `scripts/backlog/bootstrap_init_backlog.py`: initialize backlog scaffold
- `scripts/backlog/bootstrap_init_project.py`: first-run bootstrap (scaffold + config + dashboards + agent guide templates)
- `scripts/backlog/process_linter.py`: validate folder scaffold against the active process profile
- `scripts/backlog/workitem_create.py`: create a new work item with ID + bucket (Epic can also create an index file)
- `scripts/backlog/workitem_update_state.py`: update `state` + `updated` and append Worklog
- `scripts/backlog/workitem_validate_ready.py`: check Ready gate sections
- `scripts/backlog/view_generate.py`: generate plain Markdown views
- `scripts/backlog/view_refresh_dashboards.py`: refresh dashboards (and rebuild index if enabled)
- `scripts/backlog/workitem_generate_index.py`: generate an index/MOC for an item (Epic/Feature/UserStory)

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
