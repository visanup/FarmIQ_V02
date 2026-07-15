-- Edge final-weight verification
-- Replace the placeholders before running:
--   :session_id

SELECT
  session_id,
  tenant_id,
  farm_id,
  barn_id,
  station_id,
  status,
  final_weight_kg,
  end_at,
  created_at,
  updated_at
FROM weight_sessions
WHERE session_id = :session_id;

SELECT
  id,
  tenant_id,
  session_id,
  event_type,
  occurred_at,
  status,
  payload_json->>'final_weight_kg' AS final_weight_kg,
  payload_json->'payload'->'scale'->>'weight_kg' AS nested_scale_weight,
  payload_json->'payload'->'scale'->>'weight_source' AS weight_source,
  payload_json
FROM sync_outbox
WHERE session_id = :session_id
  AND event_type = 'weighvision.session.finalized'
ORDER BY occurred_at ASC, created_at ASC;
