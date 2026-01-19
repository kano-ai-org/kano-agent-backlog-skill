# Changelog

All notable changes to `kano-agent-backlog-skill` will be documented in this file.

This project uses Git tags as releases: `vX.Y.Z`.

## [Unreleased]

## [0.0.2] - 2026-01-19

### Added
- Topic templates/archetypes with variable substitution and CLI integration.
- Topic cross-references (`related_topics`) with bidirectional linking.
- Topic snapshots (create/list/restore/cleanup) for checkpointing.
- Topic merge/split operations with dry-run support and history preservation.

### Changed
- Topic distillation renders human-readable seed item listings (ID/title/type/state) while keeping UID mapping in HTML comments.
- Artifact attachment resolves items in product layout (`_kano/backlog/products/<product>/items/...`) when `--backlog-root-override` is used with `--product`.

### Documentation
- Release notes for GitHub Releases: `skills/kano-agent-backlog-skill/docs/releases/0.0.2.md`.

## [0.0.1] - 2026-01-15

### Added
- Optional SQLite index layer (rebuildable) to accelerate reads and view generation.
- DBIndex vs NoDBIndex demo dashboards under `_kano/backlog/views/_demo/`.
- Demo tool for recent/iteration focus views (`_kano/backlog/tools/generate_focus_view.py`).
- First-run bootstrap (`scripts/backlog/bootstrap_init_project.py`) + templates to enable the backlog system in a repo.
- `views.auto_refresh` config flag (default: true) to keep dashboards up to date automatically.

### Documentation
- Release notes for GitHub Releases: `skills/kano-agent-backlog-skill/docs/releases/0.0.1.md`.

### Changed
- Unified generated dashboards to prefer SQLite when enabled/available and fall back to file scan.
- Kept `scripts/backlog/view_generate_demo.py` self-contained; demo repo tool is a thin wrapper.
- Mutating scripts auto-refresh dashboards by default; `scripts/fs/*` now also require `--agent` for auditability.

### Fixed
- `query_sqlite_index.py --sql` validation (SELECT/WITH detection).


### Added
- Local-first backlog structure under `_kano/backlog/` (items, decisions/ADRs, views).
- Work item scripts: create items, validate Ready gate, update state with append-only Worklog.
- Audit logging for tool invocations with redaction and rotation.
- Plain Markdown dashboards + Obsidian Dataview/Bases demo views.
- Config system under `_kano/backlog/_config/config.json`.

### Changed
- Enforced explicit `--agent` for Worklog-writing scripts and auditability.

### Security
- Secret redaction and log rotation defaults for audit logs.
