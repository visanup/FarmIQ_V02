param(
    [string]$BaseComposeFile = "docker-compose.yml",
    [string]$OutputFile = "docker-compose.onsite.yml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$cloudLayerDir = Split-Path -Parent $PSScriptRoot
$baseComposePath = Join-Path $cloudLayerDir $BaseComposeFile
$outputPath = Join-Path $cloudLayerDir $OutputFile
$timestampCulture = [System.Globalization.CultureInfo]::InvariantCulture

if (-not (Test-Path $baseComposePath)) {
    throw "Base compose file not found: $baseComposePath"
}

$serviceImages = [ordered]@{
    "cloud-identity-access"            = "cloud-layer-cloud-identity-access:latest"
    "cloud-tenant-registry"            = "cloud-layer-cloud-tenant-registry:latest"
    "cloud-ingestion"                  = "cloud-layer-cloud-ingestion:latest"
    "cloud-telemetry-service"          = "cloud-layer-cloud-telemetry-service:latest"
    "cloud-analytics-service"          = "cloud-layer-cloud-analytics-service:latest"
    "cloud-config-rules-service"       = "cloud-layer-cloud-config-rules-service:latest"
    "cloud-audit-log-service"          = "cloud-layer-cloud-audit-log-service:latest"
    "cloud-fleet-management"           = "cloud-layer-cloud-fleet-management:latest"
    "cloud-notification-service"       = "cloud-layer-cloud-notification-service:latest"
    "cloud-reporting-export-service"   = "cloud-layer-cloud-reporting-export-service:latest"
    "cloud-feed-service"               = "cloud-layer-cloud-feed-service:latest"
    "cloud-barn-records-service"       = "cloud-layer-cloud-barn-records-service:latest"
    "cloud-weighvision-readmodel"      = "cloud-layer-cloud-weighvision-readmodel:latest"
    "cloud-llm-insights-service"       = "cloud-layer-cloud-llm-insights-service:latest"
    "cloud-ml-model-service"           = "cloud-layer-cloud-ml-model-service:latest"
    "cloud-mlflow-registry"            = "cloud-layer-cloud-mlflow-registry:latest"
    "cloud-feature-store"              = "cloud-layer-cloud-feature-store:latest"
    "cloud-drift-detection"            = "cloud-layer-cloud-drift-detection:latest"
    "cloud-inference-server"           = "cloud-layer-cloud-inference-server:latest"
    "cloud-hybrid-router"              = "cloud-layer-cloud-hybrid-router:latest"
    "cloud-standards-service"          = "cloud-layer-cloud-standards-service:latest"
    "cloud-api-gateway-bff"            = "cloud-layer-cloud-api-gateway-bff:latest"
    "dashboard-web"                    = "cloud-layer-dashboard-web:latest"
    "admin-web"                        = "cloud-layer-admin-web:latest"
    "cloud-billing-service"            = "cloud-layer-cloud-billing-service:latest"
    "cloud-advanced-analytics"         = "cloud-layer-cloud-advanced-analytics:latest"
    "cloud-data-pipeline"              = "cloud-layer-cloud-data-pipeline:latest"
    "cloud-bi-metabase"                = "cloud-layer-cloud-bi-metabase:latest"
}

$content = Get-Content -Path $baseComposePath -Raw

foreach ($entry in $serviceImages.GetEnumerator()) {
    $serviceName = [regex]::Escape($entry.Key)
    $imageName = $entry.Value
    $pattern = "(?m)^  ${serviceName}:\r?\n    build:\r?\n(?:      [^\r\n]+\r?\n)+"

    if ($content -notmatch $pattern) {
        throw "Unable to locate build block for service '$($entry.Key)' in $baseComposePath"
    }

    $replacement = "  $($entry.Key):`r`n    image: $imageName`r`n"
    $content = [regex]::Replace($content, $pattern, $replacement)
}

# Port 5141 belongs to Edge PostgreSQL when Edge and Cloud share an onsite host.
# Hybrid router remains reachable to Cloud services over farmiq-net on port 5140.
$hybridPortPattern = '(?ms)(^  cloud-hybrid-router:\r?\n.*?^    container_name: farmiq-cloud-hybrid-router\r?\n)    ports:\r?\n      - "5141:5140"\r?\n'
if ($content -notmatch $hybridPortPattern) {
    throw "Unable to locate cloud-hybrid-router host port block in $baseComposePath"
}
$hybridReplacement = '$1' + "    # Host port 5141 is reserved by Edge PostgreSQL on the combined onsite host.`r`n" +
    "    # Cloud services reach this service internally at cloud-hybrid-router:5140.`r`n"
$content = [regex]::Replace($content, $hybridPortPattern, $hybridReplacement)

$header = @(
    "# Generated from docker-compose.yml on $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz', $timestampCulture))"
    "# Onsite release compose uses prebuilt images only. Do not add --build when starting this file."
    ""
) -join "`r`n"

$content = $header + $content
Set-Content -Path $outputPath -Value $content -Encoding UTF8

Write-Host "Generated onsite compose: $outputPath" -ForegroundColor Green
