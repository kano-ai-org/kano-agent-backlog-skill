-- SQLite Schema for Global Embedding Database
-- Supports hybrid search (FTS5 keyword + FAISS semantic ANN)

-- Documents table: high-level items (work items, ADRs, etc.)
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,  -- 'item' or 'adr'
    item_type TEXT,           -- 'Task', 'Feature', 'Epic', etc. (items only)
    title TEXT NOT NULL,
    state TEXT,               -- 'New', 'InProgress', 'Done', etc.
    product TEXT,             -- Product name for scoping
    source_path TEXT NOT NULL,
    path_hash TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    metadata_json TEXT,       -- Full metadata as JSON
    UNIQUE(source_path, product)
);

CREATE INDEX IF NOT EXISTS idx_documents_product ON documents(product);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(state);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_rowid INTEGER PRIMARY KEY AUTOINCREMENT, -- integer rowid for FTS5 content_rowid
  id TEXT NOT NULL UNIQUE,                       -- stable text chunk id
  doc_id TEXT NOT NULL,
  section_path TEXT,        -- 'item/context', 'item/worklog', 'adr/decision', etc.
  chunk_kind TEXT,          -- 'header', 'section', 'worklog', 'decision'
  chunk_index INTEGER,      -- Zero-based chunk index within document
  chunk_count INTEGER,      -- Total chunks for this document
  text TEXT NOT NULL,
  chunk_char_len INTEGER,
  chunk_hash TEXT NOT NULL, -- SHA256 of text for change detection
  worklog_span_start TEXT,  -- ISO8601 timestamp for worklog entries
  worklog_span_end TEXT,
  language TEXT DEFAULT 'en',
  redaction TEXT DEFAULT 'none',
  schema_version TEXT DEFAULT '0.1.0',
  product TEXT,             -- Product name (from parent document)
  embedding_generated BOOLEAN DEFAULT 0,
  embedding_vector_id INTEGER,  -- Reference to FAISS index (for future use)
  FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_product ON chunks(product);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_kind ON chunks(chunk_kind);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_generated ON chunks(embedding_generated);

-- FTS5 virtual table for full-text search (keyword search)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  doc_id,
  section_path,
  chunk_kind,
  text,
  product,
  content=chunks,
  content_rowid=chunk_rowid
);

-- Triggers to keep FTS5 table in sync with chunks table
-- For FTS5 with external content table, we need to manually manage the index
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, doc_id, section_path, chunk_kind, text, product)
  VALUES (new.chunk_rowid, new.doc_id, new.section_path, new.chunk_kind, new.text, new.product);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, doc_id, section_path, chunk_kind, text, product)
  VALUES('delete', old.chunk_rowid, old.doc_id, old.section_path, old.chunk_kind, old.text, old.product);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, doc_id, section_path, chunk_kind, text, product)
  VALUES('delete', old.chunk_rowid, old.doc_id, old.section_path, old.chunk_kind, old.text, old.product);
  INSERT INTO chunks_fts(rowid, doc_id, section_path, chunk_kind, text, product)
  VALUES (new.chunk_rowid, new.doc_id, new.section_path, new.chunk_kind, new.text, new.product);
END;

-- Metadata table for tracking index state
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
);

-- Insert default metadata
INSERT OR IGNORE INTO metadata (key, value, updated_at) VALUES 
    ('last_ingest', NULL, NULL),
    ('last_embed', NULL, NULL),
    ('chunk_count', '0', NULL),
    ('faiss_index_size', '0', NULL);
