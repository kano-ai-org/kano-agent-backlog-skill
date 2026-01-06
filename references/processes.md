# Process Profiles

Process profiles define work item types, states, and transitions for the local
backlog. They are intended to be human-readable and easy to adjust for agent
workflows.

## Suggested schema (JSON/YAML)

```json
{
  "id": "builtin/azure-boards-agile",
  "name": "Azure Boards Agile",
  "description": "Default Agile-like workflow for agent-managed backlog items.",
  "work_item_types": [
    { "type": "Epic", "slug": "epic" },
    { "type": "Feature", "slug": "feature" },
    { "type": "UserStory", "slug": "userstory" },
    { "type": "Task", "slug": "task" },
    { "type": "Bug", "slug": "bug" }
  ],
  "states": [
    "Proposed",
    "Planned",
    "Ready",
    "InProgress",
    "Review",
    "Blocked",
    "Done",
    "Dropped"
  ],
  "default_state": "Proposed",
  "terminal_states": ["Done", "Dropped"],
  "transitions": {
    "Proposed": ["Planned", "Dropped"],
    "Planned": ["Ready", "Dropped"],
    "Ready": ["InProgress", "Dropped"],
    "InProgress": ["Review", "Blocked", "Dropped"],
    "Review": ["Done", "InProgress"],
    "Blocked": ["InProgress", "Dropped"],
    "Done": [],
    "Dropped": []
  }
}
```

## Notes

- `work_item_types` should align with item frontmatter `type`.
- `states` should align with `state` values used in items.
- Keep transitions permissive for agent autonomy; tighten only if needed.

## State semantics (standard set)

These semantics apply to built-ins that use the default KABSD state set:

- Proposed: not ready to start; needs more discovery/confirmation.
- Planned: approved for the plan; detail refinement can proceed, but not started.
- Ready: Ready gate passed (typically for Task/Bug before start).
- InProgress: work started.
- Blocked: work started but blocked.
- Review: work complete pending review/verification.
- Done: work complete and accepted.
- Dropped: work intentionally stopped.

## Config selection

Use `process.profile` and `process.path` in `_kano/backlog/_config/config.json`
to choose a built-in profile or a custom file.

Use `scripts/backlog/process_linter.py` to verify item folders match the active
process profile and optionally create missing folders.

## Built-in profiles

- `references/processes/azure-boards-agile.json` -> `builtin/azure-boards-agile`
- `references/processes/scrum.json` -> `builtin/scrum`
- `references/processes/cmmi.json` -> `builtin/cmmi`
- `references/processes/jira-default.json` -> `builtin/jira-default`

## Custom profiles

Use the template as a starting point and store it under your backlog config
area (recommended: `_kano/backlog/_config/processes/`), then point
`process.path` to that file.

Template:
- `references/processes/template.json`

Example config:

```json
{
  "process": {
    "profile": null,
    "path": "_kano/backlog/_config/processes/custom.json"
  }
}
```
