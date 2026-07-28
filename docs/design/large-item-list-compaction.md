# Reversible Large Item List Compaction

`kob workitem list` remains the canonical, complete list surface. Its default
plain output, filtering behavior, ordering, and state or dependency semantics do
not change.

Large-list compaction is an explicit read-only projection:

```bash
kob workitem list --compact
kob workitem list --compact --format json
```

The compact response has navigation authority only. It never writes item files,
changes item state, rewrites links, or changes the canonical list order.

## Canonical input and order

KOB reads item metadata from canonical Markdown files, not from a potentially
stale SQLite row or a Backboard response. Topic membership is joined from exact
item ID or UID references in `topics/*/manifest.json`.

Both canonical JSON and compact JSON retain this order:

1. `updated` descending
2. display ID ascending

Every shown item carries its one-based `canonical_position`.

## Collapse policy

The default recent window is 30 days, anchored to the newest valid canonical
`updated` date. The resulting cutoff is embedded in every dated compact group
ID. This makes a group selector replayable even if a newer item is added later.

Only items satisfying all of these conditions may be omitted:

- state is `Done`
- `updated` is valid and before the embedded cutoff
- `blocks` is empty
- `blocked_by` is empty

`Ready`, `Review`, and `Blocked` items are always shown. Items with unknown or
invalid dates fail open and remain shown. Hierarchy (`parent`), dependencies
(`blocks` and `blocked_by`), and non-dependency relations (`relates`) remain
separate response fields.

Group identity includes state, type, priority, the complete sorted topic set,
and an explicit updated selector. Topic sets use `topics:<count>:<encoded-set>`;
an empty set is `topics:0`. Topic spelling and case are preserved so an empty
set cannot collide with literal topics such as `none` or `None`. Priorities use
the same injective presence convention: an absent priority is `priority:0`,
while a present value is `priority:1:<encoded-value>`. Case is preserved and a
present empty value is explicitly represented by `priority:1:`. For example:

```text
state:done/type:task/priority:1:P2/topics:0/updated:before-2026-06-28
```

## Reversible retrieval

Any retrieval selector expands all matching items:

```bash
kob workitem list --compact --item KOB-TSK-0104 --format json
kob workitem list --compact --state Done --format json
kob workitem list --compact --topic operator-routing --format json
kob workitem list --compact \
  --group 'state:done/type:task/priority:1:P2/topics:0/updated:before-2026-06-28' \
  --format json
```

Topic matching uses exact manifest membership. Exact item matching accepts a
display ID or UID; an ambiguous display ID fails closed and requires a UID.
Unknown compact groups and invalid type or state selectors also fail closed.

Retrieval is evaluated against current canonical item state. The embedded group
cutoff is replayed, while later canonical state, link, or topic changes remain
authoritative. Replay responses declare `cutoff_source: group_selector`,
`recent_days: null`, and the exact `replay_cutoff`; they do not claim that the
cutoff was recomputed from the current newest item.

## JSON boundary

Canonical JSON uses `kob.workitem.list.v1`. Compact JSON uses
`kob.workitem.list.compact.v1` and declares:

- canonical product slug
- `authority: navigation_only`
- `mutates_backlog: false`
- `retrieval_consistency: current_canonical_state`
- canonical ordering
- recency anchor and embedded cutoff
- protected-state and dependency safety rules
- shown and omitted counts
- versioned item and group projections

The JSON response exposes structured retrieval descriptors with
`operation`, `product`, and selector objects. It does not publish shell commands
or raw argv. A caller such as KOA may translate those descriptors at its own
response boundary without becoming the canonical list owner.
