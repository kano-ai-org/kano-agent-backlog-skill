-- Migration 002: Add Global Retrieval (Documents, Chunks, FTS5)
-- Purpose: Unified storage for hybrid search across WorkItems, ADRs, Logs, and Docs.

-- Document Registry
CREATE TABLE IF NOT EXISTS documents (
  doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT,                -- Canonical UID if exists (item/adr uid)
  doctype TEXT NOT NULL,   -- workitem, adr, worklog, workset, skill, attachment
  product TEXT NOT NULL,
  path TEXT NOT NULL,      -- Relative path (normalized)
  title TEXT NOT NULL,
  updated_at TEXT,         -- ISO timestamp
  content_hash TEXT,       -- SHA256 of full file
  visibility TEXT NOT NULL DEFAULT 'canonical', -- canonical, local_cache, private
  UNIQUE(path)
);

CREATE INDEX IF NOT EXISTS idx_documents_uid ON documents(uid);
CREATE INDEX IF NOT EXISTS idx_documents_doctype ON documents(doctype);
CREATE INDEX IF NOT EXISTS idx_documents_product ON documents(product);

-- Chunks for Embedding and FTS
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  text_hash TEXT NOT NULL, -- SHA256 of chunk text (for incremental embed)
  token_count INTEGER,
  section TEXT,            -- e.g. "# Context > # Goal"
  weight_hint REAL DEFAULT 1.0,
  vector_id INTEGER,       -- ID in the sidecar ANN index
  FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash);

-- FTS5 Virtual Table for Keyword Search
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  text,
  content='chunks',
  content_rowid='chunk_id'
);

-- Trigger to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS trg_chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.chunk_id, new.text);
END;

CREATE TRIGGER IF NOT EXISTS trg_chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.chunk_id, old.text);
END;

CREATE TRIGGER IF NOT EXISTS trg_chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.chunk_id, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.chunk_id, new.text);
END;
