# Backlog Schema

## Item types

- Epic
- Feature
- UserStory
- Task
- Bug

## Parent rules

- Epic -> Feature
- Feature -> UserStory
- UserStory -> Task or Bug
- Feature -> Bug (allowed)
- Task -> Task (optional sub-task)
- Epic has no parent

## States

- Proposed
- Planned
- Ready
- InProgress
- Blocked
- Review
- Done
- Dropped

## Ready gate (required, non-empty)

To move to Ready, each item must include:
- Context
- Goal
- Approach
- Acceptance Criteria
- Risks / Dependencies

## File naming

- `<ID>_<slug>.md`
- Slug: ASCII, hyphen-separated
- ID prefixes:
  - `KABSD-EPIC-`
  - `KABSD-FTR-`
  - `KABSD-USR-`
  - `KABSD-TSK-`
  - `KABSD-BUG-`
- Prefix derivation:
  - Source: `config/profile.env` -> `PROJECT_NAME`.
  - Split on non-alphanumeric separators and camel-case boundaries, take first letters.
  - If only one letter, use the first letter plus the next consonant (A/E/I/O/U skipped).
  - If still short, use the first two letters.
  - Uppercase the result (example: `kano-agent-backlog-skill-demo` -> `KABSD`).
- Store files under `.kano/backlog/items/<type>/<bucket>/` by item type.
- Bucket names use the lower bound of each 100 range:
  - `0000`, `0100`, `0200`, ...
- For Epic, create `<ID>_<slug>.index.md` in the same folder.

## Frontmatter (minimum)

```
---
id: KABSD-TSK-0001
type: Task
title: "Short title"
state: Proposed
priority: P2
parent: KABSD-USR-0001
area: general
iteration: null
tags: []
created: 2026-01-02
updated: 2026-01-02
owner: null
external:
  azure_id: null
  jira_key: null
links:
  relates: []
  blocks: []
  blocked_by: []
decisions: []
---
```

## Immutable fields

- `id`, `type`, `created` must not be changed after creation.

