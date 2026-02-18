-- Migration 003: Add model column to worklog_entries
-- Context: Extended worklog format to optionally capture model information
-- (e.g., claude-sonnet-4.5, gpt-5.1) alongside agent identity for better
-- audit trails and debugging. This migration adds the nullable model column.

ALTER TABLE worklog_entries ADD COLUMN model TEXT;
CREATE INDEX IF NOT EXISTS idx_worklog_entries_model ON worklog_entries(model);

INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', '3');
