param(
  [string]$TenantId = "tenant-batch5-e2e",
  [string]$FarmId = "farm-batch5-e2e",
  [string]$BarnId = "barn-batch5-e2e",
  [string]$SiteId = "site-batch5-e2e",
  [string]$DeviceId = "device-batch5-e2e",
  [string]$StationId = "station-batch5-e2e"
)

$ErrorActionPreference = "Stop"

function Invoke-Json {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Uri,
    [hashtable]$Headers,
    $Body
  )

  $params = @{
    Method = $Method
    Uri = $Uri
    Headers = $Headers
  }

  if ($null -ne $Body) {
    $params["ContentType"] = "application/json"
    $params["Body"] = ($Body | ConvertTo-Json -Depth 20)
  }

  return Invoke-RestMethod @params
}

function Wait-Healthy {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [int]$TimeoutSeconds = 180
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Uri -Method Get -UseBasicParsing -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        return
      }
    } catch {
      Start-Sleep -Seconds 2
    }
  }

  throw "Timed out waiting for health: $Uri"
}

function Wait-Until {
  param(
    [scriptblock]$Condition,
    [string]$Description,
    [int]$TimeoutSeconds = 180,
    [int]$IntervalSeconds = 3
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $result = & $Condition
    if ($result) {
      return $result
    }
    Start-Sleep -Seconds $IntervalSeconds
  }

  throw "Timed out waiting for: $Description"
}

$traceId = "trace-batch5-e2e"
$requestId = "req-batch5-e2e"
$authHeader = "Bearer $TenantId"
$bffHeaders = @{
  Authorization = $authHeader
  "x-request-id" = $requestId
  "x-trace-id" = $traceId
}
$edgeTenantHeaders = @{
  "x-tenant-id" = $TenantId
  "x-request-id" = $requestId
  "x-trace-id" = $traceId
}

$runId = [System.Guid]::NewGuid().ToString("N")
$finalWeightKg = 3.33
$sessionEventId = [System.Guid]::NewGuid().ToString()
$bindMediaEventId = [System.Guid]::NewGuid().ToString()
$metadataEventId = [System.Guid]::NewGuid().ToString()
$finalizeEventId = [System.Guid]::NewGuid().ToString()

Wait-Healthy "http://localhost:5135/api/health"
Wait-Healthy "http://localhost:5132/api/health"
Wait-Healthy "http://localhost:5122/api/health"
Wait-Healthy "http://localhost:5125/api/health"
Wait-Healthy "http://localhost:5108/api/health"
Wait-Healthy "http://localhost:5109/api/health"
Wait-Healthy "http://localhost:5107/api/health"
Wait-Healthy "http://localhost:5106/api/health"
Wait-Healthy "http://localhost:5105/api/health"

$datasetContract = Invoke-Json -Method GET -Uri "http://localhost:5125/api/v1/weighvision/dataset-contract" -Headers $bffHeaders

$trainResponse = Invoke-Json -Method POST -Uri "http://localhost:5125/api/v1/weighvision/train-baseline" -Headers $bffHeaders -Body @{
  datasetPath = "/workspace-docs/iot-layer/evidence/batch2-weight-audit-dataset.csv"
  packageVersion = "wv-shadow-batch5-e2e-2026.07.14"
  channel = "stable"
  approvalState = "published"
}

$package = $trainResponse.package

$subscription = Invoke-Json -Method PUT -Uri "http://localhost:5125/api/v1/weighvision/model-subscriptions/sites/$SiteId" -Headers $bffHeaders -Body @{
  tenantId = $TenantId
  siteId = $SiteId
  farmId = $FarmId
  barnId = $BarnId
  channel = "pinned"
  pinnedPackageId = $package.id
  fallbackPackageId = $package.id
  notes = "Batch5 e2e smoke"
}

$policyEntry = Wait-Until -Description "edge policy sync cache entry" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5109/api/v1/edge-config/model-subscription/effective?tenantId=$TenantId&siteId=$SiteId"
    if ($result.data.resolved_json.activePackage.id -eq $package.id) {
      return $result
    }
  } catch {
  }
  return $null
}

$modelInfo = Invoke-Json -Method POST -Uri "http://localhost:5107/api/v1/inference/models/refresh" -Headers @{}

$sessionId = "sess-batch5-e2e-$runId"
$captureId = "cap-batch5-e2e-$runId"
$now = (Get-Date).ToUniversalTime().ToString("o")

Invoke-Json -Method POST -Uri "http://localhost:5105/api/v1/weighvision/sessions" -Headers @{} -Body @{
  sessionId = $sessionId
  eventId = $sessionEventId
  tenantId = $TenantId
  farmId = $FarmId
  barnId = $BarnId
  deviceId = $DeviceId
  stationId = $StationId
  batchId = "batch5-e2e"
  startAt = $now
} | Out-Null

$presign = Invoke-Json -Method POST -Uri "http://localhost:5106/api/v1/media/images/presign" -Headers $edgeTenantHeaders -Body @{
  tenant_id = $TenantId
  farm_id = $FarmId
  barn_id = $BarnId
  device_id = $DeviceId
  session_id = $sessionId
  filename = "batch5-e2e.jpg"
  content_type = "image/jpeg"
}

$tempFile = Join-Path ([System.IO.Path]::GetTempPath()) "batch5-e2e-$runId.jpg"
[System.IO.File]::WriteAllBytes($tempFile, [byte[]](0..31))

Invoke-WebRequest -Method Put -Uri $presign.upload_url -InFile $tempFile -ContentType "image/jpeg" -UseBasicParsing | Out-Null

$mediaComplete = Invoke-Json -Method POST -Uri "http://localhost:5106/api/v1/media/images/complete" -Headers $edgeTenantHeaders -Body @{
  tenant_id = $TenantId
  farm_id = $FarmId
  barn_id = $BarnId
  device_id = $DeviceId
  session_id = $sessionId
  object_key = $presign.object_key
  filename = "batch5-e2e.jpg"
  mime_type = "image/jpeg"
  size_bytes = (Get-Item $tempFile).Length
  captured_at = $now
}

Remove-Item -LiteralPath $tempFile -ErrorAction SilentlyContinue

Invoke-Json -Method POST -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId/bind-media" -Headers @{} -Body @{
  tenantId = $TenantId
  mediaObjectId = $mediaComplete.media_id
  occurredAt = $now
  eventId = $bindMediaEventId
} | Out-Null

Invoke-Json -Method POST -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId/metadata" -Headers @{} -Body @{
  tenantId = $TenantId
  farmId = $FarmId
  barnId = $BarnId
  deviceId = $DeviceId
  stationId = $StationId
  eventId = $metadataEventId
  occurredAt = $now
  captureId = $captureId
  mediaIds = @($mediaComplete.media_id)
  metadata = @{
    capture_id = $captureId
    roi_count = 1
    height_estimation = @{
      floor_depth_mm = 1368.858786
    }
    scale = @{
      weight_kg = $finalWeightKg
    }
    detections = @(
      @{
        confidence = 0.9232416
        depth_mm = 1294.8250685
        height_mm = 74.03371786
        width_mm = 96.89757543
        length_mm = 309.40758007
        area_xy_mm2 = 32326.37151748
        average_depth_mm = 1294.8250685
        median_depth_mm = 1294.8250685
        distance_mm = 1294.8250685
        bbox_xyxy = @(10, 20, 110, 220)
        mask_xy = @(
          @(10, 20),
          @(110, 20),
          @(110, 220),
          @(10, 220)
        )
      }
    )
  }
} | Out-Null

$job = Invoke-Json -Method POST -Uri "http://localhost:5107/api/v1/inference/jobs" -Headers $edgeTenantHeaders -Body @{
  tenantId = $TenantId
  farmId = $FarmId
  barnId = $BarnId
  deviceId = $DeviceId
  sessionId = $sessionId
  mediaId = $mediaComplete.media_id
}

$jobResult = Wait-Until -Description "inference job completion" -Condition {
  $state = Invoke-Json -Method GET -Uri "http://localhost:5107/api/v1/inference/jobs/$($job.job_id)" -Headers @{}
  if ($state.status -eq "completed") {
    return $state
  }
  if ($state.status -eq "failed") {
    throw "Inference job failed: $($state.error)"
  }
  return $null
}

Invoke-Json -Method POST -Uri "http://localhost:5105/api/v1/weighvision/sessions/$sessionId/finalize" -Headers @{} -Body @{
  tenantId = $TenantId
  eventId = $finalizeEventId
  occurredAt = (Get-Date).ToUniversalTime().ToString("o")
  finalWeightKg = $finalWeightKg
  payload = @{
    scale = @{
      weight_kg = $finalWeightKg
    }
  }
} | Out-Null

Invoke-Json -Method POST -Uri "http://localhost:5108/api/v1/sync/trigger" -Headers @{} | Out-Null

$cloudSession = Wait-Until -Description "cloud weighvision session with prediction outcome" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5125/api/v1/weighvision/sessions/$sessionId?tenantId=$TenantId" -Headers $bffHeaders
    if ($null -ne $result.sessionId -and $result.inferences.Count -gt 0) {
      $shadowInference = $result.inferences | Where-Object { $_.predicted_weight_kg -ne $null -and $_.prediction_mode -eq "shadow" } | Select-Object -First 1
      if ($shadowInference) {
        return @{
          session = $result
          shadow = $shadowInference
        }
      }
    }
  } catch {
  }
  return $null
} -TimeoutSeconds 240

$ackedPrediction = Wait-Until -Description "acked prediction outcome in sync outbox" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5108/api/v1/sync/outbox?status=acked&eventType=weighvision.inference.completed&tenantId=$TenantId&limit=20" -Headers @{}
    $match = $result.entries | Where-Object { $_.payload_json.payload.predicted_weight_kg -ne $null -and $_.payload_json.session_id -eq $sessionId } | Select-Object -First 1
    if ($match) {
      return $match
    }
  } catch {
  }
  return $null
} -TimeoutSeconds 240

$summary = [ordered]@{
  dataset_contract_version = $datasetContract.version
  trained_package_id = $package.id
  trained_package_version = $package.packageVersion
  policy_cache_package_id = $policyEntry.data.resolved_json.activePackage.id
  model_refresh = @{
    status = $modelInfo.status
    activation_source = $modelInfo.activation_source
    package_id = $modelInfo.package_id
    package_version = $modelInfo.package_version
  }
  session_id = $sessionId
  media_id = $mediaComplete.media_id
  final_weight_kg_truth = $cloudSession.session.final_weight_kg
  inference_job_id = $job.job_id
  shadow_prediction = @{
    predicted_weight_kg = $cloudSession.shadow.predicted_weight_kg
    confidence = $cloudSession.shadow.confidence
    model_version = $cloudSession.shadow.modelVersion
    package_id = $cloudSession.shadow.package_id
    package_version = $cloudSession.shadow.package_version
    feature_schema_version = $cloudSession.shadow.feature_schema_version
    prediction_mode = $cloudSession.shadow.prediction_mode
    activation_source = $cloudSession.shadow.activation_source
    source_event_type = $cloudSession.shadow.source_event_type
  }
  sync_outbox_prediction_event = @{
    id = $ackedPrediction.id
    event_type = $ackedPrediction.event_type
    status = $ackedPrediction.status
  }
}

if ([decimal]$summary.final_weight_kg_truth -ne [decimal]$finalWeightKg) {
  throw "Expected final_weight_kg truth path to remain $finalWeightKg but got $($summary.final_weight_kg_truth)"
}

if ([decimal]$summary.shadow_prediction.predicted_weight_kg -eq [decimal]$summary.final_weight_kg_truth) {
  throw "Shadow prediction unexpectedly matched the finalized truth path exactly; expected independent values for this smoke proof"
}

$summary | ConvertTo-Json -Depth 20
