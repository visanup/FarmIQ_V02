-- Batch 2 audit dataset for WeighVision session weight anomalies.
-- Replace the WHERE clause as needed for a target session/date range.

WITH weight_rollup AS (
  SELECT
    sw.session_id,
    COUNT(*) AS weight_event_count,
    MIN(sw.occurred_at) AS first_weight_at,
    MAX(sw.occurred_at) AS last_weight_at,
    MIN(sw.weight_kg) AS min_weight_kg,
    MAX(sw.weight_kg) AS max_weight_kg,
    (
      ARRAY_AGG(sw.weight_kg ORDER BY sw.occurred_at ASC)
    )[1] AS first_weight_kg,
    (
      ARRAY_AGG(sw.weight_kg ORDER BY sw.occurred_at DESC)
    )[1] AS latest_weight_kg
  FROM session_weights sw
  GROUP BY sw.session_id
),
media_rollup AS (
  SELECT
    smb.session_id,
    COUNT(*) AS media_binding_count,
    COUNT(*) FILTER (WHERE smb.is_bound) AS bound_media_count
  FROM session_media_bindings smb
  GROUP BY smb.session_id
),
capture_rollup AS (
  SELECT DISTINCT ON (scm.session_id)
    scm.session_id,
    scm.capture_id,
    scm.event_id AS capture_event_id,
    scm.trace_id AS capture_trace_id,
    scm.occurred_at AS capture_occurred_at,
    scm.metadata_schema_version,
    scm.feature_schema_version,
    scm.detection_count,
    scm.roi_count,
    scm.area_mm2,
    scm.mask_area_px2,
    scm.object_height_mm,
    scm.object_width_mm,
    scm.object_length_mm,
    scm.average_depth_mm,
    scm.median_depth_mm,
    scm.distance_mm,
    scm.confidence_score,
    scm.scale_weight_kg,
    scm.raw_metadata -> 'scale' ->> 'weight_source' AS capture_weight_source,
    scm.normalized_features
  FROM session_capture_metadata scm
  ORDER BY scm.session_id, scm.occurred_at DESC, scm.created_at DESC
),
finalize_outbox AS (
  SELECT DISTINCT ON (so.session_id)
    so.session_id,
    so.id AS finalized_event_id,
    so.occurred_at AS finalized_occurred_at,
    so.payload_json ->> 'final_weight_kg' AS outbox_final_weight_kg,
    so.payload_json -> 'payload' ->> 'final_weight_kg' AS payload_final_weight_kg,
    so.payload_json -> 'payload' -> 'scale' ->> 'weight_kg' AS payload_scale_weight_kg,
    so.payload_json -> 'payload' -> 'scale' ->> 'weight_source' AS payload_weight_source,
    so.status AS finalized_sync_status
  FROM sync_outbox so
  WHERE so.event_type = 'weighvision.session.finalized'
  ORDER BY so.session_id, so.occurred_at DESC, so.created_at DESC
)
SELECT
  ws.session_id,
  ws.tenant_id,
  ws.farm_id,
  ws.barn_id,
  ws.device_id,
  ws.station_id,
  ws.status,
  ws.start_at,
  ws.end_at,
  ws.initial_weight_kg,
  ws.final_weight_kg,
  wr.weight_event_count,
  wr.first_weight_at,
  wr.last_weight_at,
  wr.first_weight_kg,
  wr.latest_weight_kg,
  mr.media_binding_count,
  mr.bound_media_count,
  cr.capture_id,
  cr.capture_event_id,
  cr.capture_trace_id,
  cr.capture_occurred_at,
  cr.metadata_schema_version,
  cr.feature_schema_version,
  cr.detection_count,
  cr.roi_count,
  cr.area_mm2,
  cr.mask_area_px2,
  cr.object_height_mm,
  cr.object_width_mm,
  cr.object_length_mm,
  cr.average_depth_mm,
  cr.median_depth_mm,
  cr.distance_mm,
  cr.confidence_score,
  cr.scale_weight_kg,
  cr.capture_weight_source,
  fo.finalized_event_id,
  fo.finalized_occurred_at,
  fo.outbox_final_weight_kg,
  fo.payload_final_weight_kg,
  fo.payload_scale_weight_kg,
  fo.payload_weight_source,
  fo.finalized_sync_status,
  CASE
    WHEN cr.scale_weight_kg IS NULL THEN 'sensor_missing_weight'
    WHEN cr.scale_weight_kg >= 20 THEN 'sensor_unit_mismatch_candidate'
    WHEN cr.capture_weight_source = 'unstable' THEN 'sensor_unstable_weight'
    WHEN cr.distance_mm IS NOT NULL AND cr.distance_mm > 1712.69 THEN 'depth_outlier_high'
    WHEN cr.distance_mm IS NOT NULL AND cr.distance_mm < 525.72 THEN 'depth_outlier_low'
    WHEN cr.object_height_mm IS NOT NULL AND cr.object_height_mm < 0 THEN 'depth_negative_height'
    WHEN cr.detection_count > 1 THEN 'segmentation_multi_detection'
    WHEN cr.confidence_score IS NOT NULL AND cr.confidence_score < 0.35 THEN 'segmentation_low_confidence'
    ELSE 'nominal'
  END AS primary_audit_flag,
  ws.final_weight_kg - COALESCE(wr.latest_weight_kg, ws.initial_weight_kg, 0) AS final_vs_latest_weight_delta_kg,
  ws.final_weight_kg - COALESCE(cr.scale_weight_kg, 0) AS final_vs_capture_scale_delta_kg,
  cr.normalized_features
FROM weight_sessions ws
LEFT JOIN weight_rollup wr ON wr.session_id = ws.session_id
LEFT JOIN media_rollup mr ON mr.session_id = ws.session_id
LEFT JOIN capture_rollup cr ON cr.session_id = ws.session_id
LEFT JOIN finalize_outbox fo ON fo.session_id = ws.session_id
ORDER BY ws.start_at DESC, ws.session_id DESC;
