Purpose: Provide a repeatable production-like local E2E runbook for the WeighVision path using the real non-IP parameters from `iot-layer/weight-vision-service/.env`.
Scope: IoT mock-capture replay through `weight-vision-service` into local Edge and Cloud services, with explicit runtime IP overrides and repeated verification.
Owner: FarmIQ Edge and Cloud Architecture
Last updated: 2026-07-17

---

## Goal

Use this runbook when you want to rerun the local WeighVision E2E path with the same business identifiers as the real IoT configuration:

- `TENANT_ID=t-001`
- `FARM_ID=f-001`
- `BARN_ID=b-001`
- `DEVICE_ID=wv-001`
- `STATION_ID=st-01`

This runbook intentionally allows the host IP to differ from the IP inside `.env`, as long as all non-IP parameters stay aligned with the real file.

Exit condition:

- Edge services are healthy on host ports `5103` through `5109`
- Cloud services are healthy on host ports `5120`, `5121`, `5122`, `5123`, `5125`, `5126`, `5129`, `5132`, `5135`
- one-shot replay reaches both Edge and Cloud
- repeated replay loop reaches Cloud readmodel as `FINALIZED`

---

## Source of truth parameters

Read these values from:

- `iot-layer/weight-vision-service/.env`

For this verified run on Friday, July 17, 2026, the required non-IP values were:

- `TENANT_ID=t-001`
- `FARM_ID=f-001`
- `BARN_ID=b-001`
- `DEVICE_ID=wv-001`
- `STATION_ID=st-01`

The IP-related values in `.env` do not need to match the local workstation IP during rerun. Override only these at runtime:

- `MQTT_HOST`
- `MQTT_HOSTS`
- `EDGE_MEDIA_STORE_BASE_URL`
- `EDGE_SESSION_BASE_URL`
- `EDGE_VISION_INFERENCE_BASE_URL`
- `MEDIA_UPLOAD_HOST`

In the verified local rerun, the active host IP was:

- `192.168.1.108`

---

## Preflight

Before rerunning, verify:

- Docker Desktop is running
- the repository root is the current working directory
- `iot-layer/weight-vision-service/.env` still contains the expected non-IP parameters
- `iot-layer/weight-vision-capture/data/metadata/` contains reusable metadata files

Quick parameter check:

```powershell
Get-Content iot-layer\weight-vision-service\.env
```

---

## Step 1: Start the Cloud chain

Run from repository root:

```powershell
$env:CLOUD_AUTH_MODE='api_key'
$env:CLOUD_API_KEYS='edge-local-key'
$env:INTERNAL_SERVICE_TOKEN='farmiq-internal-dev-token'

docker compose -f cloud-layer/docker-compose.yml -f cloud-layer/docker-compose.dev.yml up -d --build `
  postgres `
  rabbitmq `
  cloud-identity-access `
  cloud-tenant-registry `
  cloud-ingestion `
  cloud-telemetry-service `
  cloud-config-rules-service `
  cloud-weighvision-readmodel `
  cloud-reporting-export-service `
  cloud-api-gateway-bff `
  cloud-ml-model-service
```

Expected services:

- `cloud-identity-access`
- `cloud-tenant-registry`
- `cloud-ingestion`
- `cloud-weighvision-readmodel`
- `cloud-reporting-export-service`
- `cloud-api-gateway-bff`
- `cloud-ml-model-service`

---

## Step 2: Start the Edge chain with `.env`-aligned context

Important:

- `EDGE_SITE_ID` must be set to `st-01`
- `EDGE_CONTEXTS` must use `t-001`, `f-001`, `b-001`, `st-01`
- `edge-sync-forwarder` must point to real `cloud-ingestion`, not `edge-cloud-ingestion-mock`

Run from repository root:

```powershell
$env:EDGE_TENANT_ID='t-001'
$env:EDGE_SITE_ID='st-01'
$env:MODEL_CONTROL_TOKEN='t-001'
$env:EDGE_CLOUD_TOKEN=''
$env:EDGE_CONTEXTS='[{"tenantId":"t-001","farmId":"f-001","barnId":"b-001","siteId":"st-01"}]'
$env:CLOUD_AUTH_MODE='api_key'
$env:CLOUD_API_KEY='edge-local-key'
$env:CLOUD_INGESTION_URL='http://host.docker.internal:5122/api/v1/edge/batch'

docker compose -f edge-layer/docker-compose.yml -f edge-layer/docker-compose.dev.yml up -d --build `
  postgres `
  minio `
  edge-mqtt-broker `
  edge-telemetry-timeseries `
  edge-weighvision-session `
  edge-media-store `
  edge-policy-sync `
  edge-vision-inference `
  edge-sync-forwarder `
  edge-ingress-gateway
```

---

## Step 3: Verify host health

Replace `192.168.1.108` if your current workstation IP changed.

Edge:

```powershell
$results = foreach($p in 5103,5104,5105,5106,5107,5108,5109){
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ("http://192.168.1.108:{0}/api/health" -f $p) -TimeoutSec 10
    [pscustomobject]@{Port=$p; Status=$r.StatusCode}
  } catch {
    [pscustomobject]@{Port=$p; Status=$_.Exception.Message}
  }
}
$results | ConvertTo-Json -Compress
```

Cloud:

```powershell
$results = foreach($p in 5120,5121,5122,5123,5125,5126,5129,5132,5135){
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri ("http://192.168.1.108:{0}/api/health" -f $p) -TimeoutSec 10
    [pscustomobject]@{Port=$p; Status=$r.StatusCode}
  } catch {
    [pscustomobject]@{Port=$p; Status=$_.Exception.Message}
  }
}
$results | ConvertTo-Json -Compress
```

All ports must return `200` before replay.

---

## Step 4: Run one-shot replay with runtime IP overrides

This uses the real `.env` business identifiers and overrides only network targets.

Example with the newest metadata file:

```powershell
$latest = Get-ChildItem 'iot-layer/weight-vision-capture/data/metadata' -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 -ExpandProperty FullName

powershell -ExecutionPolicy Bypass -File 'iot-layer/scripts/inject-mock-capture.ps1' `
  -SourceMetadataPath $latest `
  -TenantId 't-001' `
  -FarmId 'f-001' `
  -BarnId 'b-001' `
  -DeviceId 'wv-001' `
  -StationId 'st-01' `
  -EdgeMediaStoreBaseUrl 'http://192.168.1.108:5106' `
  -EdgeSessionBaseUrl 'http://192.168.1.108:5105' `
  -EdgeVisionInferenceBaseUrl 'http://192.168.1.108:5107' `
  -MqttHosts '192.168.1.108:5100' `
  -MediaUploadHost '192.168.1.108:9000'
```

Expected result:

- JSON summary is returned
- `docs/iot-layer/evidence/inject-mock-capture-*.log` is created

---

## Step 5: Verify one-shot reached Edge and Cloud

Replace `<sessionId>` with the returned `session_id`.

Edge verification:

```powershell
Invoke-RestMethod `
  -Uri 'http://192.168.1.108:5105/api/v1/weighvision/sessions/<sessionId>?tenantId=t-001' `
  -TimeoutSec 15 | ConvertTo-Json -Depth 12
```

Cloud verification:

```powershell
Invoke-RestMethod `
  -Uri 'http://192.168.1.108:5125/api/v1/weighvision/sessions/<sessionId>?tenantId=t-001' `
  -TimeoutSec 15 | ConvertTo-Json -Depth 12
```

Expected result:

- Edge status becomes `finalized`
- Cloud status becomes `FINALIZED`

Note:

- `cloud-api-gateway-bff` may return `404` briefly before `cloud-weighvision-readmodel` materializes the session
- this is expected eventual consistency, not an automatic failure

---

## Step 6: Run a repeated 5-session loop

This loop replays the latest 5 metadata files and waits for each session to appear in Cloud.

```powershell
$files = Get-ChildItem 'iot-layer/weight-vision-capture/data/metadata' -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5

$summaries = @()

foreach($file in $files){
  $json = powershell -ExecutionPolicy Bypass -File 'iot-layer/scripts/inject-mock-capture.ps1' `
    -SourceMetadataPath $file.FullName `
    -TenantId 't-001' `
    -FarmId 'f-001' `
    -BarnId 'b-001' `
    -DeviceId 'wv-001' `
    -StationId 'st-01' `
    -EdgeMediaStoreBaseUrl 'http://192.168.1.108:5106' `
    -EdgeSessionBaseUrl 'http://192.168.1.108:5105' `
    -EdgeVisionInferenceBaseUrl 'http://192.168.1.108:5107' `
    -MqttHosts '192.168.1.108:5100' `
    -MediaUploadHost '192.168.1.108:9000'

  $result = $json | ConvertFrom-Json
  $sessionId = $result.session_id
  $edgeStatus = $null
  $cloudStatus = $null
  $cloudCreatedAt = $null
  $cloudMeasurementCount = $null

  for($i=0; $i -lt 30; $i++){
    if(-not $edgeStatus){
      try {
        $edge = Invoke-RestMethod -Uri ("http://192.168.1.108:5105/api/v1/weighvision/sessions/{0}?tenantId=t-001" -f $sessionId) -TimeoutSec 10
        $edgeStatus = $edge.status
      } catch {}
    }

    try {
      $cloud = Invoke-RestMethod -Uri ("http://192.168.1.108:5125/api/v1/weighvision/sessions/{0}?tenantId=t-001" -f $sessionId) -TimeoutSec 10
      $cloudStatus = $cloud.status
      $cloudCreatedAt = $cloud.createdAt
      if($cloud.measurements){ $cloudMeasurementCount = @($cloud.measurements).Count } else { $cloudMeasurementCount = 0 }
      break
    } catch {}

    Start-Sleep -Seconds 2
  }

  $summaries += [pscustomobject]@{
    metadata_file = $file.Name
    session_id = $sessionId
    edge_status = $edgeStatus
    cloud_status = $cloudStatus
    cloud_created_at = $cloudCreatedAt
    cloud_measurements = $cloudMeasurementCount
    log_path = $result.log_path
  }
}

$summaries | ConvertTo-Json -Depth 6
```

Expected result:

- every row returns `edge_status = finalized`
- every row returns `cloud_status = FINALIZED`
- every row returns `cloud_measurements = 1`

---

## Verified reference result

The production-like local rerun validated on Friday, July 17, 2026 produced:

- one-shot replay success for `sess-mock-56a35128b05a4df4b415f94acaa73af7`
- successful 5-session loop with Cloud finalization for every session

Reference evidence files:

- `docs/iot-layer/evidence/inject-mock-capture-20260717-142506.log`
- `docs/iot-layer/evidence/inject-mock-capture-20260717-142822.log`
- `docs/iot-layer/evidence/inject-mock-capture-20260717-142839.log`
- `docs/iot-layer/evidence/inject-mock-capture-20260717-142938.log`
- `docs/iot-layer/evidence/inject-mock-capture-20260717-143037.log`
- `docs/iot-layer/evidence/inject-mock-capture-20260717-143138.log`

---

## Known pitfalls

- Do not use `edge-layer/docker-compose.batch5-e2e.yml` for this flow; it hard-wires `tenant-batch5-e2e`
- Do not rely on `scripts/iot-origin-e2e-html-report.ps1` for this flow without adapting its parameters; it is batch5-oriented
- `EDGE_SITE_ID` must be `st-01`, not a batch5 site ID
- `edge-sync-forwarder` must point to `cloud-ingestion`, not `edge-cloud-ingestion-mock`
- `cloud-api-gateway-bff` may return `404` temporarily while `cloud-weighvision-readmodel` catches up

---

## Related documents

- `docs/iot-layer/16-mock-capture-injection-runbook.md`
- `docs/iot-layer/13-cloud-edge-ai-control-plane-runbook.md`
- `iot-layer/README.md`
