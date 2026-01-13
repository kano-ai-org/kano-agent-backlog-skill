# Developer Snapshot Report: {{scope}}

**Scope:** {{meta.scope}}
**VCS Revision:** {{meta.vcs.revision}} (dirty={{meta.vcs.dirty}}, ref={{meta.vcs.ref}}, provider={{meta.vcs.provider}}, label={{meta.vcs.label}})

## Implementation Status (Capabilities)

This section maps backlog features to their implementation evidence.

| Feature | Status | Evidence |
|---------|--------|----------|
{{#each capabilities}}
| {{feature}} | {{status}} | {{#each evidence_refs}}<br>- `{{this}}`{{/each}} |
{{/each}}


## Technical Debt & Stubs

This section lists known incomplete implementations (TODOs, FIXMEs, NotImplementedError).

| Type | Location | Message | Ticket |
|------|----------|---------|--------|
{{#each stub_inventory}}
| {{type}} | `{{file}}:{{line}}` | {{message}} | {{ticket_ref}} |
{{/each}}

## CLI Surface

**Root Command:** {{cli_tree.[0].name}}

> [!NOTE]
> All status claims above are backed by repo evidence. `partial` status indicates presence of stubs or work-in-progress markers linked to the feature.
