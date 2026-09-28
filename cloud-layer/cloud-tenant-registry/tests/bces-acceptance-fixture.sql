-- Isolated BCES E2E fixture.  Execute only against the bces-e2e
-- cloud_tenant_registry database; the stable IDs mirror the dashboard scope.
INSERT INTO tenants (id, name, status, type, region, "updatedAt") VALUES
  ('t-001', 'BCES E2E Tenant', 'active', 'standard', 'TH', NOW())
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO farms (id, "tenantId", name, status, "updatedAt") VALUES
  ('f-001', 't-001', 'BCES E2E Farm', 'active', NOW())
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO barns (id, "tenantId", "farmId", name, status, "updatedAt") VALUES
  ('b-001', 't-001', 'f-001', 'BCES E2E Barn', 'active', NOW())
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO stations (id, "tenantId", "farmId", "barnId", name, "stationType", status, "updatedAt") VALUES
  ('st-001', 't-001', 'f-001', 'b-001', 'BCES E2E Station', 'weighing', 'active', NOW())
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO batches (
  id, "tenantId", "farmId", "barnId", species, breed_code, sex,
  initial_headcount, "startDate", status, context_revision, "updatedAt"
) VALUES (
  'batch-e2e-t001', 't-001', 'f-001', 'b-001', 'chicken', 'ROSS-308', 'mixed',
  1000, NOW() - INTERVAL '21 days', 'active', 1, NOW()
)
ON CONFLICT (id) DO UPDATE SET
  breed_code = EXCLUDED.breed_code, sex = EXCLUDED.sex,
  "startDate" = EXCLUDED."startDate", status = EXCLUDED.status,
  context_revision = EXCLUDED.context_revision;

INSERT INTO devices (id, "tenantId", "farmId", "barnId", "batchId", "deviceType", "serialNo", status, metadata, "updatedAt") VALUES
  ('wv-001', 't-001', 'f-001', 'b-001', 'batch-e2e-t001', 'weighvision', 'wv-001', 'active', '{"stationId":"st-001"}', NOW())
ON CONFLICT (id) DO UPDATE SET
  "batchId" = EXCLUDED."batchId", metadata = EXCLUDED.metadata, status = EXCLUDED.status;

INSERT INTO batch_context_outbox (
  id, batch_id, tenant_id, farm_id, barn_id, event_type, revision, payload, occurred_at, status, updated_at
) VALUES (
  'bces-e2e-batch-event-001', 'batch-e2e-t001', 't-001', 'f-001', 'b-001', 'batch.binding.upsert', 1,
  '{"eventId":"bces-e2e-batch-event-001","eventType":"batch.binding.upsert","revision":1,"occurredAt":"2026-09-25T00:00:00.000Z","tenantId":"t-001","farmId":"f-001","barnId":"b-001","batchId":"batch-e2e-t001","status":"active","species":"chicken","breedCode":"ROSS-308","sex":"mixed","startDate":"2026-09-04T00:00:00.000Z","endDate":null,"deviceBindings":[{"deviceId":"wv-001","stationId":"st-001"}]}'::jsonb,
  NOW(), 'dispatched', NOW()
)
ON CONFLICT (id) DO UPDATE SET
  payload = EXCLUDED.payload, status = EXCLUDED.status, occurred_at = EXCLUDED.occurred_at;
