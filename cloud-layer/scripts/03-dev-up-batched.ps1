# FarmIQ Cloud Layer: build/start services in ordered batches.
# Usage:
#   .\scripts\03-dev-up-batched.ps1
#   .\scripts\03-dev-up-batched.ps1 -RunSeeds
#   .\scripts\03-dev-up-batched.ps1 -FromBatch domain
#   .\scripts\03-dev-up-batched.ps1 -FromBatch pipeline -ToBatch gateway

param(
    [string]$ComposeFile = "docker-compose.dev.yml",
    [switch]$RunSeeds = $false,
    [ValidateSet("infra", "core", "pipeline", "domain", "analytics", "gateway")]
    [string]$FromBatch = "infra",
    [ValidateSet("infra", "core", "pipeline", "domain", "analytics", "gateway")]
    [string]$ToBatch = "gateway",
    [int]$RetryIntervalSeconds = 5,
    [int]$MaxHttpRetries = 24
)

$ErrorActionPreference = "Stop"

$SharedDir = Join-Path $PSScriptRoot "Shared"
. "$SharedDir\Config.ps1"
. "$SharedDir\Utilities.ps1"

function Ensure-DockerNetwork {
    param([string]$NetworkName = "farmiq-net")

    Write-Host "Ensuring Docker network '$NetworkName' exists..." -ForegroundColor Yellow
    $networkExists = docker network ls --format "{{.Name}}" | Select-String -Pattern ("^{0}$" -f [regex]::Escape($NetworkName))
    if (-not $networkExists) {
        docker network create $NetworkName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create Docker network '$NetworkName'."
        }
        Write-Host "  Created '$NetworkName'" -ForegroundColor Green
        return
    }

    Write-Host "  '$NetworkName' already exists" -ForegroundColor Green
}

function Wait-PostgresReady {
    param(
        [int]$MaxRetries = 24,
        [int]$RetryInterval = 5
    )

    Write-Host "Waiting for postgres..." -ForegroundColor Yellow
    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        docker compose -f $script:ComposePath exec -T postgres pg_isready -U $Script:PostgresUser 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  postgres is ready" -ForegroundColor Green
            return
        }

        Start-Sleep -Seconds $RetryInterval
    }

    throw "postgres did not become ready in time."
}

function Write-ServiceDiagnostics {
    param(
        [string]$Service,
        [int]$LogTail = 30
    )

    Write-Host ""
    Write-Host ("Diagnostics for {0}:" -f $Service) -ForegroundColor Yellow

    $psOutput = docker compose -f $script:ComposePath ps $Service 2>&1
    if ($psOutput) {
        Write-Host "Compose status:" -ForegroundColor Gray
        ($psOutput | Out-String).TrimEnd().Split([Environment]::NewLine) | ForEach-Object {
            if ($_ -ne "") {
                Write-Host ("  {0}" -f $_) -ForegroundColor Gray
            }
        }
    }

    $containerId = docker compose -f $script:ComposePath ps -q $Service 2>$null | Select-Object -First 1
    if (-not $containerId) {
        Write-Host "  Container not found yet." -ForegroundColor Yellow
        return
    }

    $inspectFormat = 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}} exit={{.State.ExitCode}} restarts={{.RestartCount}} startedAt={{.State.StartedAt}}'
    $inspectOutput = docker inspect --format $inspectFormat $containerId 2>&1
    if ($LASTEXITCODE -eq 0 -and $inspectOutput) {
        Write-Host ("State: {0}" -f $inspectOutput) -ForegroundColor Gray
    }

    $logs = docker compose -f $script:ComposePath logs --tail=$LogTail $Service 2>&1
    if ($logs) {
        Write-Host "Recent logs:" -ForegroundColor Gray
        ($logs | Out-String).TrimEnd().Split([Environment]::NewLine) | ForEach-Object {
            if ($_ -ne "") {
                Write-Host ("  {0}" -f $_) -ForegroundColor Gray
            }
        }
    }
}

function Wait-HttpReady {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Service = $Name,
        [int]$MaxRetries = 24,
        [int]$RetryInterval = 5
    )

    Write-Host "Waiting for $Name..." -ForegroundColor Yellow
    $lastStatus = $null
    $lastError = $null

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "  $Name is ready ($($response.StatusCode))" -ForegroundColor Green
                return
            }

            $lastStatus = $response.StatusCode
            $lastError = "Unexpected HTTP status"
        } catch {
            $status = $null
            if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
                $status = $_.Exception.Response.StatusCode.value__
            }
            if ($status) {
                $lastStatus = $status
            }
            $lastError = $_.Exception.Message
        }

        Start-Sleep -Seconds $RetryInterval
    }

    if ($lastStatus -eq 404) {
        Write-Host ("Hint: {0} answered 404. Check whether the service exposes {1}." -f $Name, $Url) -ForegroundColor Yellow
    } elseif ($lastError -match "actively refused|connection refused") {
        Write-Host ("Hint: {0} is reachable by container name but is not listening on the expected port yet." -f $Name) -ForegroundColor Yellow
    } elseif ($lastError) {
        Write-Host ("Last error: {0}" -f $lastError) -ForegroundColor Yellow
    }

    Write-ServiceDiagnostics -Service $Service
    throw "$Name did not become ready in time. Last checked: $Url"
}

function Invoke-BatchWait {
    param([hashtable]$Batch)

    switch ($Batch.Name) {
        "infra" {
            Wait-PostgresReady -MaxRetries $MaxHttpRetries -RetryInterval $RetryIntervalSeconds
            if (-not (Wait-RabbitMQReady -MaxRetries $MaxHttpRetries -RetryInterval $RetryIntervalSeconds)) {
                throw "rabbitmq did not become ready in time."
            }
            if (-not (Wait-VaultReady -MaxRetries 12 -RetryInterval $RetryIntervalSeconds)) {
                throw "vault did not become ready in time."
            }
        }
        default {
            foreach ($check in $Batch.HealthChecks) {
                $serviceName = if ($check.Service) { $check.Service } else { $check.Name }
                Wait-HttpReady -Name $check.Name -Service $serviceName -Url $check.Url -MaxRetries $MaxHttpRetries -RetryInterval $RetryIntervalSeconds
            }
        }
    }
}

function Invoke-ComposeBatch {
    param([hashtable]$Batch)

    Write-Host ""
    Write-Host ("=== Batch: {0} ===" -f $Batch.Name) -ForegroundColor Cyan
    Write-Host ("Services: {0}" -f ($Batch.Services -join ", ")) -ForegroundColor Gray

    docker compose -f $script:ComposePath up -d --build @($Batch.Services)
    if ($LASTEXITCODE -ne 0) {
        throw ("docker compose up failed for batch '{0}'." -f $Batch.Name)
    }

    Invoke-BatchWait -Batch $Batch
}

$ComposePath = Get-DockerComposePath -ComposeFile $ComposeFile
$script:ComposePath = $ComposePath

if (-not (Test-Path $ComposePath)) {
    Write-Host "ERROR: Compose file not found: $ComposePath" -ForegroundColor Red
    exit 1
}

if (-not (Test-Docker)) {
    Write-Host "ERROR: Docker is not available. Please ensure Docker Desktop is running." -ForegroundColor Red
    exit 1
}

$batches = @(
    @{
        Name = "infra"
        Services = @("postgres", "rabbitmq", "vault", "pgadmin")
        HealthChecks = @()
    },
    @{
        Name = "core"
        Services = @(
            "cloud-identity-access",
            "cloud-tenant-registry",
            "cloud-standards-service",
            "cloud-config-rules-service",
            "cloud-audit-log-service",
            "cloud-llm-insights-service"
        )
        HealthChecks = @(
            @{ Name = "cloud-identity-access"; Url = "http://localhost:5120/api/health" },
            @{ Name = "cloud-tenant-registry"; Url = "http://localhost:5121/api/health" },
            @{ Name = "cloud-standards-service"; Url = "http://localhost:5133/api/health" },
            @{ Name = "cloud-config-rules-service"; Url = "http://localhost:5126/api/health" },
            @{ Name = "cloud-audit-log-service"; Url = "http://localhost:5127/api/health" },
            @{ Name = "cloud-llm-insights-service"; Url = "http://localhost:5134/api/health" }
        )
    },
    @{
        Name = "pipeline"
        Services = @(
            "cloud-ingestion",
            "cloud-telemetry-service"
        )
        HealthChecks = @(
            @{ Name = "cloud-ingestion"; Url = "http://localhost:5122/api/health" },
            @{ Name = "cloud-telemetry-service"; Url = "http://localhost:5123/api/health" }
        )
    },
    @{
        Name = "domain"
        Services = @(
            "cloud-notification-service",
            "cloud-feed-service",
            "cloud-barn-records-service",
            "cloud-weighvision-readmodel",
            "cloud-billing-service",
            "cloud-reporting-export-service"
        )
        HealthChecks = @(
            @{ Name = "cloud-notification-service"; Url = "http://localhost:5128/api/health" },
            @{ Name = "cloud-feed-service"; Url = "http://localhost:5130/api/health" },
            @{ Name = "cloud-barn-records-service"; Url = "http://localhost:5131/api/health" },
            @{ Name = "cloud-weighvision-readmodel"; Url = "http://localhost:5132/api/health" },
            @{ Name = "cloud-billing-service"; Url = "http://localhost:5145/api/health" },
            @{ Name = "cloud-reporting-export-service"; Url = "http://localhost:5129/api/health" }
        )
    },
    @{
        Name = "analytics"
        Services = @(
            "cloud-analytics-service",
            "cloud-advanced-analytics",
            "cloud-data-pipeline",
            "cloud-bi-metabase"
        )
        HealthChecks = @(
            @{ Name = "cloud-analytics-service"; Url = "http://localhost:5124/api/health" },
            @{ Name = "cloud-advanced-analytics"; Url = "http://localhost:5146/api/health" },
            @{ Name = "cloud-data-pipeline"; Url = "http://localhost:5147/api/health" },
            @{ Name = "cloud-bi-metabase"; Url = "http://localhost:5148/api/health" }
        )
    },
    @{
        Name = "gateway"
        Services = @("cloud-api-gateway-bff")
        HealthChecks = @(
            @{ Name = "cloud-api-gateway-bff"; Url = "http://localhost:5125/api/health" }
        )
    }
)

$batchNames = $batches | ForEach-Object { $_.Name }
$fromIndex = $batchNames.IndexOf($FromBatch)
$toIndex = $batchNames.IndexOf($ToBatch)

if ($fromIndex -gt $toIndex) {
    Write-Host "ERROR: FromBatch must come before or equal to ToBatch." -ForegroundColor Red
    exit 1
}

$selectedBatches = $batches[$fromIndex..$toIndex]

Write-Host "=== FarmIQ Cloud Layer: Batched Build/Up ===" -ForegroundColor Cyan
Write-Host ("Compose file: {0}" -f $ComposePath) -ForegroundColor Gray
Write-Host ("Batch range : {0} -> {1}" -f $FromBatch, $ToBatch) -ForegroundColor Gray
if ($FromBatch -ne "infra") {
    Write-Host "Warning     : earlier batches are assumed to already be running." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Execution plan:" -ForegroundColor Yellow
foreach ($batch in $selectedBatches) {
    Write-Host ("  - {0}: {1}" -f $batch.Name, ($batch.Services -join ", ")) -ForegroundColor Gray
}

Ensure-DockerNetwork

foreach ($batch in $selectedBatches) {
    Invoke-ComposeBatch -Batch $batch
}

if ($RunSeeds) {
    Write-Host ""
    Write-Host "Running migrations + seeds..." -ForegroundColor Yellow
    & "$PSScriptRoot\04-run-seeds.ps1"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "All selected batches completed successfully." -ForegroundColor Green
