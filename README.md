# kano-agent-backlog-skill

**Local-first backlog + decision trail for agent collaboration.**  
Turn chat-only context (trade-offs, decisions, why-not-that-option) into durable engineering assets, so your agent writes code only after capturing **what to do, why, and how to verify**.

> Code can be rewritten. Lost decisions can’t.

## What this is

`kano-agent-backlog-skill` is an **Agent Skill bundle** (centered around `SKILL.md`) that guides/constrains an agent into a “tickets first” workflow:

- Create/update a work item (Epic/Feature/UserStory/Task/Bug) before any code change
- Capture key decisions via append-only Worklog entries or ADRs, and link them together
- Enforce a Ready gate so each item has the minimum shippable context (Context/Goal/Approach/Acceptance/Risks)
- Optional Obsidian views (Dataview / Bases) so humans can inspect, intervene, and review

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
- `references/views.md`: Obsidian view patterns (Dataview + Bases)
- `scripts/kano`: Typer-based CLI entrypoint with subcommands:
  - `item` - Create and manage work items (Epic/Feature/UserStory/Task/Bug)
  - `item update-state` - Transition item states with worklog tracking
  - `worklog` - Append worklog entries
  - `adr` - Create and manage Architecture Decision Records
  - `workset` - Per-item execution cache (init/refresh/next/promote/cleanup/detect-adr)
  - `topic` - Context grouping and switching (create/add/pin/switch/export-context/list)
  - `view` - Generate dashboards and reports
  - `backlog` - Initialize and manage backlog structure
  - `doctor` - Validate backlog health
- `src/kano_backlog_core`: canonical models/storage helpers
- `src/kano_backlog_ops`: use-cases (create/update/view/workset/topic)
- `src/kano_backlog_cli`: CLI wiring (commands + utilities)

Note: backlog administration commands are grouped under `kano backlog ...` (init/validate/demo).

Optionally, create `_kano/backlog/` in your project repo to store items, ADRs, views, and helper scripts as the system of record.

## Quick start (see value in ~5 minutes)

1) Run `python skills/kano-agent-backlog-skill/scripts/kano backlog init --product <my-product> --agent <id>` to scaffold `_kano/backlog/products/<my-product>/`
2) (Optional) Open the repo in Obsidian and enable Dataview or Bases
3) Open `_kano/backlog/products/<my-product>/views/` (or regenerate them with `python skills/kano-agent-backlog-skill/scripts/kano view refresh --agent <id> --product <my-product>`)
4) Before any code change, create a Task/Bug and satisfy the Ready gate
5) When a load-bearing decision happens, append a Worklog line; create an ADR when it's truly architectural and link it

## Workset and Topic Usage

### Worksets: Focused Execution

Worksets prevent agent drift during task execution by providing a structured working context:

```bash
# Initialize workset for a task
kano workset init --item TASK-0042 --agent kiro

# Get next action from plan
kano workset next --item TASK-0042

# Detect decisions that should become ADRs
kano workset detect-adr --item TASK-0042

# Promote deliverables to canonical artifacts
kano workset promote --item TASK-0042 --agent kiro

# Clean up expired worksets
kano workset cleanup --ttl-hours 72
```

See [docs/workset.md](docs/workset.md) for complete documentation.

### Topics: Context Switching

Topics enable rapid context switching when focus areas change.

Unlike worksets (which live entirely under `_kano/backlog/.cache/worksets/items/<item-id>/`), topics are stored under `_kano/backlog/topics/<topic>/` so the deterministic `brief.md` can be shared/reviewed. Raw materials under `materials/` are treated as cache.

```bash
# Create a topic for related work
kano topic create auth-refactor --agent kiro

# Add items to the topic
kano topic add auth-refactor --item TASK-0042
kano topic add auth-refactor --item BUG-0012

# Pin relevant documents
kano topic pin auth-refactor --doc _kano/backlog/decisions/ADR-0015.md

# Collect a code snippet reference (optional cached snapshot)
kano topic add-snippet auth-refactor --file src/auth.py --start 10 --end 25 --agent kiro --snapshot

# Distill deterministic brief.md from collected materials
kano topic distill auth-refactor

# Switch active topic (per-agent pointer lives in cache)
kano topic switch auth-refactor --agent kiro

# Export context bundle
kano topic export-context auth-refactor --format json

# Close and later cleanup closed topics
kano topic close auth-refactor --agent kiro
kano topic cleanup --ttl-days 14
kano topic cleanup --ttl-days 14 --apply
```

See [docs/topic.md](docs/topic.md) for complete documentation.
5) When a load-bearing decision happens, append a Worklog line; create an ADR when it’s truly architectural and link it

## Skill version

Show the current skill version:

```bash
python -c "import pathlib; print((pathlib.Path('skills/kano-agent-backlog-skill') / 'VERSION').read_text().strip())"
```

## External references

- Agent skills overview (Anthropic/Claude): https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Versioning policy: `VERSIONING.md`
- Release notes: `CHANGELOG.md`

## Contributing

PRs welcome, with one rule: **don’t turn this into another Jira.**  
The point is to preserve decisions and acceptance, not to worship process.

## License

MIT
