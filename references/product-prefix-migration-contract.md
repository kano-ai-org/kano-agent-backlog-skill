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
  --confirm \
  --agent <audit-actor>
```

Apply regenerates the plan and requires an exact hash match. It stages every
output, hashes backups and staged bytes, checks concurrent drift, publishes the
new item and reference state, retires old paths, writes a tracked migration
receipt, and runs postcondition verification. Any failure after staging
attempts an exact automatic rollback.

`--agent` is required for every apply mutation. The core API enforces the same
requirement, validates the actor before transaction or backlog writes, and
rejects empty, malformed, or placeholder identities. Attribution is explicit;
there is no environment, wrapper, or default actor.

`--write` is a deprecated spelling of `--apply`. It does not bypass the actor,
plan hash, or confirmation gate.

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
hash, validated `apply_agent`, preservation policy, and external update
requirements. Local transaction backups live below ignored
`.kano/cache/prefix-migrations/<plan-hash>/`.

Planning remains `kob.product_prefix_migration.plan.v2`. Actors are execution
provenance and are never added to `PrefixMigrationRequest`, plan JSON, or the
plan-hash preimage, so previously reviewed plan hashes remain stable. New
result, verification, status, rollback, receipt, and journal evidence is v3.
Readers continue to accept legacy v2 journals and receipts; their missing
`apply_agent` is exposed as `null`, not inferred or backfilled. Idempotent replay
returns the original persisted provenance and never rewrites either evidence
file. Verification requires matching, valid receipt and journal `apply_agent`
values for v3 evidence while accepting actorless v2 evidence.

Recovery readers bind the requested hash to the journal hash and embedded-plan
hash, then bind the receipt path, receipt operation hash, complete receipt
identity, plan identity, and v3 apply actor. Every journal operation path must
remain below the shared backlog, every backup path below the transaction
`backup/` directory, and every stage path below `stage/`; malformed or escaping
paths are rejected before recovery reads or writes. Containment resolves
existing symlinks and the nearest existing ancestor of not-yet-created targets,
so lexical in-root paths cannot redirect outside their assigned root. Every
recoverable state validates the staged receipt path, hash, and identity before
rollback I/O; `applied` additionally requires the canonical receipt. Missing,
drifted, or identity-mismatched receipts fail verification, status, replay, and
rollback closed.

KOB is pre-1.0. A migration does not create an implicit legacy-prefix alias.
The old prefix fails boundedly after apply; historical evidence remains
readable through the migration receipt and immutable UID mapping. A durable
legacy alias requires a separate, explicit compatibility decision.

## Verify, Status, And Rollback

```bash
kob config migrate-prefix --verify --plan-hash <sha256>
kob config migrate-prefix --status --plan-hash <sha256>
kob config migrate-prefix --rollback --plan-hash <sha256> --confirm \
  --agent <audit-actor>
```

Verify checks journal hashes, registered prefix uniqueness, new-prefix
resolution, absence of an implicit old-prefix alias, UID/display-ID mappings,
and stale canonical refs outside Worklog. Rollback restores exact pre-migration
bytes and fails closed if later edits have drifted from both recorded states.
Verify and status do not require an actor; supplying `--agent` to plan, verify,
or status is rejected rather than ignored. Manual rollback requires a validated
actor and records `rollback_agent`, `rollback_mode=manual`, and a timestamp.
Automatic rollback reuses the validated apply actor and records
`rollback_mode=automatic`. Provenance fields in verification, status, and
rollback output are nullable for compatible v2 evidence.

Before restoration starts, rollback persists `status=recovery_required`, the
validated `rollback_agent`, `rollback_mode`, and `rollback_attempted_at`.
Each restore appends an `in_progress` entry to `rollback_attempts[]`, then marks
that same entry `failed` with a bounded error and timestamp or `completed` with
a completion timestamp. Top-level rollback fields mirror the latest attempt;
retries append rather than overwrite prior actors or modes. `rolled_back_at` is
written only after every operation reaches its recorded before-state. Drift,
partial restoration, or an exception preserves already-restored path evidence
and leaves `recovery_required` retryable. V3 recovery states require complete,
state-appropriate attempt provenance. Old v2 evidence without attempts remains
readable, and a new manual rollback may append attempts without upgrading its
schema or inventing an apply actor. A core `failed` status is also a nonzero CLI
result; evidence-update failures are surfaced rather than swallowed.

Repo catalogs are outside KOB ownership. A ready plan reports the required
`repo_catalog:<product>:backlog_prefix=<new-prefix>` update, which must be
committed and validated in the owning integration repository.
