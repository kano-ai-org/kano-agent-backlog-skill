-- kano-agent-backlog-skill (file-first) optional DB index schema
--
-- This database is a rebuildable index/cache. Source of truth remains Markdown files under:
--   _kano/backlog/items/** and _kano/backlog/decisions/**
--
-- Notes:
-- - Keep schema compatible with SQLite; Postgres can map with minor type tweaks.
-- - Store raw frontmatter as JSON text to preserve unknown fields.
-- - Worklog is append-only in source; we index parsed entries for querying.

PRAGMA foreign_keys = ON;

-- Key/value metadata for the index itself.
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Initialize schema version to 0 (baseline; migrations will upgrade)
INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', '0');

-- Backlog items (Epic/Feature/UserStory/Task/Bug, plus any process-defined types).
CREATE TABLE IF NOT EXISTS items (
  id TEXT NOT NULL,
  product TEXT NOT NULL,
  uid TEXT,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  state TEXT,
  priority TEXT,
  parent_id TEXT,
  area TEXT,
  iteration TEXT,
  owner TEXT,
  created TEXT,
  updated TEXT,
  source_path TEXT NOT NULL,
  content_sha256 TEXT,
  frontmatter_json TEXT NOT NULL,
  PRIMARY KEY(product, id),
  UNIQUE(source_path)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_items_source_path ON items(source_path);
CREATE INDEX IF NOT EXISTS idx_items_product ON items(product);
CREATE INDEX IF NOT EXISTS idx_items_parent_id ON items(parent_id);
CREATE INDEX IF NOT EXISTS idx_items_state ON items(state);
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_product_id ON items(product, id);

-- Tags: normalized for simple filtering/grouping.
CREATE TABLE IF NOT EXISTS item_tags (
  product TEXT NOT NULL,
  item_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY(product, item_id, tag),
  FOREIGN KEY(product, item_id) REFERENCES items(product, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag);

-- Links: includes parent edges (optional) and link relations from frontmatter `links.*`.
CREATE TABLE IF NOT EXISTS item_links (
  product TEXT NOT NULL,
  item_id TEXT NOT NULL,
  relation TEXT NOT NULL, -- e.g. relates, blocks, blocked_by, parent, external
  target TEXT NOT NULL,   -- item id or external key/url
  target_uid TEXT,        -- canonical UID when resolvable (nullable)
  PRIMARY KEY(product, item_id, relation, target),
  FOREIGN KEY(product, item_id) REFERENCES items(product, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_item_links_relation ON item_links(relation);
CREATE INDEX IF NOT EXISTS idx_item_links_target ON item_links(target);
CREATE INDEX IF NOT EXISTS idx_item_links_target_uid ON item_links(target_uid);

-- Decisions/ADRs: we store decision references (links) from item frontmatter.
-- The decision_ref can be a wiki-link target, filename, or URL.
CREATE TABLE IF NOT EXISTS item_decisions (
  product TEXT NOT NULL,
  item_id TEXT NOT NULL,
  decision_ref TEXT NOT NULL,
  PRIMARY KEY(product, item_id, decision_ref),
  FOREIGN KEY(product, item_id) REFERENCES items(product, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_item_decisions_ref ON item_decisions(decision_ref);

-- Worklog entries: parsed from the markdown Worklog section.
CREATE TABLE IF NOT EXISTS worklog_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT NOT NULL,
  item_id TEXT NOT NULL,
  occurred_at TEXT, -- best-effort timestamp (if parseable)
  agent TEXT,
  message TEXT NOT NULL,
  raw_line TEXT NOT NULL,
  FOREIGN KEY(product, item_id) REFERENCES items(product, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_worklog_entries_item_id ON worklog_entries(item_id);
CREATE INDEX IF NOT EXISTS idx_worklog_entries_occurred_at ON worklog_entries(occurred_at);
CREATE INDEX IF NOT EXISTS idx_worklog_entries_agent ON worklog_entries(agent);

