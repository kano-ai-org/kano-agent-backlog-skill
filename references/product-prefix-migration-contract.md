# Product Prefix Migration Contract

`kob config migrate-prefix` changes one registered product prefix without
changing product ownership or immutable item UIDs. Planning is the default and
is read-only.

## Plan

```bash
kob -P <product> config migrate-prefix \
  --from <current-prefix> \
  --to <new-prefix> \
  --compact
```

A ready plan contains a SHA-256 `plan_hash`, source revision, complete
item mapping, backlog-relative changed-file inventory, resolver checks,
historical-evidence policy, external update requirements, warnings, and hard
blockers. It fails closed for:

- duplicate source display IDs or UIDs;
- prefix and destination-path collisions;
- stale canonical refs that do not map to a source item;
- unparsed canonical-looking item files;
- roots outside the shared backlog;
- symlinks, scan-limit overflow, or invalid prefix grammar.

The plan snapshot covers the shared registry, every configured product item,
all product views, and every target-product artifact and metadata file. Raw
filesystem paths are never part of the public plan.

## Apply

```bash
kob -P <product> config migrate-prefix \
  --from <current-prefix> \
  --to <new-prefix> \
  --apply \
  --plan-hash <reviewed-sha256> \
  --confirm
```

Apply regenerates the plan and requires an exact hash match. It stages every
output, hashes backups and staged bytes, checks concurrent drift, publishes the
new item and reference state, retires old paths, writes a tracked migration
receipt, and runs postcondition verification. Any failure after staging
attempts an exact automatic rollback.

`--write` is a deprecated spelling of `--apply`. It does not bypass the
plan hash or confirmation gate.

## Evidence And Compatibility

Canonical frontmatter, hierarchy, relations, decisions, and readable body refs
change from the old display prefix to the new display prefix. Item UIDs remain
unchanged. A missing canonical ref remains missing, but its product prefix is
rewritten and the plan emits a `missing_reference_reprefixed` warning instead
of inventing a target item.

The following historical evidence remains byte-preserved even when its owning
path moves to the new display ID:

- `# Worklog` text;
- duplicate-admission payloads;
- artifact payloads;
- historical receipt payloads.

The tracked receipt records the old/new ID map, UIDs, source revision, plan
hash, preservation policy, and external update requirements. Local transaction
backups live below ignored `.kano/cache/prefix-migrations/<plan-hash>/`.

KOB is pre-1.0. A migration does not create an implicit legacy-prefix alias.
The old prefix fails boundedly after apply; historical evidence remains
readable through the migration receipt and immutable UID mapping. A durable
legacy alias requires a separate, explicit compatibility decision.

## Verify, Status, And Rollback

```bash
kob config migrate-prefix --verify --plan-hash <sha256>
kob config migrate-prefix --status --plan-hash <sha256>
kob config migrate-prefix --rollback --plan-hash <sha256> --confirm
```

Verify checks journal hashes, registered prefix uniqueness, new-prefix
resolution, absence of an implicit old-prefix alias, UID/display-ID mappings,
and stale canonical refs outside Worklog. Rollback restores exact pre-migration
bytes and fails closed if later edits have drifted from both recorded states.

Repo catalogs are outside KOB ownership. A ready plan reports the required
`repo_catalog:<product>:backlog_prefix=<new-prefix>` update, which must be
committed and validated in the owning integration repository.

