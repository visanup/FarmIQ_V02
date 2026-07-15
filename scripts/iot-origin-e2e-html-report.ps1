param(
  [switch]$Up,
  [string]$SourceMetadataPath = "iot-layer/weight-vision-capture/data/metadata/20260210_073143.json",
  [decimal]$TruthWeightKg = 3.33,
  [string]$TenantId = "tenant-batch5-e2e",
  [string]$FarmId = "farm-batch5-e2e",
  [string]$BarnId = "barn-batch5-e2e",
  [string]$SiteId = "site-batch5-e2e",
  [string]$WvDeviceId = "wv-iot-origin-e2e",
  [string]$StationId = "station-iot-origin-e2e"
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ServiceDir = Join-Path $RootDir "iot-layer/weight-vision-service"
$EvidenceDir = Join-Path $RootDir "docs/iot-layer/evidence"
$SourceMetadataFullPath = (Resolve-Path (Join-Path $RootDir $SourceMetadataPath)).Path
$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$RunId = [System.Guid]::NewGuid().ToString("N")
$SessionId = "sess-iot-origin-$RunId"
$TraceId = "trace-iot-origin-$RunId"
$RequestId = "req-iot-origin-$RunId"
$PackageVersion = "wv-shadow-iot-origin-$RunStamp"
$HtmlReportPath = Join-Path $EvidenceDir "iot-origin-e2e-$RunStamp.html"
$JsonReportPath = Join-Path $EvidenceDir "iot-origin-e2e-$RunStamp.json"
$LogPath = Join-Path $EvidenceDir "iot-origin-e2e-$RunStamp.log"
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "farmiq-iot-origin-e2e-$RunId"
$CaptureRoot = Join-Path $TempRoot "capture-data"
$MetadataDir = Join-Path $CaptureRoot "metadata"
$ImagesDir = Join-Path $CaptureRoot "images"
$StateDir = Join-Path $TempRoot "state"
$BufferDir = Join-Path $TempRoot "buffer"
$SourceImageId = ""

$CloudComposeFiles = @(
  (Join-Path $RootDir "cloud-layer/docker-compose.yml"),
  (Join-Path $RootDir "cloud-layer/docker-compose.batch5-e2e.yml")
)
$EdgeComposeFiles = @(
  (Join-Path $RootDir "edge-layer/docker-compose.yml"),
  (Join-Path $RootDir "edge-layer/docker-compose.dev.yml"),
  (Join-Path $RootDir "edge-layer/docker-compose.batch5-e2e.yml")
)

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
  }

  if ($Headers) {
    $params["Headers"] = $Headers
  }

  if ($null -ne $Body) {
    $params["ContentType"] = "application/json"
    $params["Body"] = ($Body | ConvertTo-Json -Depth 100)
  }

  return Invoke-RestMethod @params
}

function Wait-Healthy {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [int]$TimeoutSeconds = 240
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -Uri $Uri -Method Get -UseBasicParsing -TimeoutSec 5
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
        return
      }
    } catch {
    }
    Start-Sleep -Seconds 2
  }

  throw "Timed out waiting for health: $Uri"
}

function Wait-Until {
  param(
    [Parameter(Mandatory = $true)][scriptblock]$Condition,
    [Parameter(Mandatory = $true)][string]$Description,
    [int]$TimeoutSeconds = 240,
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

function Get-ComposeArgs {
  param([string[]]$Files)
  $args = @()
  foreach ($file in $Files) {
    $args += @("-f", $file)
  }
  return $args
}

function Start-RequiredStack {
  $cloudArgs = Get-ComposeArgs -Files $CloudComposeFiles
  $edgeArgs = Get-ComposeArgs -Files $EdgeComposeFiles

  & docker compose @cloudArgs up -d --build postgres rabbitmq cloud-ingestion cloud-weighvision-readmodel cloud-ml-model-service cloud-api-gateway-bff
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to start required cloud services"
  }

  & docker compose @edgeArgs up -d --build postgres minio edge-mqtt-broker edge-ingress-gateway edge-telemetry-timeseries edge-weighvision-session edge-media-store edge-vision-inference edge-sync-forwarder edge-policy-sync
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to start required edge services"
  }
}

function Seed-Allowlists {
  $edgeArgs = Get-ComposeArgs -Files $EdgeComposeFiles
  $postgresUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "farmiq" }
  $postgresDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "farmiq" }
  $sql = @"
INSERT INTO device_allowlist (tenant_id, device_id, farm_id, barn_id, enabled, created_at, updated_at)
VALUES ('$TenantId', '$WvDeviceId', '$FarmId', '$BarnId', TRUE, NOW(), NOW())
ON CONFLICT (tenant_id, device_id) DO UPDATE
SET enabled = TRUE,
    farm_id = EXCLUDED.farm_id,
    barn_id = EXCLUDED.barn_id,
    updated_at = NOW();

INSERT INTO station_allowlist (tenant_id, station_id, farm_id, barn_id, enabled, created_at, updated_at)
VALUES ('$TenantId', '$StationId', '$FarmId', '$BarnId', TRUE, NOW(), NOW())
ON CONFLICT (tenant_id, station_id) DO UPDATE
SET enabled = TRUE,
    farm_id = EXCLUDED.farm_id,
    barn_id = EXCLUDED.barn_id,
    updated_at = NOW();
"@

  & docker compose @edgeArgs exec -T postgres psql -U $postgresUser -d $postgresDb -v ON_ERROR_STOP=1 -c $sql | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to seed device/station allowlists"
  }
}

function New-MockCapture {
  New-Item -ItemType Directory -Force -Path $MetadataDir, $ImagesDir, $StateDir, $BufferDir | Out-Null

  $sourceMetadata = Get-Content -Path $SourceMetadataFullPath -Raw | ConvertFrom-Json
  $script:SourceImageId = [string]$sourceMetadata.image_id
  $timestampIso = (Get-Date).ToUniversalTime().ToString("o")

  $sourceMetadata.timestamp = $timestampIso
  $sourceMetadata.image_id = $SessionId
  if ($sourceMetadata.PSObject.Properties.Name -contains "session_id") {
    $sourceMetadata.session_id = $SessionId
  } else {
    Add-Member -InputObject $sourceMetadata -NotePropertyName "session_id" -NotePropertyValue $SessionId
  }
  if ($sourceMetadata.PSObject.Properties.Name -contains "batch_id") {
    $sourceMetadata.batch_id = "batch-iot-origin-e2e"
  } else {
    Add-Member -InputObject $sourceMetadata -NotePropertyName "batch_id" -NotePropertyValue "batch-iot-origin-e2e"
  }

  if (-not $sourceMetadata.scale) {
    Add-Member -InputObject $sourceMetadata -NotePropertyName "scale" -NotePropertyValue ([pscustomobject]@{})
  }
  if ($sourceMetadata.scale.PSObject.Properties.Name -contains "weight_kg") {
    $sourceMetadata.scale.weight_kg = [double]$TruthWeightKg
  } else {
    Add-Member -InputObject $sourceMetadata.scale -NotePropertyName "weight_kg" -NotePropertyValue ([double]$TruthWeightKg)
  }
  if ($sourceMetadata.scale.PSObject.Properties.Name -contains "weight_source") {
    $sourceMetadata.scale.weight_source = "mock_load_cell"
  } else {
    Add-Member -InputObject $sourceMetadata.scale -NotePropertyName "weight_source" -NotePropertyValue "mock_load_cell"
  }

  $metadataTargetPath = Join-Path $MetadataDir "$SessionId.json"
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText(
    $metadataTargetPath,
    ($sourceMetadata | ConvertTo-Json -Depth 100),
    $utf8NoBom
  )

  $sourceImageDir = Join-Path (Split-Path (Split-Path $SourceMetadataFullPath -Parent) -Parent) "images"
  $sourceFiles = Get-ChildItem -Path $sourceImageDir -Filter "$SourceImageId`_*.*"
  if (-not $sourceFiles) {
    throw "No source images found for image_id=$SourceImageId"
  }

  $copiedImages = @()
  foreach ($file in $sourceFiles) {
    $suffix = $file.Name.Substring($SourceImageId.Length)
    $target = Join-Path $ImagesDir "$SessionId$suffix"
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    $copiedImages += $target
  }

  return [ordered]@{
    metadata_path = $metadataTargetPath
    capture_root = $CaptureRoot
    copied_images = $copiedImages
    timestamp = $timestampIso
  }
}

function Get-IngressStats {
  try {
    return Invoke-Json -Method GET -Uri "http://localhost:5103/api/v1/ingress/stats"
  } catch {
    return $null
  }
}

function Set-ServiceEnv {
  param(
    [Parameter(Mandatory = $true)][string]$MetadataPath
  )

  $env:TENANT_ID = $TenantId
  $env:FARM_ID = $FarmId
  $env:BARN_ID = $BarnId
  $env:DEVICE_ID = $WvDeviceId
  $env:STATION_ID = $StationId
  $env:MQTT_HOSTS = "127.0.0.1:5100"
  $env:MQTT_PORT = "5100"
  $env:EDGE_MEDIA_STORE_BASE_URL = "http://localhost:5106"
  $env:EDGE_SESSION_BASE_URL = "http://localhost:5105"
  $env:CAPTURE_DATA_DIR = $CaptureRoot
  $env:STATE_DIR = $StateDir
  $env:EVENT_BUFFER_DIR = $BufferDir
  $env:DRY_RUN = "false"
  $env:STATUS_PUBLISH_ENABLED = "false"
  $env:METADATA_FILE_ONCE = $MetadataPath
  $env:MEDIA_UPLOAD_HOST = "localhost:9000"
  $env:NO_PROXY = "localhost,127.0.0.1"
  $env:no_proxy = "localhost,127.0.0.1"
}

function Invoke-WeightVisionService {
  param(
    [Parameter(Mandatory = $true)][string]$MetadataPath
  )

  Set-ServiceEnv -MetadataPath $MetadataPath
  Push-Location $ServiceDir
  try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
      $output = & python run_service.py 2>&1
      $exitCode = $LASTEXITCODE
    } finally {
      $ErrorActionPreference = $previousErrorActionPreference
    }
    @($output | ForEach-Object { $_.ToString() }) | Set-Content -Path $LogPath -Encoding UTF8
    if ($exitCode -ne 0) {
      throw "weight-vision-service exited with code $exitCode"
    }
    return $output
  } finally {
    Pop-Location
  }
}

function ConvertTo-PrettyJson {
  param($Value)
  return ($Value | ConvertTo-Json -Depth 100)
}

function ConvertTo-HtmlPre {
  param($Value)
  return [System.Net.WebUtility]::HtmlEncode((ConvertTo-PrettyJson $Value))
}

function Write-HtmlReport {
  param(
    [Parameter(Mandatory = $true)]$Summary,
    [Parameter(Mandatory = $true)]$ServiceLog
  )

  $serviceLogText = if ($ServiceLog) {
    [System.Net.WebUtility]::HtmlEncode(($ServiceLog -join [Environment]::NewLine))
  } else {
    ""
  }

  $html = @"
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>FarmIQ IoT-Origin E2E Report</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --line: #d3c8b8;
      --ink: #1b2421;
      --muted: #5b655f;
      --accent: #275d4f;
      --accent-soft: #dbe8e2;
      --ok: #0e6b46;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 32px;
      background: linear-gradient(180deg, #f4f1ea 0%, #ebe3d5 100%);
      color: var(--ink);
      font: 14px/1.5 "Segoe UI", "Noto Sans Thai", sans-serif;
    }
    h1, h2, h3 {
      margin: 0 0 12px;
      line-height: 1.2;
    }
    h1 { font-size: 30px; }
    h2 { font-size: 18px; margin-top: 28px; }
    .hero {
      padding: 28px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 18px;
      box-shadow: 0 12px 40px rgba(36, 48, 42, 0.08);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-top: 18px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px;
    }
    .badge {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 700;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      font-size: 12px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      background: var(--panel);
      border-radius: 14px;
      overflow: hidden;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      width: 240px;
      color: var(--muted);
      font-weight: 600;
    }
    tr:last-child th, tr:last-child td {
      border-bottom: 0;
    }
    pre {
      margin: 0;
      padding: 16px;
      background: #17201d;
      color: #ecf3ef;
      border-radius: 16px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .ok {
      color: var(--ok);
      font-weight: 700;
    }
    .muted {
      color: var(--muted);
    }
  </style>
</head>
<body>
  <section class="hero">
    <span class="badge">IoT-Origin E2E</span>
    <h1>FarmIQ WeighVision End-to-End Verification</h1>
    <p class="muted">Report generated at $([System.Net.WebUtility]::HtmlEncode([string]$Summary.generated_at))</p>
    <p><span class="ok">PASS</span> IoT-layer mock capture delivered image + weight into Edge, metadata routed through MQTT/ingress, shadow prediction executed on Edge, and outcome synced back to Cloud.</p>
  </section>

  <section class="grid">
    <article class="card">
      <h2>Run Summary</h2>
      <table>
        <tr><th>Session ID</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.session_id))</td></tr>
        <tr><th>Truth Weight (kg)</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.truth_weight_kg))</td></tr>
        <tr><th>Shadow Prediction (kg)</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.shadow_prediction.predicted_weight_kg))</td></tr>
        <tr><th>Model Package</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.model_control.trained_package_version))</td></tr>
        <tr><th>Metadata Source Event</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.edge.capture_metadata.source_event_type))</td></tr>
      </table>
    </article>

    <article class="card">
      <h2>Trace Gate</h2>
      <table>
        <tr><th>Ingress Processed Delta</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.ingress.processed_delta))</td></tr>
        <tr><th>Edge Metadata Items</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.edge.capture_metadata.count))</td></tr>
        <tr><th>Cloud Inferences</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.cloud.inference_count))</td></tr>
        <tr><th>Final Truth Preserved</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.assertions.truth_path_preserved))</td></tr>
        <tr><th>Prediction Synced Back</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.assertions.prediction_synced_back))</td></tr>
      </table>
    </article>
  </section>

  <section>
    <h2>Control Plane</h2>
    <pre>$(ConvertTo-HtmlPre $Summary.model_control)</pre>
  </section>

  <section>
    <h2>Mock Capture Input</h2>
    <pre>$(ConvertTo-HtmlPre $Summary.mock_capture)</pre>
  </section>

  <section>
    <h2>Edge Verification</h2>
    <pre>$(ConvertTo-HtmlPre $Summary.edge)</pre>
  </section>

  <section>
    <h2>Cloud Verification</h2>
    <pre>$(ConvertTo-HtmlPre $Summary.cloud)</pre>
  </section>

  <section>
    <h2>Service Log</h2>
    <pre>$serviceLogText</pre>
  </section>
</body>
</html>
"@

  Set-Content -Path $HtmlReportPath -Value $html -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

if ($Up) {
  Start-RequiredStack
}

Wait-Healthy "http://localhost:5135/api/health"
Wait-Healthy "http://localhost:5132/api/health"
Wait-Healthy "http://localhost:5122/api/health"
Wait-Healthy "http://localhost:5125/api/health"
Wait-Healthy "http://localhost:5108/api/health"
Wait-Healthy "http://localhost:5109/api/health"
Wait-Healthy "http://localhost:5107/api/health"
Wait-Healthy "http://localhost:5106/api/health"
Wait-Healthy "http://localhost:5105/api/health"
Wait-Healthy "http://localhost:5103/api/health"

Seed-Allowlists

$bffHeaders = @{
  Authorization = "Bearer $TenantId"
  "x-request-id" = $RequestId
  "x-trace-id" = $TraceId
}
$edgeTenantHeaders = @{
  "x-tenant-id" = $TenantId
  "x-request-id" = $RequestId
  "x-trace-id" = $TraceId
}

$ingressBefore = Get-IngressStats

$datasetContract = Invoke-Json -Method GET -Uri "http://localhost:5125/api/v1/weighvision/dataset-contract" -Headers $bffHeaders
$trainResponse = Invoke-Json -Method POST -Uri "http://localhost:5125/api/v1/weighvision/train-baseline" -Headers $bffHeaders -Body @{
  datasetPath = "/workspace-docs/iot-layer/evidence/batch2-weight-audit-dataset.csv"
  packageVersion = $PackageVersion
  channel = "stable"
  approvalState = "published"
}
$package = $trainResponse.package

$subscriptionError = $null
try {
  Invoke-Json -Method PUT -Uri "http://localhost:5125/api/v1/weighvision/model-subscriptions/sites/$SiteId" -Headers $bffHeaders -Body @{
    tenantId = $TenantId
    siteId = $SiteId
    farmId = $FarmId
    barnId = $BarnId
    channel = "pinned"
    pinnedPackageId = $package.id
    fallbackPackageId = $package.id
    notes = "IoT-origin e2e smoke"
  } | Out-Null
} catch {
  $subscriptionError = $_.Exception.Message
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

$mockCapture = New-MockCapture
$serviceLog = Invoke-WeightVisionService -MetadataPath $mockCapture.metadata_path

$edgeSession = Wait-Until -Description "edge session created" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5105/api/v1/weighvision/sessions/$SessionId" -Headers @{}
    if ($null -ne $result.sessionId) {
      return $result
    }
  } catch {
  }
  return $null
}

$edgeMetadata = Wait-Until -Description "edge capture metadata persisted" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5105/api/v1/weighvision/sessions/$SessionId/metadata" -Headers @{}
    if ($result.items.Count -gt 0) {
      return $result
    }
  } catch {
  }
  return $null
}

$latestCapture = $edgeMetadata.items[-1]
$mediaId = $latestCapture.mediaIds[0]
if (-not $mediaId) {
  throw "No mediaId found in persisted capture metadata"
}

$job = Invoke-Json -Method POST -Uri "http://localhost:5107/api/v1/inference/jobs" -Headers $edgeTenantHeaders -Body @{
  tenantId = $TenantId
  farmId = $FarmId
  barnId = $BarnId
  deviceId = $WvDeviceId
  sessionId = $SessionId
  mediaId = $mediaId
}

$jobResult = Wait-Until -Description "inference job completion" -Condition {
  try {
    $state = Invoke-Json -Method GET -Uri "http://localhost:5107/api/v1/inference/jobs/$($job.job_id)" -Headers @{}
    if ($state.status -eq "completed") {
      return $state
    }
    if ($state.status -eq "failed") {
      throw "Inference job failed: $($state.error)"
    }
  } catch {
    throw
  }
  return $null
}

$edgeResults = Invoke-Json -Method GET -Uri "http://localhost:5107/api/v1/inference/results?sessionId=$SessionId&limit=10" -Headers @{}
Invoke-Json -Method POST -Uri "http://localhost:5108/api/v1/sync/trigger" -Headers @{} | Out-Null

$cloudSession = Wait-Until -Description "cloud session with shadow prediction" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5125/api/v1/weighvision/sessions/${SessionId}?tenantId=$TenantId" -Headers $bffHeaders
    if ($null -ne $result.sessionId -and $result.inferences.Count -gt 0) {
      $shadow = $result.inferences | Where-Object {
        $_.predicted_weight_kg -ne $null -and $_.prediction_mode -eq "shadow"
      } | Select-Object -First 1
      if ($shadow) {
        return @{
          session = $result
          shadow = $shadow
        }
      }
    }
  } catch {
  }
  return $null
}

$ackedPrediction = Wait-Until -Description "acked prediction outbox event" -Condition {
  try {
    $result = Invoke-Json -Method GET -Uri "http://localhost:5108/api/v1/sync/outbox?status=acked&eventType=weighvision.inference.completed&tenantId=$TenantId&limit=20" -Headers @{}
    $match = $result.entries | Where-Object {
      $_.payload_json.payload.predicted_weight_kg -ne $null -and $_.payload_json.session_id -eq $SessionId
    } | Select-Object -First 1
    if ($match) {
      return $match
    }
  } catch {
  }
  return $null
}

$ingressAfter = Get-IngressStats
$processedBefore = if ($ingressBefore -and $ingressBefore.counters.messages_valid_total -ne $null) { [int]$ingressBefore.counters.messages_valid_total } else { 0 }
$processedAfter = if ($ingressAfter -and $ingressAfter.counters.messages_valid_total -ne $null) { [int]$ingressAfter.counters.messages_valid_total } else { 0 }
$processedDelta = $processedAfter - $processedBefore
$finalizedMeasurement = $cloudSession.session.measurements | Where-Object { $_.source -eq "finalized" } | Select-Object -First 1
$shadowInference = $cloudSession.shadow
$edgeInferenceResult = $edgeResults.results | Select-Object -First 1

if (-not $finalizedMeasurement) {
  throw "Cloud session is missing finalized measurement for truth-path validation"
}

if ([decimal]$finalizedMeasurement.weightKg -ne $TruthWeightKg) {
  throw "Expected finalized truth path to remain $TruthWeightKg but got $($finalizedMeasurement.weightKg)"
}

if ([decimal]$shadowInference.predicted_weight_kg -eq $TruthWeightKg) {
  throw "Shadow prediction unexpectedly matched the finalized truth path exactly; expected independent values"
}

if ($processedDelta -lt 1) {
  throw "Expected MQTT ingress processed_count to increase, but delta was $processedDelta"
}

$summary = [ordered]@{
  generated_at = (Get-Date).ToString("o")
  session_id = $SessionId
  trace_id = $TraceId
  truth_weight_kg = [double]$TruthWeightKg
  mock_capture = [ordered]@{
    source_metadata_path = $SourceMetadataFullPath
    source_image_id = $SourceImageId
    generated_metadata_path = $mockCapture.metadata_path
    capture_root = $mockCapture.capture_root
    copied_images = $mockCapture.copied_images
    timestamp = $mockCapture.timestamp
  }
  ingress = [ordered]@{
    before = $ingressBefore
    after = $ingressAfter
    processed_delta = $processedDelta
  }
  model_control = [ordered]@{
    dataset_contract_version = $datasetContract.version
    trained_package_id = $package.id
    trained_package_version = $package.packageVersion
    subscription_error = $subscriptionError
    policy_cache_package_id = $policyEntry.data.resolved_json.activePackage.id
    model_refresh = @{
      status = $modelInfo.status
      activation_source = $modelInfo.activation_source
      package_id = $modelInfo.package_id
      package_version = $modelInfo.package_version
    }
  }
  edge = [ordered]@{
    session = [ordered]@{
      session_id = $edgeSession.sessionId
      status = $edgeSession.status
      initial_weight_kg = $edgeSession.initialWeightKg
      final_weight_kg = $edgeSession.finalWeightKg
      image_count = $edgeSession.imageCount
      inference_result_id = $edgeSession.inferenceResultId
    }
    capture_metadata = [ordered]@{
      count = $edgeMetadata.items.Count
      capture_id = $latestCapture.captureId
      media_id = $mediaId
      media_ids = $latestCapture.mediaIds
      source_event_type = $latestCapture.sourceEventType
      feature_schema_version = $latestCapture.featureSchemaVersion
      metadata_schema_version = $latestCapture.metadataSchemaVersion
      normalized_features = $latestCapture.normalizedFeatures
    }
    inference_job = [ordered]@{
      job_id = $jobResult.job_id
      status = $jobResult.status
      result_id = $jobResult.result_id
      media_id = $jobResult.media_id
    }
    inference_results = [ordered]@{
      count = $edgeResults.count
      first_result = if ($edgeInferenceResult) {
        [ordered]@{
          id = $edgeInferenceResult.id
          predicted_weight_kg = $edgeInferenceResult.predicted_weight_kg
          confidence = $edgeInferenceResult.confidence
          model_version = $edgeInferenceResult.model_version
          prediction_mode = $edgeInferenceResult.metadata.prediction_mode
          package_version = $edgeInferenceResult.metadata.package_version
          fallback_engaged = $edgeInferenceResult.metadata.fallback_engaged
        }
      } else {
        $null
      }
    }
    acked_prediction_event = @{
      id = $ackedPrediction.id
      event_type = $ackedPrediction.event_type
      status = $ackedPrediction.status
    }
  }
  cloud = [ordered]@{
    session_id = $cloudSession.session.sessionId
    status = $cloudSession.session.status
    finalized_measurement = [ordered]@{
      id = $finalizedMeasurement.id
      weight_kg = $finalizedMeasurement.weightKg
      source = $finalizedMeasurement.source
    }
    inference_count = $cloudSession.session.inferences.Count
    shadow_prediction = [ordered]@{
      id = $shadowInference.id
      predicted_weight_kg = $shadowInference.predicted_weight_kg
      prediction_mode = $shadowInference.prediction_mode
      package_version = $shadowInference.package_version
      source_event_type = $shadowInference.source_event_type
    }
  }
  shadow_prediction = [ordered]@{
    id = $shadowInference.id
    predicted_weight_kg = $shadowInference.predicted_weight_kg
    prediction_mode = $shadowInference.prediction_mode
    package_version = $shadowInference.package_version
    source_event_type = $shadowInference.source_event_type
  }
  assertions = [ordered]@{
    truth_path_preserved = $true
    prediction_synced_back = $true
    ingress_trace_confirmed = $processedDelta -ge 1
    metadata_routed_via_mqtt = $latestCapture.sourceEventType -eq "weighvision.inference.completed"
  }
  artifacts = [ordered]@{
    html_report = $HtmlReportPath
    json_report = $JsonReportPath
    service_log = $LogPath
  }
}

$summary | ConvertTo-Json -Depth 100 | Set-Content -Path $JsonReportPath -Encoding UTF8
Write-HtmlReport -Summary $summary -ServiceLog $serviceLog
$summary | ConvertTo-Json -Depth 100
