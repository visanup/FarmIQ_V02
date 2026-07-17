param(
    [ValidateSet("full", "batched", "verify", "down")]
    [string]$Mode = "full",
    [string]$ComposeFile = "docker-compose.dev.yml",
    [switch]$RunSeeds = $false,
    [ValidateSet("infra", "core", "pipeline", "domain", "analytics", "gateway")]
    [string]$FromBatch = "infra",
    [ValidateSet("infra", "core", "pipeline", "domain", "analytics", "gateway")]
    [string]$ToBatch = "gateway"
)

$ErrorActionPreference = "Stop"

$SharedDir = Join-Path $PSScriptRoot "Shared"
. "$SharedDir\Config.ps1"
. "$SharedDir\Utilities.ps1"

function Ensure-DockerNetwork {
    param([string]$NetworkName = "farmiq-net")

    $networkExists = docker network ls --format "{{.Name}}" | Select-String -Pattern ("^{0}$" -f [regex]::Escape($NetworkName))
    if (-not $networkExists) {
        Write-Host "Creating Docker network '$NetworkName'..." -ForegroundColor Yellow
        docker network create $NetworkName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create Docker network '$NetworkName'."
        }
    }
}

if (-not (Test-Docker)) {
    Write-Host "ERROR: Docker is not available. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

$composePath = Get-DockerComposePath -ComposeFile $ComposeFile
if (-not (Test-Path $composePath)) {
    Write-Host "ERROR: Compose file not found: $composePath" -ForegroundColor Red
    exit 1
}

switch ($Mode) {
    "full" {
        Write-Host "=== Cloud deploy: full ===" -ForegroundColor Cyan
        Ensure-DockerNetwork
        docker compose -f $composePath up -d --build
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        if ($RunSeeds) {
            & "$PSScriptRoot\04-run-seeds.ps1"
            exit $LASTEXITCODE
        }
    }

    "batched" {
        Write-Host "=== Cloud deploy: batched ===" -ForegroundColor Cyan
        $batchedArgs = @(
            "-ComposeFile", $ComposeFile,
            "-FromBatch", $FromBatch,
            "-ToBatch", $ToBatch
        )
        if ($RunSeeds) {
            $batchedArgs += "-RunSeeds"
        }

        & "$PSScriptRoot\03-dev-up-batched.ps1" @batchedArgs
        exit $LASTEXITCODE
    }

    "verify" {
        Write-Host "=== Cloud deploy: verify ===" -ForegroundColor Cyan
        & "$PSScriptRoot\06-verify-compose.ps1" -ComposeFile $ComposeFile
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        & "$PSScriptRoot\07-verify-bff-tenants-route.ps1"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        & "$PSScriptRoot\08-verify-dashboard-pages.ps1"
        exit $LASTEXITCODE
    }

    "down" {
        Write-Host "=== Cloud deploy: down ===" -ForegroundColor Cyan
        docker compose -f $composePath down
        exit $LASTEXITCODE
    }
}
