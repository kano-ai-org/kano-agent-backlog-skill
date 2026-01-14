# Product Manager Snapshot Report: {{scope}}

**Scope:** {{meta.scope}}
**VCS:** branch={{meta.vcs.branch}}, revno={{meta.vcs.revno}}, hash={{meta.vcs.hash}}, dirty={{meta.vcs.dirty}}, provider={{meta.vcs.provider}}

## Feature Delivery Status

Overview of feature implementation based on repository evidence.

### Done / In Review
{{#each capabilities}}
  {{#if (eq status "done")}}
- [x] **{{feature}}**
  - _Evidence:_ {{#each evidence_refs}}{{this}}; {{/each}}
  {{/if}}
{{/each}}


### In Progress / Partial
{{#each capabilities}}
  {{#if (eq status "partial")}}
- [/] **{{feature}}**
  - _Status:_ Partial / In Progress
  - _Evidence:_ {{#each evidence_refs}}{{this}}; {{/each}}
  {{/if}}
{{/each}}


### Not Started / Missing
{{#each capabilities}}
  {{#if (eq status "missing")}}
- [ ] **{{feature}}**
  {{/if}}
{{/each}}

## Known Risks (Stubs)
The following items have explicit code markers indicating incomplete work:

{{#each stub_inventory}}
- **{{type}}** in `{{file}}`: "{{message}}" {{#if ticket_ref}}(Ticket: {{ticket_ref}}){{/if}}
{{/each}}
