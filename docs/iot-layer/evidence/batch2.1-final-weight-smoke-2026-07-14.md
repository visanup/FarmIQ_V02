Purpose: Record the local Batch 2.1 end-to-end proof for `final_weight_kg`.  
Scope: Docker Compose verification, smoke session evidence, and defects uncovered/fixed during proof.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Final verified session

- `session_id`: `sess-fw-20260714-113013`
- `tenant_id`: `tenant-int-001`
- `expected_weight_kg`: `12.34`
- `create_event_id`: `617202a5-735f-44e1-8f7a-239393b4dfee`
- `finalize_event_id`: `ac4e2bea-8cc3-4258-bd44-587c7842c301`

## Verified path

`payload.scale.weight_kg`
-> `edge-weighvision-session.finalWeightKg`
-> `weight_sessions.final_weight_kg`
-> `sync_outbox.payload_json.final_weight_kg`
-> `cloud_ingestion.cloud_dedupe`
-> `cloud_weighvision_readmodel.weighvision_session`
-> `cloud_weighvision_readmodel.weighvision_measurement`

## Verified results

- Edge session API returned `finalWeightKg = 12.34`
- Edge `weight_sessions.status = finalized`
- Edge `weight_sessions.final_weight_kg = 12.34`
- Edge `sync_outbox.event_type = weighvision.session.finalized`
- Edge `sync_outbox.status = acked`
- Edge outbox top-level `final_weight_kg = 12.34`
- Edge outbox nested `payload.scale.weight_kg = 12.34`
- Cloud ingestion `cloud_dedupe` contains `ac4e2bea-8cc3-4258-bd44-587c7842c301`
- Cloud readmodel session status is `FINALIZED`
- Cloud readmodel `weighvision_measurement.weightKg = 12.340`
- Cloud readmodel measurement `source = finalized`

## First-run defect that was intentionally preserved as evidence

Initial session:

- `session_id`: `sess-fw-20260714-110908`
- `finalize_event_id`: `b3c94c1c-4399-4336-8386-2431b4eb3c1e`

What it proved:

- Edge finalize path was already correct
- Cloud ingestion received the finalized event

Why it did not close the exit gate:

- `cloud-weighvision-readmodel` attempted to create the same `(tenantId, sessionId)` twice across `session.created` and `session.finalized`
- the service hit Prisma `P2002` on `WeighVisionSession`
- result: Cloud session stayed `RUNNING` and no finalized measurement row was written

## Defects fixed during Batch 2.1 proof

1. `cloud-weighvision-readmodel` production image no longer relies on runtime `npx prisma`
2. `cloud-weighvision-readmodel` startup now tolerates pre-seeded local databases through `migrate deploy -> db push` fallback
3. `cloud-weighvision-readmodel` session materialization is now idempotent with `upsert` on `(tenantId, sessionId)`

## Exit gate result

Batch 2.1 local smoke is satisfied for `final_weight_kg` end-to-end proof.
