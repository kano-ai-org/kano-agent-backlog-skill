# Workflow SOP

## A) Planning (discussion -> tickets)

1. Create or update Epic for the milestone.
2. Split into Features (capabilities).
3. Split into UserStories (user perspective).
4. Split into Tasks/Bugs (single focused coding sessions).
5. Fill Ready gate sections for each Task/Bug.
6. Append Worklog entry: "Created from discussion: ..." (scripts require `--agent`).

## B) Ready gate

- Move to Ready only after required sections are complete.
- No code changes until the item is Ready.

## C) Execution

1. Set state to InProgress.
2. Append Worklog for important decisions or changes.
3. If a decision is architectural, create ADR and link it:
   - Add ADR id to item `decisions: []`
   - Append Worklog entry referencing the ADR

## D) Completion

1. Move state to Review -> Done.
2. Append a Worklog summary with:
   - What changed
   - Related items and ADRs

## D.1) Parent sync (forward-only)

- When a child state changes, parents can be auto-advanced forward-only.
- Parent edits never force child states.
- Use `--no-sync-parent` if you need to keep parent state unchanged for a manual re-plan.

## E) Scope change

- Do not rewrite a ticket into a different task.
- Split into a new ticket and link via `links.relates`.
- Append a Worklog entry explaining the split.

## F) File operations

- Use `scripts/backlog/*` or `scripts/fs/*` for backlog/skill artifacts.
- Scripts only operate under `_kano/backlog/` or `_kano/backlog_sandbox/` to keep audit logs clean.
