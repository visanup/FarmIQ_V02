param(
    [ValidateSet("up", "down", "verify")]
    [string]$Mode = "up",
    [ValidateSet("all", "dashboard-web", "admin-web")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..\..")
$CloudBaseCompose = Join-Path $RootDir "cloud-layer\docker-compose.yml"
$CloudDevCompose = Join-Path $RootDir "cloud-layer\docker-compose.dev.yml"

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

function Get-TargetServices {
    switch ($Target) {
        "dashboard-web" { return @("dashboard-web") }
        "admin-web" { return @("admin-web") }
        default { return @("dashboard-web", "admin-web") }
    }
}

function Test-HttpUrl {
    param(
        [string]$Name,
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
        Write-Host ("[OK] {0} -> {1}" -f $Name, $response.StatusCode) -ForegroundColor Green
    } catch {
        throw ("{0} is not reachable at {1}" -f $Name, $Url)
    }
}

$services = Get-TargetServices

switch ($Mode) {
    "up" {
        Ensure-DockerNetwork
        docker compose -f $CloudBaseCompose -f $CloudDevCompose --profile ui up -d --build @services
        exit $LASTEXITCODE
    }

    "down" {
        docker compose -f $CloudBaseCompose -f $CloudDevCompose stop @services
        exit $LASTEXITCODE
    }

    "verify" {
        if ($services -contains "dashboard-web") {
            Test-HttpUrl -Name "dashboard-web" -Url "http://localhost:5142"
        }
        if ($services -contains "admin-web") {
            Test-HttpUrl -Name "admin-web" -Url "http://localhost:5143"
        }
    }
}
