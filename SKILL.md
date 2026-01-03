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
- Hierarchy is in frontmatter links, not folder nesting; avoid moving files to reflect scope changes.
- Filenames stay stable; use ASCII slugs.
- Never include secrets in backlog files or logs.
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

- `.kano/backlog/_meta/` (schema, conventions, config)
- `.kano/backlog/items/epics/`
- `.kano/backlog/items/features/`
- `.kano/backlog/items/userstories/`
- `.kano/backlog/items/tasks/`
- `.kano/backlog/items/bugs/`
- `.kano/backlog/decisions/` (ADR files)
- `.kano/backlog/views/` (Obsidian Dataview/DataviewJS)

## Item bucket folders (per 100)

- Store items under `.kano/backlog/items/<type>/<bucket>/`.
- Bucket names use 4 digits for the lower bound of each 100 range.
  - Example: `0000`, `0100`, `0200`, `0300`, ...
- Example path:
  - `.kano/backlog/items/tasks/0000/KABSD-TSK-0007_define-secret-provider-validation.md`

## Index/MOC files

- For Epic, create an adjacent index file:
  - `<ID>_<slug>.index.md`
- Index files should render a tree using Dataview/DataviewJS and rely on `parent` links.
- Track epic index files in `.kano/backlog/_meta/indexes.md` (type, item_id, index_file, updated, notes).

## References

- Schema and rules: `references/schema.md`
- Templates: `references/templates.md`
- Workflow SOP: `references/workflow.md`
- View patterns: `references/views.md`

If the backlog structure is missing, propose creation and wait for user approval before writing files.

## State update helper

- Use `.kano/backlog/tools/update_state.py` to update state + append Worklog.
- Prefer `--action` for common transitions (`start`, `ready`, `review`, `done`, `block`, `drop`).
- When moving to Ready, it validates required sections unless `--force` is set.

