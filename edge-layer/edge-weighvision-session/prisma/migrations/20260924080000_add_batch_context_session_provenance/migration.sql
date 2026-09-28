ALTER TABLE weight_sessions
  ADD COLUMN IF NOT EXISTS batch_context_revision INTEGER NULL,
  ADD COLUMN IF NOT EXISTS batch_context_resolution TEXT NOT NULL DEFAULT 'unassigned',
  ADD COLUMN IF NOT EXISTS batch_context_reason TEXT NULL,
  ADD COLUMN IF NOT EXISTS batch_context_provenance JSONB NULL;
