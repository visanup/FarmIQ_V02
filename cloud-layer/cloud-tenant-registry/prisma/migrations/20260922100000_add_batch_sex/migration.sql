-- Batch ML context. Nullable preserves historical batches while new UI/API writes it.
ALTER TABLE "batches"
  ADD COLUMN IF NOT EXISTS "sex" TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'batches_sex_check'
      AND conrelid = 'public.batches'::regclass
  ) THEN
    ALTER TABLE "batches"
      ADD CONSTRAINT "batches_sex_check"
      CHECK ("sex" IS NULL OR "sex" IN ('as_hatched', 'male', 'female'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS "batches_tenant_id_sex_idx"
  ON "batches"("tenantId", "sex");
