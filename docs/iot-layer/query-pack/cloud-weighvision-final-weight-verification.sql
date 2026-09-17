-- Cloud final-weight verification
-- Replace the placeholders before running:
--   :tenant_id
--   :session_id
--   :finalize_event_id

SELECT
  tenant_id,
  event_id,
  first_seen_at
FROM cloud_dedupe
WHERE tenant_id = :tenant_id
  AND event_id = :finalize_event_id;

SELECT
  "tenantId",
  "sessionId",
  status,
  "startedAt",
  "endedAt",
  "createdAt",
  "updatedAt"
FROM weighvision_session
WHERE "tenantId" = :tenant_id
  AND "sessionId" = :session_id;

SELECT
  "tenantId",
  "sessionId",
  ts,
  "weightKg",
  source,
  "metaJson"
FROM weighvision_measurement
WHERE "tenantId" = :tenant_id
  AND "sessionId" = :session_id
ORDER BY ts DESC;
