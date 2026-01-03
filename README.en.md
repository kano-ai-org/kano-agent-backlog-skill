# kano-agent-backlog-skill

**Local-first backlog + decision trail for agent collaboration.**  
Turn “chat-only context” (trade-offs, decisions, why-not-that-option) into durable engineering assets, so your agent writes code only after capturing **what to do, why, and how to verify**.

> Code can be rewritten. Lost decisions can’t.

Chinese version: `README.md`

## What this is

`kano-agent-backlog-skill` is an **Agent Skill bundle** (centered around `SKILL.md`) that guides/constrains an agent into a “tickets first” workflow:

- Create/update a work item (Epic/Feature/UserStory/Task/Bug) before any code change
- Capture key decisions via append-only Worklog entries or ADRs, and link them together
- Enforce a Ready gate so each item has the minimum shippable context (Context/Goal/Approach/Acceptance/Risks)
- Optional Obsidian + Dataview views so humans can inspect, intervene, and review

This skill is **local-first**: you can start without Jira / Azure Boards and still keep engineering discipline.

## Why you might want it

If any of these sound familiar, this helps:

- You made an architecture choice, but later forgot *why you didn’t pick the other option*
- The agent output works, but maintenance feels like archaeology (missing rationale and constraints)
- Requirement changes force you back into chat history to understand impact
- You want the agent as a teammate, but you end up acting as the “human memory cache”

Goal: convert “evaporating context” into **searchable, linkable, auditable** files in your repo.

## What you get (implemented)

- `SKILL.md`: the workflow and rules (planning-before-coding, Ready gate, worklog discipline)
- `references/schema.md`: item types, states, naming, minimal frontmatter
- `references/templates.md`: work item / ADR templates
- `references/workflow.md`: SOP (when to create items, when to record decisions, how to converge)
- `references/views.md`: Obsidian Dataview query/view patterns

Optionally, create `.kano/backlog/` in your project repo to store items, ADRs, views, and helper scripts as the system-of-record.

## Quick start (see value in ~5 minutes)

1) Add a backlog folder to your repo (recommended): `.kano/backlog/`
2) (Optional) Open the repo in Obsidian and enable the Dataview plugin
3) Open `.kano/backlog/views/Dashboard.md` or build your own views from `references/views.md`
4) Before any code change, have the agent create a Task/Bug using `references/templates.md` and satisfy the Ready gate
5) When a load-bearing decision happens, append a Worklog line; create an ADR when it’s truly architectural and link it

## Recommended backlog structure (in your project)

```text
.kano/backlog/
  _meta/                 # schema, conventions, index registry
  items/
    epics/<bucket>/
    features/<bucket>/
    userstories/<bucket>/
    tasks/<bucket>/
    bugs/<bucket>/
  decisions/             # ADRs
  views/                 # Obsidian Dataview dashboards / generated views
  tools/                 # optional helper scripts (state transition, view generation)
```

Buckets are per-100 (`0000`, `0100`, `0200`, ...) to avoid huge folders.

## What this repo contains (source of truth)

- Agent rules: `SKILL.md`
- References: `references/`

If you’re looking for a working `.kano/backlog` example, use the demo host repo (or treat `references/templates.md` as your initialization input).

## Roadmap (direction, not promises)

- Reusable `.kano/backlog` bootstrap assets (templates + tools) for one-command initialization
- Minimal Jira/Azure Boards linking (sync only a few fields to avoid two-way-sync hell)
- A lightweight Ready gate validator while staying local-first

## Contributing

PRs welcome, with one rule: **don’t turn this into another Jira.**  
The point is to preserve decisions and acceptance, not to worship process.

## License

Not specified yet (TBD).

