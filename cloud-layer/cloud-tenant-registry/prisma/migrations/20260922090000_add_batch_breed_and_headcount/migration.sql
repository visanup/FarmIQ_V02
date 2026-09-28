-- Batch ML context. Values are nullable so historical batches remain valid.
ALTER TABLE "batches"
  ADD COLUMN IF NOT EXISTS "breed_code" TEXT,
  ADD COLUMN IF NOT EXISTS "initial_headcount" INTEGER;

CREATE INDEX IF NOT EXISTS "batches_tenant_id_breed_code_idx"
  ON "batches"("tenantId", "breed_code");
