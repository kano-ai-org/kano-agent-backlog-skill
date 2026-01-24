-- Canonical Schema for Kano Backlog System
-- ============================================
--
-- This schema defines the canonical data model for the Kano backlog system.
-- It is used by:
-- 1. Repo-level derived index (SQLite at _kano/backlog/_index/backlog.sqlite3)
-- 2. Workset DBs (per-agent/per-task materialized cache bundles)
--
-- Per ADR-0012, workset DBs MUST reuse this schema (no parallel schema allowed).
-- Worksets may add workset-specific tables (prefixed with "workset_") but MUST NOT
-- modify core table definitions.
--
-- Schema version: 0 (base schema)
-- Related: ADR-0004, ADR-0008, ADR-0012
-- Last updated: 2026-01-09

-- Schema metadata (version tracking per ADR-0008)
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Initialize schema version
INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', '0');

-- ============================================
-- Core Entities
-- ============================================

-- Items: Work items (Epic/Feature/Story/Task/Bug) and ADRs
CREATE TABLE IF NOT EXISTS items (
  uid TEXT PRIMARY KEY,              -- UUIDv7 (globally unique, from frontmatter)
  id TEXT NOT NULL,                  -- Display ID (e.g., KABSD-TSK-0049)
  type TEXT NOT NULL,                -- Work item type: Epic, Feature, UserStory, Task, Bug, ADR
  state TEXT NOT NULL,               -- Current state: Proposed, Planned, Ready, InProgress, Blocked, Review, Done, Dropped
  title TEXT NOT NULL,               -- Item title
  path TEXT NOT NULL UNIQUE,         -- Relative path to canonical file
  mtime REAL NOT NULL,               -- File modification timestamp (Unix epoch)
  content_hash TEXT,                 -- Hash of content (for change detection)
  frontmatter TEXT,                  -- Full frontmatter blob (JSON)
  created TEXT NOT NULL,             -- Creation date (ISO 8601)
  updated TEXT NOT NULL,             -- Last updated date (ISO 8601)
  priority TEXT,                     -- Priority: P1, P2, P3, P4
  parent_uid TEXT,                   -- UID of parent item (null if root)
  owner TEXT,                        -- Current owner/assignee
  area TEXT,                         -- Functional area
  iteration TEXT,                    -- Iteration/sprint identifier
  tags TEXT                          -- Array of tags (JSON)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_state ON items(state);
CREATE INDEX IF NOT EXISTS idx_items_parent_uid ON items(parent_uid);
CREATE INDEX IF NOT EXISTS idx_items_priority ON items(priority);
CREATE INDEX IF NOT EXISTS idx_items_area ON items(area);
CREATE INDEX IF NOT EXISTS idx_items_mtime ON items(mtime);
CREATE INDEX IF NOT EXISTS idx_items_id ON items(id);

-- Links: Typed relationships for graph queries
CREATE TABLE IF NOT EXISTS links (
  source_uid TEXT NOT NULL,          -- Link source (referencing item)
  target_uid TEXT NOT NULL,          -- Link target (referenced item)
  type TEXT NOT NULL,                -- Link type: parent, relates_to, blocks, blocked_by, decision_ref
  PRIMARY KEY (source_uid, target_uid, type),
  FOREIGN KEY (source_uid) REFERENCES items(uid) ON DELETE CASCADE,
  FOREIGN KEY (target_uid) REFERENCES items(uid) ON DELETE CASCADE
);

-- Indexes for graph traversal
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_uid);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_uid);
CREATE INDEX IF NOT EXISTS idx_links_type ON links(type);

-- Worklog: Append-only audit trail for work items
CREATE TABLE IF NOT EXISTS worklog (
  uid TEXT PRIMARY KEY,              -- Unique worklog entry ID (UUIDv7)
  item_uid TEXT NOT NULL,            -- UID of parent item
  timestamp TEXT NOT NULL,           -- ISO 8601 timestamp
  agent TEXT NOT NULL,               -- Agent/user who created entry
  content TEXT NOT NULL,             -- Worklog entry text
  FOREIGN KEY (item_uid) REFERENCES items(uid) ON DELETE CASCADE
);

-- Index for worklog queries
CREATE INDEX IF NOT EXISTS idx_worklog_item_uid ON worklog(item_uid);
CREATE INDEX IF NOT EXISTS idx_worklog_timestamp ON worklog(timestamp);

-- Chunks: Content chunks for semantic search and FTS
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,         -- Unique chunk identifier (UUIDv7 or <item_uid>_<index>)
  parent_uid TEXT NOT NULL,          -- UID of parent item
  chunk_index INTEGER NOT NULL,      -- Sequence number within parent (0-based)
  content TEXT NOT NULL,             -- Chunk text content
  section TEXT,                      -- Section type: Context, Goal, Approach, Acceptance Criteria, etc.
  embedding BLOB,                    -- Float32 vector array (optional, for semantic search)
  UNIQUE(parent_uid, chunk_index),
  FOREIGN KEY (parent_uid) REFERENCES items(uid) ON DELETE CASCADE
);

-- Indexes for chunk queries
CREATE INDEX IF NOT EXISTS idx_chunks_parent_uid ON chunks(parent_uid);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section);

-- Full-text search index for chunks (FTS5)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  parent_uid UNINDEXED,
  content,
  section UNINDEXED,
  content='chunks',
  content_rowid='rowid'
);

-- Triggers to keep FTS index in sync with chunks table
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, chunk_id, parent_uid, content, section)
  VALUES (new.rowid, new.chunk_id, new.parent_uid, new.content, new.section);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks BEGIN
  DELETE FROM chunks_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_update AFTER UPDATE ON chunks BEGIN
  DELETE FROM chunks_fts WHERE rowid = old.rowid;
  INSERT INTO chunks_fts(rowid, chunk_id, parent_uid, content, section)
  VALUES (new.rowid, new.chunk_id, new.parent_uid, new.content, new.section);
END;

-- ============================================
-- Workset-Specific Tables (Optional, Additive Only)
-- ============================================
-- These tables are ONLY present in workset DBs, not in repo-level index.
-- They MUST NOT modify core table schemas above.
-- Per ADR-0012, workset-specific tables MUST be prefixed with "workset_".

-- Workset Manifest: Metadata about the workset bundle
CREATE TABLE IF NOT EXISTS workset_manifest (
  workset_id TEXT PRIMARY KEY,       -- Unique workset identifier (UUIDv7)
  agent TEXT NOT NULL,               -- Agent who created this workset
  task_id TEXT,                      -- Associated task UID (optional)
  created_at TEXT NOT NULL,          -- ISO 8601 timestamp
  ttl_hours INTEGER,                 -- Time-to-live in hours (null = no expiry)
  seed_items TEXT,                   -- JSON array of seed UIDs
  expansion_params TEXT,             -- JSON: {k_hop: 2, edge_types: [...]}
  source_commit_hash TEXT,           -- Git commit of canonical files
  canonical_index_version TEXT NOT NULL,  -- Schema version of source index
  CHECK (length(canonical_index_version) > 0)  -- Ensure version is not empty
);

-- Workset Provenance: Track how items were selected into this workset
CREATE TABLE IF NOT EXISTS workset_provenance (
  item_uid TEXT PRIMARY KEY,         -- UID of item in this workset
  selection_reason TEXT NOT NULL,    -- "seed", "parent_expansion", "dependency_expansion", "manual"
  distance_from_seed INTEGER,        -- Hop count from nearest seed (0 for seeds)
  included_at TEXT NOT NULL,         -- ISO 8601 timestamp when item was added
  FOREIGN KEY (item_uid) REFERENCES items(uid) ON DELETE CASCADE
);

-- Index for provenance queries
CREATE INDEX IF NOT EXISTS idx_workset_provenance_reason ON workset_provenance(selection_reason);
CREATE INDEX IF NOT EXISTS idx_workset_provenance_distance ON workset_provenance(distance_from_seed);

-- ============================================
-- Notes
-- ============================================
--
-- 1. Content Storage Strategy:
--    - Full content: Store complete frontmatter + content in items.frontmatter (JSON)
--    - Pointer-based: Store only uid, path, content_hash (require canonical file access)
--    - Hybrid: Store summaries in items, pointers in path, optionally full content for hot items
--
-- 2. Schema Evolution:
--    - Migrations are applied via ADR-0008 framework (references/migrations/*.sql)
--    - Workset DBs MUST follow same migration sequence as repo-level index
--    - Workset schema_version MUST NOT exceed canonical schema_version
--
-- 3. Graph Model:
--    - Nodes: items table (all types)
--    - Edges: links table (typed relationships)
--    - Graph expansion uses links table for k-hop traversal
--
-- 4. Derived Data:
--    - Both repo-level index and workset DBs are DERIVED from canonical Markdown files
--    - Safe to delete and rebuild at any time
--    - Canonical files in _kano/backlog/products/<product>/items/ are source of truth
--
-- 5. Workset-Specific Extensions:
--    - Add new tables prefixed with "workset_" (allowed)
--    - Do NOT modify items, links, chunks, worklog, or schema_meta tables
--    - Do NOT add columns to core tables
--    - Do NOT rename or remove columns from canonical schema
