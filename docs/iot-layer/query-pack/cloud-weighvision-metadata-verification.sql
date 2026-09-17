-- Cloud metadata trace verification
-- Replace:
--   :tenant_id
--   :session_id

SELECT
  s.id,
  s."tenantId",
  s."farmId",
  s."barnId",
  s."stationId",
  s."sessionId",
  s.status,
  s."startedAt",
  s."endedAt",
  i.id AS inference_id,
  i."modelVersion",
  i.ts AS inference_ts,
  i."resultJson"
FROM weighvision_session s
LEFT JOIN weighvision_inference i
  ON i."sessionDbId" = s.id
WHERE s."tenantId" = :tenant_id
  AND s."sessionId" = :session_id
ORDER BY i.ts ASC;

SELECT
  tenant_id,
  event_id,
  first_seen_at
FROM cloud_dedupe
WHERE tenant_id = :tenant_id
ORDER BY first_seen_at DESC;
