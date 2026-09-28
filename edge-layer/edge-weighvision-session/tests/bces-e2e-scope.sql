-- Isolated BCES E2E fixture. Apply only to bces-e2e-edge-postgres.
INSERT INTO edge_batch_context_cache (
  tenant_id, farm_id, barn_id, batch_id, revision, lifecycle,
  species, breed_code, sex, start_date, model_policy_json,
  hash, fetched_at, expires_at
) VALUES (
  't-001', 'f-001', 'b-001', 'batch-e2e-t001', 1, 'active',
  'chicken', 'broiler', 'mixed', NOW() - INTERVAL '21 days',
  jsonb_build_object('mode', 'fallback', 'modelVersion', 'wv-shadow-1.0.0'),
  'bces-e2e-t001', NOW(), NOW() + INTERVAL '1 day'
)
ON CONFLICT (tenant_id, batch_id) DO UPDATE SET
  farm_id = EXCLUDED.farm_id,
  barn_id = EXCLUDED.barn_id,
  revision = EXCLUDED.revision,
  lifecycle = EXCLUDED.lifecycle,
  species = EXCLUDED.species,
  breed_code = EXCLUDED.breed_code,
  sex = EXCLUDED.sex,
  start_date = EXCLUDED.start_date,
  model_policy_json = EXCLUDED.model_policy_json,
  hash = EXCLUDED.hash,
  fetched_at = NOW(),
  expires_at = EXCLUDED.expires_at;

INSERT INTO edge_batch_binding_cache (
  tenant_id, batch_id, binding_id, device_id, station_id, revision, active
) VALUES (
  't-001', 'batch-e2e-t001', 'binding-e2e-t001', 'wv-001', 'st-001', 1, TRUE
)
ON CONFLICT (tenant_id, binding_id) DO UPDATE SET
  batch_id = EXCLUDED.batch_id,
  device_id = EXCLUDED.device_id,
  station_id = EXCLUDED.station_id,
  revision = EXCLUDED.revision,
  active = TRUE,
  updated_at = NOW();
