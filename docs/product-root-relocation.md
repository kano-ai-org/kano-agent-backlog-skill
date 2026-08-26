# Guarded Product Root Relocation

`kob migration relocate-product` moves one registered product root into the
canonical `products/<slug>` location of the shared backlog. It is intended for
identity-preserving convergence of an external product root, not item remapping
or cross-product migration.

## Safety Contract

- `plan` is read-only and produces a deterministic SHA-256 over the config
  revision, canonical byte manifest, item IDs/UIDs, structured-ref diagnostics,
  registry collision scan, durable sequence state, and destination path digest.
- `apply` requires both the exact reviewed `--plan-hash` and `--confirm`.
- The destination must be the registered slug's canonical shared root and must
  be absent or empty. Symlinks, prefix/identity collisions, raw filesystem
  navigation refs, active SQLite WAL/SHM files, stale config/source bytes, and
  non-empty targets fail closed.
- Canonical item, Worklog, receipt, artifact, ADR, and evidence bytes are copied
  without rewriting IDs, UIDs, history, hierarchy, or refs.
- Derived views and metadata rows are not copied as authority. The target
  product index is rebuilt from canonical files. Durable ID sequences and
  reservations are exported separately and restored into the fresh index.
- The cross-volume-safe transaction copies into a destination-volume stage,
  verifies every canonical hash, publishes the target on that volume, commits
  the config atomically, rebuilds the product index, and only then renames the
  source to a verified rollback root on the source volume.
- The source rollback root is retained. This command never deletes the source
  before config, target, identity, reference, and index postconditions pass.

Public JSON uses bounded refs such as
`product:<slug>:configured-root`,
`product:<slug>/items/...`,
`project-config:.kano/backlog_config.toml`, and
`product-cache:<slug>/index/backlog.db`. Raw absolute paths are confined to the
local recovery journal and are not emitted as navigation refs or receipts.

## Workflow

Build and review a no-write plan:

```bash
kob migration relocate-product plan \
  --product <slug> \
  --backlog-root <shared-backlog-root>
```

`--destination-root` is optional. When supplied it must resolve exactly to
`<shared-backlog-root>/products/<slug>`. Use `--expected-source-revision` to
bind an external approval or handoff to a previously observed canonical
snapshot.

Apply the exact plan:

```bash
kob migration relocate-product apply \
  --product <slug> \
  --backlog-root <shared-backlog-root> \
  --plan-hash <sha256> \
  --confirm
```

Inspect or verify one persisted transaction:

```bash
kob migration relocate-product status <sha256> \
  --backlog-root <shared-backlog-root>

kob migration relocate-product verify <sha256> \
  --backlog-root <shared-backlog-root>
```

Recover an interrupted or applied transaction:

```bash
kob migration relocate-product rollback <sha256> \
  --backlog-root <shared-backlog-root> \
  --confirm
```

Rollback refuses to remove a target with unexpected canonical files or changed
hashes. Resolve that drift explicitly instead of deleting or rebuilding the
backlog.

## Scope Boundaries

This command does not remap Display IDs or UIDs, rewrite historical Worklog
text, merge a non-empty destination, migrate multiple products, copy derived
views as authority, expose raw filesystem navigation refs, or mutate a
production product without an exact reviewed plan and confirmation.
