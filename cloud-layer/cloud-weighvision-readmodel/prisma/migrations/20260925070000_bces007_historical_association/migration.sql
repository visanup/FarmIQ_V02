-- BCES-007: additive audit and a queue separate from realtime inference.
CREATE TABLE IF NOT EXISTS "weighvision_historical_association_audit" (
  "id" TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "sessionDbId" TEXT NOT NULL,
  "sessionId" TEXT NOT NULL, "previousBatchId" TEXT, "targetBatchId" TEXT NOT NULL,
  "requestedBy" TEXT, "reason" TEXT NOT NULL,
  "associatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "weighvision_historical_association_audit_sessionDbId_fkey"
    FOREIGN KEY ("sessionDbId") REFERENCES "weighvision_session"("id") ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "weighvision_historical_association_audit_tenant_session_idx"
  ON "weighvision_historical_association_audit"("tenantId", "sessionId", "associatedAt" DESC);

CREATE TABLE IF NOT EXISTS "weighvision_historical_reprocess_job" (
  "id" TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "batchId" TEXT NOT NULL,
  "from" TIMESTAMP(3) NOT NULL, "to" TIMESTAMP(3) NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'queued', "requestedBy" TEXT,
  "requestedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "cancelledAt" TIMESTAMP(3), "reason" TEXT
);
CREATE INDEX IF NOT EXISTS "weighvision_historical_reprocess_job_tenant_status_idx"
  ON "weighvision_historical_reprocess_job"("tenantId", "status", "requestedAt");

ALTER TABLE "weighvision_historical_reprocess_job"
  ADD COLUMN IF NOT EXISTS "startedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "completedAt" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "pauseReason" TEXT,
  ADD COLUMN IF NOT EXISTS "totalSessions" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "submittedSessions" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "skippedSessions" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS "lastError" TEXT;

-- Immutable lineage is independent of the read-model projection. Reprocess
-- can therefore never overwrite an original inference result.
CREATE TABLE IF NOT EXISTS "weighvision_inference_revision" (
  "id" TEXT PRIMARY KEY, "tenantId" TEXT NOT NULL, "sessionId" TEXT NOT NULL,
  "inferenceId" TEXT NOT NULL, "originalInferenceId" TEXT,
  "historicalJobId" TEXT NOT NULL, "revision" INTEGER NOT NULL,
  "provenance" JSONB NOT NULL, "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "weighvision_inference_revision_inferenceId_fkey"
    FOREIGN KEY ("inferenceId") REFERENCES "weighvision_inference"("id") ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "weighvision_inference_revision_inference_uq"
  ON "weighvision_inference_revision"("inferenceId");
CREATE INDEX IF NOT EXISTS "weighvision_inference_revision_session_idx"
  ON "weighvision_inference_revision"("tenantId", "sessionId", "revision" DESC);
