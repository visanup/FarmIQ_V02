param(
    [ValidateSet("core", "capture", "full", "status", "logs", "config", "down")]
    [string]$Action = "full",
    [string]$Service = "",
    [switch]$BuildImages
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$iotRoot = Split-Path -Parent $scriptRoot

$baseFiles = @("-f", "docker-compose.yml")
$captureFiles = @("-f", "docker-compose.yml", "--profile", "capture")

function Invoke-Compose {
    param(
        [string[]]$ComposeArgs
    )

    Push-Location $iotRoot
    try {
        & docker compose @ComposeArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

function Get-UpArgs {
    param(
        [string[]]$Files,
        [string[]]$Services
    )

    $args = @($Files)
    $args += @("up", "-d")
    if ($BuildImages) {
        $args += "--build"
    }
    $args += $Services
    return $args
}

switch ($Action) {
    "core" {
        Invoke-Compose (Get-UpArgs -Files $baseFiles -Services @("ui-app", "weight-vision-calibrator", "weight-vision-service"))
    }
    "capture" {
        Invoke-Compose (Get-UpArgs -Files $captureFiles -Services @("weight-vision-capture"))
    }
    "full" {
        Invoke-Compose (Get-UpArgs -Files $captureFiles -Services @("ui-app", "weight-vision-calibrator", "weight-vision-service", "weight-vision-capture"))
    }
    "status" {
        Invoke-Compose ($captureFiles + @("ps"))
    }
    "logs" {
        if ([string]::IsNullOrWhiteSpace($Service)) {
            Invoke-Compose ($captureFiles + @("logs", "-f"))
        }
        else {
            Invoke-Compose ($captureFiles + @("logs", "-f", $Service))
        }
    }
    "config" {
        Invoke-Compose ($captureFiles + @("config"))
    }
    "down" {
        Invoke-Compose ($captureFiles + @("down", "--remove-orphans"))
    }
}
