-- Migration 001: Add source_path to items for SQLite index
-- Context: Earlier schema versions lacked source_path, causing ingesters and queries
-- to fail when rebuilding the derived SQLite index. This migration adds the column
-- and the supporting unique index. Multiple NULLs are permitted by SQLite unique index
-- semantics; new inserts will always set a concrete path value.

ALTER TABLE items ADD COLUMN source_path TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_source_path ON items(source_path);

INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', '1');
