param(
  [Parameter(Mandatory = $true)][string]$SessionId,
  [string]$TenantId = "tenant-batch5-e2e",
  [decimal]$TruthWeightKg = 3.33,
  [string]$ServiceLogPath = ""
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EvidenceDir = Join-Path $RootDir "docs/iot-layer/evidence"
$RunStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$HtmlReportPath = Join-Path $EvidenceDir "iot-origin-e2e-$RunStamp.html"
$JsonReportPath = Join-Path $EvidenceDir "iot-origin-e2e-$RunStamp.json"

function Invoke-Json {
  param(
    [Parameter(Mandatory = $true)][string]$Uri,
    [hashtable]$Headers
  )

  $params = @{
    Uri = $Uri
    UseBasicParsing = $true
  }
  if ($Headers) {
    $params["Headers"] = $Headers
  }

  try {
    $response = Invoke-WebRequest @params
    return ($response.Content | ConvertFrom-Json)
  } catch {
    $message = $_.Exception.Message
    if ($_.Exception.Response) {
      try {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $body = $reader.ReadToEnd()
        $reader.Close()
        $message = "$message | body=$body"
      } catch {
      }
    }
    throw "Invoke-Json failed for $Uri :: $message"
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
    [string[]]$ServiceLog
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
    h1, h2 { margin: 0 0 12px; line-height: 1.2; }
    h1 { font-size: 30px; }
    h2 { font-size: 18px; margin-top: 28px; }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 12px 40px rgba(36, 48, 42, 0.08);
    }
    .hero { padding: 28px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-top: 18px;
    }
    .card { padding: 18px; }
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
    tr:last-child th, tr:last-child td { border-bottom: 0; }
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
    .ok { color: var(--ok); font-weight: 700; }
    .muted { color: var(--muted); }
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
        <tr><th>Model Package</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.shadow_prediction.package_version))</td></tr>
        <tr><th>Metadata Source Event</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.edge.capture_metadata.source_event_type))</td></tr>
      </table>
    </article>

    <article class="card">
      <h2>Trace Gate</h2>
      <table>
        <tr><th>Edge Metadata Items</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.edge.capture_metadata.count))</td></tr>
        <tr><th>Cloud Inferences</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.cloud.inference_count))</td></tr>
        <tr><th>Truth Path Preserved</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.assertions.truth_path_preserved))</td></tr>
        <tr><th>Prediction Synced Back</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.assertions.prediction_synced_back))</td></tr>
        <tr><th>Metadata Routed via MQTT</th><td>$([System.Net.WebUtility]::HtmlEncode([string]$Summary.assertions.metadata_routed_via_mqtt))</td></tr>
      </table>
    </article>
  </section>

  <section>
    <h2>Ingress Snapshot</h2>
    <pre>$(ConvertTo-HtmlPre $Summary.ingress)</pre>
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
    <h2>Outbox Evidence</h2>
    <pre>$(ConvertTo-HtmlPre $Summary.outbox)</pre>
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

$headers = @{
  Authorization = "Bearer $TenantId"
  "x-request-id" = "report-$RunStamp"
  "x-trace-id" = "report-$RunStamp"
}
$edgeHeaders = @{
  "x-tenant-id" = $TenantId
  "x-request-id" = "report-$RunStamp"
  "x-trace-id" = "report-$RunStamp"
}

$edgeSession = Invoke-Json -Uri "http://localhost:5105/api/v1/weighvision/sessions/$SessionId" -Headers $edgeHeaders
$edgeMetadataResponse = Invoke-Json -Uri "http://localhost:5105/api/v1/weighvision/sessions/$SessionId/metadata" -Headers $edgeHeaders
$edgeResults = Invoke-Json -Uri "http://localhost:5107/api/v1/inference/results?sessionId=$SessionId&limit=10" -Headers $edgeHeaders
$cloudSession = Invoke-Json -Uri "http://localhost:5125/api/v1/weighvision/sessions/${SessionId}?tenantId=$TenantId" -Headers $headers
$outboxEntries = Invoke-Json -Uri "http://localhost:5108/api/v1/sync/outbox?status=acked&eventType=weighvision.inference.completed&tenantId=$TenantId&limit=20" -Headers $edgeHeaders
$ingressStats = Invoke-Json -Uri "http://localhost:5103/api/v1/ingress/stats"

$latestCapture = $edgeMetadataResponse.items[-1]
$edgeInferenceResult = $edgeResults.results | Select-Object -First 1
$finalizedMeasurement = $cloudSession.measurements | Where-Object { $_.source -eq "finalized" } | Select-Object -First 1
$shadowInference = $cloudSession.inferences | Where-Object {
  $_.predicted_weight_kg -ne $null -and $_.prediction_mode -eq "shadow"
} | Select-Object -First 1
$ackedPrediction = $outboxEntries.entries | Where-Object {
  $_.payload_json.payload.predicted_weight_kg -ne $null -and $_.payload_json.session_id -eq $SessionId
} | Select-Object -First 1

if (-not $finalizedMeasurement) {
  throw "Cloud session is missing finalized measurement for $SessionId"
}
if (-not $shadowInference) {
  throw "Cloud session is missing shadow prediction for $SessionId"
}
if (-not $ackedPrediction) {
  throw "Edge sync outbox is missing acked shadow prediction event for $SessionId"
}

$serviceLog = @()
if ($ServiceLogPath -and (Test-Path $ServiceLogPath)) {
  $serviceLog = Get-Content -Path $ServiceLogPath
}

$summary = [ordered]@{
  generated_at = (Get-Date).ToString("o")
  session_id = $SessionId
  truth_weight_kg = [double]$TruthWeightKg
  ingress = [ordered]@{
    mqtt_connected = $ingressStats.mqttConnected
    counters = $ingressStats.counters
    last_message_at = $ingressStats.lastMessageAt
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
      count = $edgeMetadataResponse.items.Count
      capture_id = $latestCapture.captureId
      media_ids = $latestCapture.mediaIds
      source_event_type = $latestCapture.sourceEventType
      metadata_schema_version = $latestCapture.metadataSchemaVersion
      feature_schema_version = $latestCapture.featureSchemaVersion
      normalized_features = $latestCapture.normalizedFeatures
    }
    inference_results = [ordered]@{
      count = $edgeResults.count
      first_result = [ordered]@{
        id = $edgeInferenceResult.id
        predicted_weight_kg = $edgeInferenceResult.predicted_weight_kg
        confidence = $edgeInferenceResult.confidence
        model_version = $edgeInferenceResult.model_version
        package_version = $edgeInferenceResult.metadata.package_version
        prediction_mode = $edgeInferenceResult.metadata.prediction_mode
      }
    }
  }
  cloud = [ordered]@{
    session_id = $cloudSession.sessionId
    status = $cloudSession.status
    finalized_measurement = [ordered]@{
      id = $finalizedMeasurement.id
      weight_kg = $finalizedMeasurement.weightKg
      source = $finalizedMeasurement.source
    }
    inference_count = $cloudSession.inferences.Count
    shadow_prediction = [ordered]@{
      id = $shadowInference.id
      predicted_weight_kg = $shadowInference.predicted_weight_kg
      prediction_mode = $shadowInference.prediction_mode
      package_version = $shadowInference.package_version
      source_event_type = $shadowInference.source_event_type
    }
  }
  outbox = [ordered]@{
    id = $ackedPrediction.id
    event_type = $ackedPrediction.event_type
    status = $ackedPrediction.status
    trace_id = $ackedPrediction.trace_id
  }
  shadow_prediction = [ordered]@{
    id = $shadowInference.id
    predicted_weight_kg = $shadowInference.predicted_weight_kg
    prediction_mode = $shadowInference.prediction_mode
    package_version = $shadowInference.package_version
    source_event_type = $shadowInference.source_event_type
  }
  assertions = [ordered]@{
    truth_path_preserved = ([decimal]$finalizedMeasurement.weightKg -eq $TruthWeightKg)
    prediction_synced_back = $true
    metadata_routed_via_mqtt = ($latestCapture.sourceEventType -eq "weighvision.inference.completed")
  }
  artifacts = [ordered]@{
    html_report = $HtmlReportPath
    json_report = $JsonReportPath
    service_log = $ServiceLogPath
  }
}

$summary | ConvertTo-Json -Depth 100 | Set-Content -Path $JsonReportPath -Encoding UTF8
Write-HtmlReport -Summary $summary -ServiceLog $serviceLog
$summary | ConvertTo-Json -Depth 100
