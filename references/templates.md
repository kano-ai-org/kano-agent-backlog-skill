# Templates

## Work item template

Place the file under `.kano/backlog/items/<type>/`.
Use the ID prefix derived from `config/profile.env` -> `PROJECT_NAME` (example: `kano-agent-backlog-skill-demo` -> `KABSD`).

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

# Context

# Goal

# Non-Goals

# Approach

# Alternatives

# Acceptance Criteria

# Risks / Dependencies

# Worklog

2026-01-02 10:00 [agent=codex] Created from discussion: <summary>.
```

## Worklog line format

```
YYYY-MM-DD HH:MM [agent=codex] <message>
```

## ADR template

```
---
id: ADR-0001
title: "Decision title"
status: Proposed
date: 2026-01-02
related_items: []
supersedes: null
superseded_by: null
---

# Decision

# Context

# Options Considered

# Pros / Cons

# Consequences

# Follow-ups
```

