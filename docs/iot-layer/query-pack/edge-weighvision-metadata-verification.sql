-- Edge metadata trace verification
-- Replace the placeholders before running:
--   :session_id
--   :capture_id

SELECT
  ws.session_id,
  ws.tenant_id,
  ws.farm_id,
  ws.barn_id,
  ws.device_id,
  ws.station_id,
  ws.status,
  ws.start_at,
  ws.final_weight_kg,
  scm.capture_id,
  scm.event_id,
  scm.metadata_schema_version,
  scm.feature_schema_version,
  scm.occurred_at,
  scm.detection_count,
  scm.roi_count,
  scm.area_mm2,
  scm.mask_area_px2,
  scm.bbox_x1,
  scm.bbox_y1,
  scm.bbox_x2,
  scm.bbox_y2,
  scm.object_height_mm,
  scm.object_width_mm,
  scm.object_length_mm,
  scm.average_depth_mm,
  scm.median_depth_mm,
  scm.distance_mm,
  scm.confidence_score,
  scm.scale_weight_kg,
  scm.raw_metadata,
  scm.normalized_features
FROM weight_sessions ws
LEFT JOIN session_capture_metadata scm
  ON scm.session_id = ws.session_id
WHERE ws.session_id = :session_id
  AND (:capture_id IS NULL OR scm.capture_id = :capture_id)
ORDER BY scm.occurred_at ASC;

SELECT
  id,
  tenant_id,
  session_id,
  event_type,
  occurred_at,
  status,
  payload_json
FROM sync_outbox
WHERE session_id = :session_id
  AND event_type = 'weighvision.inference.completed'
ORDER BY occurred_at ASC, created_at ASC;
