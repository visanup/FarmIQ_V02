Purpose: Standard local runbook to prove `final_weight_kg` from Edge finalize payload to Cloud readmodel.  
Scope: Batch 2.1 local smoke, Docker Compose verification, and SQL checklist for `final_weight_kg` end-to-end.  
Owner: FarmIQ Edge and IoT Architecture  
Last updated: 2026-07-14  

---

## Goal

Use this runbook to prove one finalized session can be traced end-to-end:

- nested `payload.scale.weight_kg` accepted by Edge finalize API
- Edge persists `weight_sessions.final_weight_kg`
- Edge writes `sync_outbox.payload_json.final_weight_kg`
- `edge-sync-forwarder` sends the finalized event to cloud
- `cloud-ingestion` deduplicates the same `event_id`
- `cloud-weighvision-readmodel` marks the session `FINALIZED`
- `cloud-weighvision-readmodel` writes a `finalized` measurement row

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

Important:

- `cloud-weighvision-readmodel` now uses the local Prisma binary inside the image
- if `migrate deploy` hits `P3005` on a pre-seeded local database, startup falls back to `prisma db push`

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
Invoke-RestMethod http://localhost:5108/api/ready
Invoke-RestMethod http://localhost:5122/api/v1/edge/diagnostics/handshake -Headers @{'x-api-key'='edge-local-key'}
Invoke-RestMethod http://localhost:5132/api/ready
```

Expected:

- `edge-weighvision-session` returns `ready`
- `edge-sync-forwarder` returns `ready`
- `cloud-ingestion` handshake returns `ok = true`
- `cloud-weighvision-readmodel` returns `ready`

---

## 3. Push one mock finalized session

Run from repo root:

```powershell
$sessionId = "sess-fw-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$tenantId = "tenant-int-001"
$traceId = [guid]::NewGuid().ToString()
$createEventId = [guid]::NewGuid().ToString()
$finalizeEventId = [guid]::NewGuid().ToString()
$startAt = (Get-Date).ToUniversalTime().ToString("o")
$occurredAt = (Get-Date).ToUniversalTime().AddSeconds(5).ToString("o")
$expectedWeightKg = 12.34

$createBody = @{
  sessionId = $sessionId
  eventId = $createEventId
  tenantId = $tenantId
  farmId = "farm-alpha"
  barnId = "barn-a1"
  deviceId = "edge-cam-01"
  stationId = "station-01"
  batchId = "batch-final-weight"
  startAt = $startAt
} | ConvertTo-Json

$finalizeBody = @{
  tenantId = $tenantId
  eventId = $finalizeEventId
  occurredAt = $occurredAt
  payload = @{
    scale = @{
      weight_kg = $expectedWeightKg
      weight_source = "instant"
    }
    finalize_reason = "batch-2.1-local-smoke"
  }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Method Post -Uri "http://localhost:5105/api/v1/weighvision/sessions" -Headers @{'x-trace-id' = $traceId} -ContentType "application/json" -Body $createBody
Invoke-RestMethod -Method Post -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId/finalize" -Headers @{'x-trace-id' = $traceId} -ContentType "application/json" -Body $finalizeBody
Invoke-RestMethod -Method Get -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId" -Headers @{'x-trace-id' = $traceId}
Invoke-RestMethod -Method Post -Uri "http://localhost:5108/api/v1/sync/trigger" -Headers @{'x-trace-id' = $traceId} -ContentType "application/json" -Body "{}"
Start-Sleep -Seconds 10

"sessionId=$sessionId"
"tenantId=$tenantId"
"createEventId=$createEventId"
"finalizeEventId=$finalizeEventId"
"expectedWeightKg=$expectedWeightKg"
```

Expected:

- create returns `status = created`
- finalize returns `status = finalized`
- session GET returns `finalWeightKg = 12.34`
- sync trigger returns success

---

## 4. Quick API verify

```powershell
Invoke-RestMethod "http://localhost:5108/api/v1/sync/outbox?status=acked&eventType=weighvision.session.finalized&tenantId=tenant-int-001&limit=20"
```

Expected:

- one `weighvision.session.finalized` row exists with:
  - `status = acked`
  - top-level `payload_json.final_weight_kg`
  - nested `payload_json.payload.scale.weight_kg`

---

## 5. SQL query pack

### Edge

Use [query-pack/edge-weighvision-final-weight-verification.sql](./query-pack/edge-weighvision-final-weight-verification.sql)

Checklist:

- `weight_sessions.final_weight_kg` equals expected value
- `weight_sessions.status = finalized`
- `sync_outbox.event_type = weighvision.session.finalized`
- `sync_outbox.status = acked`
- `sync_outbox.payload_json->>'final_weight_kg'` equals expected value
- `sync_outbox.payload_json->'payload'->'scale'->>'weight_kg'` equals expected value

### Cloud

Use [query-pack/cloud-weighvision-final-weight-verification.sql](./query-pack/cloud-weighvision-final-weight-verification.sql)

Checklist:

- `cloud_ingestion.cloud_dedupe` contains the same finalized `event_id`
- `cloud_weighvision_readmodel.weighvision_session.status = FINALIZED`
- `cloud_weighvision_readmodel.weighvision_session.endedAt` is populated
- `cloud_weighvision_readmodel.weighvision_measurement.weightKg` equals expected value
- `cloud_weighvision_readmodel.weighvision_measurement.source = finalized`

---

## 6. Known defects fixed during this proof

This runbook assumes the following local defects are already corrected in the repo:

1. `cloud-weighvision-readmodel` runtime no longer drifts to Prisma 7 via `npx`
2. `cloud-weighvision-readmodel` can start against a pre-seeded local DB by falling back from `migrate deploy` to `db push`
3. `cloud-weighvision-readmodel` finalization path is idempotent across `session.created` and `session.finalized` races
4. `edge-weighvision-session` can read nested `payload.scale.weight_kg`
5. `weight-vision-service` emits explicit top-level `final_weight_kg`

---

## Exit gate

- [ ] one session finalized from the real Edge API path
- [ ] nested `payload.scale.weight_kg` becomes Edge `final_weight_kg`
- [ ] Edge outbox row is `acked`
- [ ] Cloud dedupe contains the same finalized event
- [ ] Cloud session becomes `FINALIZED`
- [ ] Cloud measurement row exists with `source = finalized`
- [ ] expected weight value is preserved end-to-end without field loss

If all checks pass, Batch 2.1 local smoke is complete for `final_weight_kg` end-to-end proof.
