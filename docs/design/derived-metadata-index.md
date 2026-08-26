# Derived metadata index

KOB keeps canonical item Markdown and frontmatter authoritative. The local
SQLite metadata index is a disposable projection used by bounded list, search,
status, and exact-item reads. A cache row never overrides canonical content.

## Contract

Each metadata row is product-scoped and records:

- display ID and UID
- product, item type, state, priority, title, and slug
- parent and duplicate references
- updated date and estimated token count
- product-relative source reference
- source size, high-resolution modification time, and content hash

Raw workspace paths are not part of the read contract. `source_ref` is
product-relative and rejects absolute paths or parent traversal.

The snapshot records independent schema versions for the row and snapshot
contracts, an inventory revision, a content revision, item count, generation,
status, and an optional invalidation reason. Inventory revision is deterministic
over sorted source refs, sizes, and modification times. Content revision is
deterministic over sorted source refs and source hashes.

## Read lifecycle

Before using rows, KOB compares the live canonical inventory with the published
snapshot.

- Exact ID or UID reads validate the matched source hash.
- List and metadata search reads validate the complete content revision.
- An exact ref absent from the index receives a bounded canonical lookup.
- Missing, incomplete, stale, schema-mismatched, or corrupt metadata falls back
  to canonical frontmatter.
- Fallback never silently omits an item solely because the index is unavailable.

Read diagnostics expose:

```text
index_used
index_status
index_revision
canonical_revision
fallback_scan
scanned_count
matched_count
revision_check_ms
elapsed_ms
stale_reason
recovery
```

Ordinary item listing remains stable. Pass `--index-diagnostics` to emit the
diagnostic object on stderr.

## Mutation lifecycle

Canonical writes happen first. Successful create, state, Ready-field, reparent,
relation, worklog, decision, and artifact mutations then update the affected
derived row. Tracked deletion removes its row. Batch schema repair rebuilds the
product snapshot once after canonical writes finish.

An incremental row update keeps a previously verified snapshot ready. If no
verified snapshot exists, the projection remains `incomplete` until a rebuild.
This prevents a partial producer run from becoming an authoritative read source.

Rebuild publication runs in one SQLite transaction: product rows are replaced,
revisions are computed from the staged rows, and the ready snapshot is published
with them. A failed transaction rolls back.

## Operations

```bash
kob -P <product> index build --force --format json
kob -P <product> index refresh --format json
kob -P <product> index status --format json
kob -P <product> index query --item <ID-or-UID> --format json
kob -P <product> index doctor --format json
```

`build` and `refresh` both perform an atomic canonical rebuild. `doctor` verifies
row parity and source hashes. The recovery value in stale diagnostics points to
the product-scoped rebuild command.

The metadata rows and snapshots are disposable. The current SQLite container
also preserves ID sequence and reservation tables, so operators should use
`kob index build` instead of deleting the database file. Metadata schema
reconciliation replaces only derived tables and leaves sequence state intact.

## Performance evidence

`metadata_index_smoke_test` creates more than 600 canonical items and enforces:

- exact lookup p95 below 100 ms
- metadata query p95 below 500 ms
- bounded token query p95 below 2 seconds
- canonical revision check p95 below 100 ms

The fixture also covers cold startup, explicit invalidation, tracked and
out-of-band mutations, create/reparent/state/decision lifecycle, deletion,
incomplete and corrupt databases, source-hash drift, and shared-database product
isolation.

## Boundaries

- The index is not canonical storage.
- It is not a semantic or vector index.
- It does not replace product or prefix resolution.
- It does not expose raw filesystem paths.
- Cache failure must not block local-first canonical reads.
