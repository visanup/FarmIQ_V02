param(
    [ValidateSet("core", "full", "capture-recreate", "capture-rebuild", "smoke", "status", "logs", "config", "down")]
    [string]$Action = "core",
    [string]$Service = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$iotRoot = Split-Path -Parent $scriptRoot

$baseFiles = @("-f", "docker-compose.yml")
$smokeFiles = @("-f", "docker-compose.yml", "-f", "docker-compose.capture-smoke.yml")

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

switch ($Action) {
    "core" {
        Invoke-Compose ($baseFiles + @("up", "-d", "--build", "ui-app", "weight-vision-calibrator", "weight-vision-service"))
    }
    "full" {
        Invoke-Compose ($baseFiles + @("--profile", "capture", "up", "-d", "--build", "ui-app", "weight-vision-calibrator", "weight-vision-service", "weight-vision-capture"))
    }
    "capture-recreate" {
        Invoke-Compose ($baseFiles + @("--profile", "capture", "up", "-d", "--force-recreate", "weight-vision-capture"))
    }
    "capture-rebuild" {
        Invoke-Compose ($baseFiles + @("--profile", "capture", "build", "weight-vision-capture"))
        Invoke-Compose ($baseFiles + @("--profile", "capture", "up", "-d", "--force-recreate", "weight-vision-capture"))
    }
    "smoke" {
        Invoke-Compose ($smokeFiles + @("up", "-d", "--build", "weight-vision-capture-smoke"))
    }
    "status" {
        Invoke-Compose ($smokeFiles + @("ps"))
    }
    "logs" {
        if ([string]::IsNullOrWhiteSpace($Service)) {
            Invoke-Compose ($smokeFiles + @("logs", "-f"))
        }
        else {
            Invoke-Compose ($smokeFiles + @("logs", "-f", $Service))
        }
    }
    "config" {
        Invoke-Compose ($baseFiles + @("config"))
    }
    "down" {
        Invoke-Compose ($smokeFiles + @("down", "--remove-orphans"))
    }
}
