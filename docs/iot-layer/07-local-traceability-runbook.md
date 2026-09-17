Purpose: Standard local runbook for rebuild, startup, and smoke verification of WeighVision metadata traceability.  
Scope: Edge and Cloud local Docker flows for Batch 1 `JSON -> Edge -> Cloud` verification.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Goal

Use this runbook to:

- rebuild the required services
- start the local Edge and Cloud path
- push one mock session through the real HTTP flow
- verify `JSON -> Edge -> Cloud` with the existing query pack

---

## Services in scope

Cloud:

- `postgres`
- `rabbitmq`
- `cloud-ingestion`
- `cloud-weighvision-readmodel`

Edge:

- `postgres` from `docker-compose.dev.yml`
- `edge-weighvision-session`
- `edge-sync-forwarder`

---

## 1. Rebuild and start

### Cloud

From repo root:

```powershell
cd cloud-layer
docker compose up -d --build postgres rabbitmq cloud-ingestion cloud-weighvision-readmodel
```

### Edge

Important: Edge must use both compose files because `postgres` is defined in `docker-compose.dev.yml`.

```powershell
cd edge-layer
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build postgres edge-weighvision-session edge-sync-forwarder
```

---

## 2. Health check

From repo root:

```powershell
Invoke-RestMethod http://localhost:5105/api/ready
Invoke-RestMethod http://localhost:5108/api/health
Invoke-RestMethod http://localhost:5122/api/v1/edge/diagnostics/handshake -Headers @{'x-api-key'='edge-local-key'}
Invoke-RestMethod http://localhost:5132/api/ready
```

Expected:

- Edge WeighVision Session returns `ready`
- Edge Sync Forwarder returns `healthy`
- Cloud Ingestion handshake returns `ok = true`
- Cloud WeighVision Readmodel returns `ready`

---

## 3. Push one mock session

Run from repo root:

```powershell
$sessionId = "sess-int-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$tenantId = "tenant-int-001"
$farmId = "farm-alpha"
$barnId = "barn-a1"
$deviceId = "edge-cam-01"
$stationId = "station-01"
$traceId = [guid]::NewGuid().ToString()
$createdEventId = [guid]::NewGuid().ToString()
$inferenceEventId = [guid]::NewGuid().ToString()
$captureId = "cap-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$startAt = (Get-Date).ToUniversalTime().ToString("o")
$metadataAt = (Get-Date).ToUniversalTime().AddSeconds(5).ToString("o")

$createBody = @{
  sessionId = $sessionId
  eventId = $createdEventId
  tenantId = $tenantId
  farmId = $farmId
  barnId = $barnId
  deviceId = $deviceId
  stationId = $stationId
  batchId = "batch-int-local"
  startAt = $startAt
} | ConvertTo-Json

$metadataBody = @{
  tenantId = $tenantId
  farmId = $farmId
  barnId = $barnId
  deviceId = $deviceId
  stationId = $stationId
  eventId = $inferenceEventId
  occurredAt = $metadataAt
  captureId = $captureId
  mediaIds = @("media-$captureId")
  metadata = @{
    capture_id = $captureId
    image_id = "img-$captureId"
    metadata_schema = @{ name = "farmiq.weighvision.capture-metadata"; version = "1.0" }
    roi_count = 1
    scale = @{ weight_kg = 2.80 }
    detections = @(
      @{
        confidence = 0.99
        bbox = @{ x1 = 100; y1 = 120; x2 = 390; y2 = 470 }
        area_mm2 = 158000.0
        mask_area_px2 = 46000
        object_height_mm = 325.0
        object_width_mm = 220.0
        object_length_mm = 305.0
        average_depth_mm = 805.0
        median_depth_mm = 800.0
        distance_mm = 826.0
      }
    )
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri "http://localhost:5105/api/v1/weighvision/sessions" -Headers @{'x-trace-id' = $traceId} -ContentType "application/json" -Body $createBody
Invoke-RestMethod -Method Post -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId/metadata" -Headers @{'x-trace-id' = $traceId} -ContentType "application/json" -Body $metadataBody
Invoke-RestMethod -Method Get -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId/metadata" -Headers @{'x-trace-id' = $traceId}
Invoke-RestMethod -Method Post -Uri "http://localhost:5108/api/v1/sync/trigger" -Headers @{'x-trace-id' = $traceId} -ContentType "application/json" -Body "{}"
Start-Sleep -Seconds 8

"sessionId=$sessionId"
"captureId=$captureId"
"createdEventId=$createdEventId"
"inferenceEventId=$inferenceEventId"
```

Expected:

- session create returns `201`
- metadata POST returns normalized feature payload
- metadata GET returns one persisted record
- sync trigger returns success

---

## 4. Smoke verify via API

```powershell
Invoke-RestMethod "http://localhost:5108/api/v1/sync/outbox?status=acked&eventType=weighvision.inference.completed&tenantId=tenant-int-001&limit=20"
Invoke-RestMethod "http://localhost:5122/api/v1/edge/diagnostics/dedupe?tenant_id=tenant-int-001&limit=20" -Headers @{'x-api-key'='edge-local-key'}
```

Expected:

- Edge outbox shows `weighvision.inference.completed` with `status = acked`
- Cloud dedupe shows the same `event_id`

---

## 5. Verify with query pack

### Edge

Replace `:session_id` and `:capture_id` in:

- [query-pack/edge-weighvision-metadata-verification.sql](./query-pack/edge-weighvision-metadata-verification.sql)

Example:

```powershell
$sql = Get-Content ".\docs\iot-layer\query-pack\edge-weighvision-metadata-verification.sql" -Raw
$sql = $sql.Replace(':session_id', '''<session_id>''').Replace(':capture_id', '''<capture_id>''')
$sql | powershell -Command "docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T postgres psql -U farmiq -d farmiq" -WorkingDirectory ".\edge-layer"
```

### Cloud

Verify:

- `cloud_ingestion.cloud_dedupe`
- `cloud_weighvision_readmodel.weighvision_session`
- `cloud_weighvision_readmodel.weighvision_inference`

Example:

```powershell
$readSql = @'
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
WHERE s."tenantId" = 'tenant-int-001'
  AND s."sessionId" = '<session_id>'
ORDER BY i.ts ASC;
'@

$dedupeSql = @'
SELECT tenant_id, event_id, first_seen_at
FROM cloud_dedupe
WHERE tenant_id = 'tenant-int-001'
ORDER BY first_seen_at DESC;
'@

$readSql | docker exec -i farmiq-cloud-postgres psql -U farmiq -d cloud_weighvision_readmodel
$dedupeSql | docker exec -i farmiq-cloud-postgres psql -U farmiq -d cloud_ingestion
```

---

## Exit gate

- [ ] metadata endpoint `POST /metadata` returns success
- [ ] metadata endpoint `GET /metadata` returns persisted record
- [ ] `session_capture_metadata` contains the session and capture
- [ ] `sync_outbox` contains `weighvision.inference.completed` with `acked`
- [ ] `cloud_dedupe` contains the same event id
- [ ] `cloud_weighvision_readmodel` contains the inference record

If all checks pass, Batch 1 traceability is healthy for local development.
