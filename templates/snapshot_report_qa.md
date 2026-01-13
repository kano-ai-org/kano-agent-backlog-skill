# QA Snapshot Report: {{scope}}

**Scope:** {{meta.scope}}
**VCS Revision:** {{meta.vcs.revision}} (dirty={{meta.vcs.dirty}}, ref={{meta.vcs.ref}}, provider={{meta.vcs.provider}}, label={{meta.vcs.label}})

## Testability & Evidence

Features that report "Done" status and their associated evidence.

{{#each capabilities}}
### {{feature}}
- **Status:** {{status}}
- **Test Evidence References:**
  {{#each evidence_refs}}
  - `{{this}}`
  {{/each}}
  {{#unless evidence_refs}}
  - _No specific evidence found._
  {{/unless}}
{{/each}}

## CLI Surface (Test Scope)
The following command structure is exposed in the CLI and requires testing:

**Root:** `{{cli_tree.[0].name}}` ({{cli_tree.[0].help}})

_(Note: Recursive tree listing would go here in fully expanded report)_

## Health Check
Environment health status:

| Check | Passed | Message |
|-------|--------|---------|
{{#each health}}
| {{name}} | {{passed}} | {{message}} |
{{/each}}
