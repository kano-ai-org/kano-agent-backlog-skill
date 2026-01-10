# Workset (Execution Cache)

Workset is a **derived, ephemeral execution cache** used while an agent is working on a Task/Bug.
It is not the source of truth: canonical work items and ADRs remain the SSOT.

## Goals

- Prevent “agent drift” during longer tasks
- Provide an execution checklist and a place to capture notes/deliverables
- Make promotion back to canonical artifacts explicit (worklog, ADRs, attachments)

## Principles

- Workset data is derived and discardable (TTL cleanup is expected)
- Git must not track workset files
- Promote load-bearing information back to canonical items/ADRs

## Directory layout

Recommended (per ADR-0011):

```text
_kano/backlog/.cache/worksets/<item-id>/
  meta.json
  plan.md
  notes.md
  deliverables/
```

Note: some scripts may default to a different cache root; use `--cache-root` to override.

## Commands

### 1) Initialize a workset

```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_init.py \
  --item <id/uid/id@uidshort> \
  --agent <agent-name> \
  [--cache-root <path>]
```

Expected outputs (under the chosen cache root):

- `meta.json`: created/refreshed timestamps, agent, source paths
- `plan.md`: checklist template
- `notes.md`: notes template (use `Decision:` markers for ADR promotion)
- `deliverables/`: files to promote

The script appends a Worklog line like `Workset initialized: ...`.

### 2) What’s next (from the plan checklist)

```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_next.py \
  --item <id/uid/id@uidshort> \
  [--cache-root <path>]
```

This reads `plan.md` and prints the next unchecked step.

### 3) Refresh from canonical

```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_refresh.py \
  --item <id/uid/id@uidshort> \
  --agent <agent-name> \
  [--cache-root <path>]
```

This updates `meta.json` and appends a Worklog line like `Workset refreshed: ...`.

### 4) Promote deliverables back to canonical

```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_promote.py \
  --item <id/uid/id@uidshort> \
  --agent <agent-name> \
  [--cache-root <path>] \
  [--dry-run]
```

This scans `deliverables/` and attaches artifacts to the work item (and appends a Worklog summary).

### 5) TTL cleanup

```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_cleanup.py \
  --agent <agent-name> \
  [--cache-root <path>] \
  [--ttl-hours <N>]
```

## ADR promotion heuristic

Use `workset_detect_adr.py` to scan `notes.md` for `Decision:` markers:

```bash
python skills/kano-agent-backlog-skill/scripts/backlog/workset_detect_adr.py --item <id>
python skills/kano-agent-backlog-skill/scripts/backlog/workset_detect_adr.py --item <id> --format json
```

When a decision is detected:

- Extract rationale into an ADR
- Link the ADR back to the item (`decisions:` frontmatter)
- Append a Worklog line (append-only)

## Git ignore

Ensure cache paths are ignored, for example:

```gitignore
_kano/**/.cache/
_kano/backlog/**/.cache/
```

## Roadmap

Workset is discussed in ADR-0011/ADR-0012 and tracked as features (e.g., execution layer + promote flows).
