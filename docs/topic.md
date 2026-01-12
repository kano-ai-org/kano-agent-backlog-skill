# Topic (Context Grouping)

Topics provide a **higher-level grouping mechanism** for rapid context switching when users change focus areas during a conversation. While worksets are per-item execution caches, topics group multiple items and documents into a coherent context bundle.

## Goals

- Enable rapid context switching between focus areas
- Group related items and documents for coherent context loading
- Support multi-item work sessions without losing context
- Provide deterministic context export for agent consumption

## Principles

- Topics are derived and ephemeral (like worksets)
- One active topic per agent at a time
- Topics reference items by UID (not copies)
- Pinned documents provide additional context beyond items

## Directory Layout

```text
_kano/backlog/.cache/worksets/topics/<topic-name>/
  manifest.json   # Topic metadata: seed_items, pinned_docs, timestamps
  notes.md        # Optional topic-level notes

_kano/backlog/.cache/worksets/
  active_topic.<agent>.txt   # Current active topic for agent
```

### Manifest Structure

```json
{
  "topic": "auth-refactor",
  "agent": "kiro",
  "seed_items": ["TASK-0042", "TASK-0043", "BUG-0012"],
  "pinned_docs": ["_kano/backlog/decisions/ADR-0015.md"],
  "created_at": "2026-01-12T10:00:00Z",
  "updated_at": "2026-01-12T14:30:00Z"
}
```

## CLI Commands

All topic commands are accessed via `kano topic <subcommand>`.

### Create a Topic

```bash
kano topic create <topic-name> --agent <agent-name> [--no-notes] [--format plain|json]
```

Creates a new topic:
- Validates topic name (alphanumeric, hyphens, underscores)
- Creates `manifest.json` with empty seed_items and pinned_docs
- Optionally creates `notes.md` (use `--no-notes` to skip)

### Add Items to Topic

```bash
kano topic add <topic-name> --item <id> [--format plain|json]
```

Adds a backlog item to the topic:
- Verifies item exists in backlog
- Adds item UID to `seed_items` array
- Skips if item already in topic (idempotent)
- Updates `updated_at` timestamp

### Pin Documents

```bash
kano topic pin <topic-name> --doc <path> [--format plain|json]
```

Pins a document to the topic:
- Verifies document exists
- Adds path to `pinned_docs` array
- Skips if already pinned (idempotent)
- Supports relative paths from workspace root

### Switch Active Topic

```bash
kano topic switch <topic-name> --agent <agent-name> [--format plain|json]
```

Switches the active topic for an agent:
- Updates `active_topic.<agent>.txt`
- Returns summary (item count, pinned doc count)
- Shows previous topic if any

### Export Context Bundle

```bash
kano topic export-context <topic-name> [--format markdown|json]
```

Exports topic context as a bundle:
- Loads summaries of all seed items (title, state, type)
- Includes content from pinned documents
- Output is deterministic (sorted, consistent formatting)
- Use `--format json` for machine parsing

### List Topics

```bash
kano topic list [--agent <agent-name>] [--format plain|json]
```

Lists all topics:
- Shows item count and pinned doc count
- Marks active topic (if `--agent` specified)
- Shows last updated timestamp

## Common Workflows

### Setting Up a Focus Area

```bash
# 1. Create topic for your work area
kano topic create auth-refactor --agent kiro

# 2. Add related items
kano topic add auth-refactor --item TASK-0042
kano topic add auth-refactor --item TASK-0043
kano topic add auth-refactor --item BUG-0012

# 3. Pin relevant documents
kano topic pin auth-refactor --doc _kano/backlog/decisions/ADR-0015.md
kano topic pin auth-refactor --doc docs/auth-design.md

# 4. Switch to the topic
kano topic switch auth-refactor --agent kiro
```

### Context Switching

```bash
# Check current topics
kano topic list --agent kiro

# Switch to different focus area
kano topic switch payment-flow --agent kiro

# Export context for agent consumption
kano topic export-context payment-flow --format json
```

### Loading Context into Agent

```bash
# Export as markdown for human review
kano topic export-context auth-refactor

# Export as JSON for programmatic use
kano topic export-context auth-refactor --format json
```

## Integration with Worksets

Topics and worksets work together:

1. **Topic**: Groups related items for context switching
2. **Workset**: Per-item execution cache for focused work

Typical flow:
```bash
# Switch to topic
kano topic switch auth-refactor --agent kiro

# Initialize workset for specific item
kano workset init --item TASK-0042 --agent kiro

# Work on item with workset
kano workset next --item TASK-0042

# When done, switch topic or continue with next item
```

## Git Ignore

Topics are stored in the cache directory, which should be ignored:

```gitignore
_kano/**/.cache/
_kano/backlog/**/.cache/
```

## Related

- [Workset](workset.md) - Per-item execution cache
- ADR-0011: Workset vs GraphRAG separation
