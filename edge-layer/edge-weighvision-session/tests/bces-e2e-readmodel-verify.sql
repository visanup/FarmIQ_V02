SELECT
  "tenantId",
  "farmId",
  "barnId",
  "batchId",
  "stationId",
  "sessionId",
  status
FROM weighvision_session
WHERE "tenantId" = 't-001'
ORDER BY "createdAt" DESC
LIMIT 2;
