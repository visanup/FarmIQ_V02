-- Cloud-to-Edge Batch Context outbox.  All changes are additive so existing
-- batches remain valid and can receive their first revision on the next edit.
ALTER TABLE "batches"
  ADD COLUMN IF NOT EXISTS "context_revision" INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS "batch_context_outbox" (
  "id" TEXT NOT NULL,
  "batch_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "farm_id" TEXT NOT NULL,
  "barn_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "revision" INTEGER NOT NULL,
  "payload" JSONB NOT NULL,
  "occurred_at" TIMESTAMPTZ NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "attempt_count" INTEGER NOT NULL DEFAULT 0,
  "last_attempt_at" TIMESTAMPTZ,
  "dispatched_at" TIMESTAMPTZ,
  "last_error" TEXT,
  "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "batch_context_outbox_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "batch_context_outbox_batch_id_revision_key"
    UNIQUE ("batch_id", "revision"),
  CONSTRAINT "batch_context_outbox_status_check"
    CHECK ("status" IN ('pending', 'dispatched', 'failed'))
);

CREATE INDEX IF NOT EXISTS "batch_context_outbox_status_created_at_idx"
  ON "batch_context_outbox"("status", "created_at");
CREATE INDEX IF NOT EXISTS "batch_context_outbox_tenant_id_farm_id_barn_id_idx"
  ON "batch_context_outbox"("tenant_id", "farm_id", "barn_id");
