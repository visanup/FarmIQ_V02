Purpose: Provide the verification workflow and query pack for Batch 1 metadata traceability.  
Scope: JSON -> Edge -> Cloud verification for one WeighVision session.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Goal

Use this pack to prove that one session is traceable from IoT capture output to Edge persistence and Cloud persistence.

Success means:

- raw metadata exists at source
- key feature fields are persisted on Edge
- sync outbox contains the metadata event
- Cloud readmodel contains the synchronized inference event

---

## Required references

- [WeighVision metadata contract](../contracts/weighvision-capture-metadata.contract.md)
- [Field deployment enhancement plan](04-field-deployment-enhancement-plan.md)
- [Field deployment ticket backlog](05-field-deployment-ticket-backlog.md)
- [Local traceability runbook](07-local-traceability-runbook.md)

---

## Verified reference session

The following local integration session was used to verify Batch 1 end-to-end after closing the routing, schema bootstrap, and RabbitMQ startup defects:

- `session_id`: `sess-int-20260714-004`
- `capture_id`: `cap-20260714-004`
- `tenant_id`: `tenant-int-001`
- `session-created event_id`: `e11b0921-9d45-4da4-a6fc-68ce74bbadca`
- `inference-completed event_id`: `021856ac-a754-44a5-bc3a-f707b9e84eb7`

Observed result:

- metadata `POST /api/v1/weighvision/sessions/:sessionId/metadata` returned success
- metadata `GET /api/v1/weighvision/sessions/:sessionId/metadata` returned persisted record
- Edge `session_capture_metadata` contains the traceable raw and normalized payloads
- Edge `sync_outbox` contains the metadata event with `status = acked`
- Cloud `cloud_dedupe` contains the same event id
- Cloud `weighvision_inference` contains the synchronized inference payload

---

## Verification steps

### Step 1: confirm IoT source artifact

Find the capture JSON in:

- `iot-layer/weight-vision-capture/data/metadata/<capture_id>.json`

Verify:

- `image_id`
- `timestamp`
- `detections`
- `scale.weight_kg` if present

### Step 2: confirm Edge raw persistence

Run:

- [edge-weighvision-metadata-verification.sql](./query-pack/edge-weighvision-metadata-verification.sql)

Verify:

- `session_capture_metadata.raw_metadata` exists
- `capture_id` matches `image_id`
- `metadata_schema_version` and `feature_schema_version` are present

### Step 3: confirm Edge normalized feature mapping

In the same Edge query result verify:

- `area_mm2`
- `mask_area_px2`
- `bbox_x1..bbox_y2`
- `object_height_mm`
- `object_width_mm`
- `average_depth_mm`
- `median_depth_mm`
- `distance_mm`
- `confidence_score`

### Step 4: confirm Edge-to-Cloud sync payload

In Edge DB verify:

- `sync_outbox.event_type = 'weighvision.inference.completed'`
- `payload_json.payload.normalized_features` exists
- `payload_json.payload.metadata` exists

### Step 5: confirm Cloud persistence

Run:

- [cloud-weighvision-metadata-verification.sql](./query-pack/cloud-weighvision-metadata-verification.sql)

Verify:

- Cloud session exists
- Cloud inference record exists
- `resultJson` contains `metadata_schema`, `feature_schema`, `normalized_features`, and `metadata`

---

## Exit gate checklist

- [x] one session can be traced from capture JSON to Edge `session_capture_metadata`
- [x] critical feature fields are preserved as typed Edge columns
- [x] one `weighvision.inference.completed` event exists in Edge `sync_outbox`
- [x] one Cloud inference record exists for the same session
- [x] the team can inspect results using the included query pack without ad hoc SQL
