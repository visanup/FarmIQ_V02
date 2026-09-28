ALTER TABLE "batch_context_outbox"
  ADD COLUMN IF NOT EXISTS "change_sequence" BIGSERIAL;

CREATE UNIQUE INDEX IF NOT EXISTS "batch_context_outbox_change_sequence_key"
  ON "batch_context_outbox"("change_sequence");
