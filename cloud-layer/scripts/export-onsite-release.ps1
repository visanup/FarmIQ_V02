param(
    [string]$OutputRoot = "",
    [switch]$SkipComposeGeneration
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$cloudLayerDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $cloudLayerDir
$timestampCulture = [System.Globalization.CultureInfo]::InvariantCulture

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $cloudLayerDir "exports"
}

$timestamp = (Get-Date).ToString("yyyyMMdd-HHmmss", $timestampCulture)
$releaseDir = Join-Path $OutputRoot "onsite-release-$timestamp"
$composePath = Join-Path $cloudLayerDir "docker-compose.onsite.yml"
$guideSourcePath = Join-Path $repoRoot "docs\cloud-layer\06-ubuntu-onsite-release-guide.html"

if (-not $SkipComposeGeneration) {
    & (Join-Path $PSScriptRoot "generate-onsite-compose.ps1")
}

if (-not (Test-Path $composePath)) {
    throw "Onsite compose file not found: $composePath"
}

if (-not (Test-Path $guideSourcePath)) {
    throw "Onsite guide not found: $guideSourcePath"
}

$bundles = @(
    [pscustomobject]@{
        Name = "infra"
        Archive = "cloud-layer-infra-$timestamp.tar"
        Images = @(
            "postgres:16-alpine",
            "dpage/pgadmin4:8",
            "hashicorp/vault:1.13.3",
            "rabbitmq:3.13-management-alpine",
            "redis:7-alpine",
            "gcr.io/datadoghq/agent:7"
        )
    },
    [pscustomobject]@{
        Name = "cloud-services"
        Archive = "cloud-layer-cloud-services-$timestamp.tar"
        Images = @(
            "cloud-layer-cloud-identity-access:latest",
            "cloud-layer-cloud-tenant-registry:latest",
            "cloud-layer-cloud-ingestion:latest",
            "cloud-layer-cloud-telemetry-service:latest",
            "cloud-layer-cloud-analytics-service:latest",
            "cloud-layer-cloud-config-rules-service:latest",
            "cloud-layer-cloud-audit-log-service:latest",
            "cloud-layer-cloud-fleet-management:latest",
            "cloud-layer-cloud-notification-service:latest",
            "cloud-layer-cloud-reporting-export-service:latest",
            "cloud-layer-cloud-feed-service:latest",
            "cloud-layer-cloud-barn-records-service:latest",
            "cloud-layer-cloud-weighvision-readmodel:latest",
            "cloud-layer-cloud-llm-insights-service:latest",
            "cloud-layer-cloud-ml-model-service:latest",
            "cloud-layer-cloud-mlflow-registry:latest",
            "cloud-layer-cloud-feature-store:latest",
            "cloud-layer-cloud-drift-detection:latest",
            "cloud-layer-cloud-inference-server:latest",
            "cloud-layer-cloud-hybrid-router:latest",
            "cloud-layer-cloud-standards-service:latest",
            "cloud-layer-cloud-api-gateway-bff:latest",
            "cloud-layer-cloud-billing-service:latest",
            "cloud-layer-cloud-advanced-analytics:latest",
            "cloud-layer-cloud-data-pipeline:latest",
            "cloud-layer-cloud-bi-metabase:latest"
        )
    },
    [pscustomobject]@{
        Name = "apps-web"
        Archive = "cloud-layer-apps-web-$timestamp.tar"
        Images = @(
            "cloud-layer-dashboard-web:latest",
            "cloud-layer-admin-web:latest"
        )
    }
)

function Assert-ImagesExist {
    param([string[]]$Images)

    $missing = @()
    foreach ($image in $Images) {
        docker image inspect $image *> $null
        if ($LASTEXITCODE -ne 0) {
            $missing += $image
        }
    }

    if ($missing.Count -gt 0) {
        throw "Missing Docker images: $($missing -join ', ')"
    }
}

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
Copy-Item -Path $composePath -Destination (Join-Path $releaseDir "docker-compose.onsite.yml") -Force
Copy-Item -Path $guideSourcePath -Destination (Join-Path $releaseDir "ubuntu-onsite-release-guide.html") -Force

$manifestLines = @(
    "Cloud-layer onsite release created on $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss K', $timestampCulture)).",
    "Artifacts in this folder:",
    "- docker-compose.onsite.yml",
    "- ubuntu-onsite-release-guide.html"
)

foreach ($bundle in $bundles) {
    Assert-ImagesExist -Images $bundle.Images

    $archivePath = Join-Path $releaseDir $bundle.Archive
    Write-Host "Exporting bundle '$($bundle.Name)'..." -ForegroundColor Cyan
    docker save -o $archivePath @($bundle.Images)
    if ($LASTEXITCODE -ne 0) {
        throw "docker save failed for bundle '$($bundle.Name)'"
    }

    $bundle.Images | Set-Content -Path (Join-Path $releaseDir "images-$($bundle.Name).txt") -Encoding UTF8
    $manifestLines += "- $($bundle.Archive)"
    $manifestLines += "- images-$($bundle.Name).txt"
}

$manifestLines += ""
$manifestLines += "Expected onsite source layout:"
$manifestLines += "- FarmIQ_V02/apps"
$manifestLines += "- FarmIQ_V02/cloud-layer"
$manifestLines += ""
$manifestLines += "Recommended onsite startup:"
$manifestLines += "- docker compose -f docker-compose.onsite.yml up -d"

$manifestLines | Set-Content -Path (Join-Path $releaseDir "README.txt") -Encoding UTF8

Write-Host ""
Write-Host "Onsite release ready: $releaseDir" -ForegroundColor Green
