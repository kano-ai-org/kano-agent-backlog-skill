-- kano-agent-backlog-skill (file-first) optional DB index schema
--
-- This database is a rebuildable index/cache. Source of truth remains Markdown files under
-- _kano/backlog/products/<product>/items/**
--
-- Alignment:
-- - Core tables (schema_meta/items/links/worklog) intentionally match
--   canonical_schema.sql (ADR-0012) so we can converge on a single shared contract.
-- - This index does not currently populate chunks/chunks_fts; those belong to the
--   embedding/search pipeline.

PRAGMA foreign_keys = ON;

-- Key/value metadata for the index itself.
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Initialize schema version
INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', '0');

-- Items: Work items (Epic/Feature/Story/Task/Bug) and ADRs (canonical contract).
CREATE TABLE IF NOT EXISTS items (
  uid TEXT PRIMARY KEY,
  id TEXT NOT NULL,
  type TEXT NOT NULL,
  state TEXT NOT NULL,
  title TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  mtime REAL NOT NULL,
  content_hash TEXT,
  frontmatter TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL,
  priority TEXT,
  parent_uid TEXT,
  owner TEXT,
  area TEXT,
  iteration TEXT,
  tags TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_state ON items(state);
CREATE INDEX IF NOT EXISTS idx_items_parent_uid ON items(parent_uid);
CREATE INDEX IF NOT EXISTS idx_items_priority ON items(priority);
CREATE INDEX IF NOT EXISTS idx_items_area ON items(area);
CREATE INDEX IF NOT EXISTS idx_items_mtime ON items(mtime);
CREATE INDEX IF NOT EXISTS idx_items_id ON items(id);

-- Links: typed relationships for graph queries (aligned with canonical schema).
CREATE TABLE IF NOT EXISTS links (
  source_uid TEXT NOT NULL,
  target_uid TEXT NOT NULL,
  type TEXT NOT NULL,
  PRIMARY KEY(source_uid, target_uid, type),
  FOREIGN KEY(source_uid) REFERENCES items(uid) ON DELETE CASCADE,
  FOREIGN KEY(target_uid) REFERENCES items(uid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_uid);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_uid);
CREATE INDEX IF NOT EXISTS idx_links_type ON links(type);

-- Worklog: append-only audit trail (aligned with canonical schema per ADR-0012).
CREATE TABLE IF NOT EXISTS worklog (
  uid TEXT PRIMARY KEY,
  item_uid TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  agent TEXT NOT NULL,
  content TEXT NOT NULL,
  FOREIGN KEY(item_uid) REFERENCES items(uid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_worklog_item_uid ON worklog(item_uid);
CREATE INDEX IF NOT EXISTS idx_worklog_timestamp ON worklog(timestamp);
