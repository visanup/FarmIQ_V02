param(
  [ValidateSet("up", "down", "ps", "logs", "seed", "smoke-http", "smoke-mqtt", "config", "validate")]
  [string]$Command = "ps",
  [string]$Service,
  [switch]$WithFeedIntake,
  [switch]$Volumes
)

$ErrorActionPreference = "Stop"

$EdgeDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$ComposeBase = Join-Path $EdgeDir "docker-compose.yml"
$ComposeDev = Join-Path $EdgeDir "docker-compose.dev.yml"

function Get-ComposeArgs {
  $args = @("-f", $ComposeBase, "-f", $ComposeDev)
  if ($WithFeedIntake) {
    $args += @("--profile", "feed-intake")
  }
  return $args
}

function Invoke-Compose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
  & docker compose @(Get-ComposeArgs) @Args
}

function Test-RequiredFiles {
  $required = @(
    $ComposeBase,
    $ComposeDev,
    (Join-Path $PSScriptRoot "run-seeds.ps1"),
    (Join-Path $PSScriptRoot "edge-smoke-http.ps1"),
    (Join-Path $PSScriptRoot "edge-smoke-mqtt.ps1")
  )

  foreach ($path in $required) {
    if (-not (Test-Path $path)) {
      throw "Missing required file: $path"
    }
  }
}

switch ($Command) {
  "up" {
    Invoke-Compose up -d --build
  }
  "down" {
    if ($Volumes) {
      Invoke-Compose down -v
    } else {
      Invoke-Compose down
    }
  }
  "ps" {
    Invoke-Compose ps
  }
  "logs" {
    if ($Service) {
      Invoke-Compose logs -f --tail=200 $Service
    } else {
      Invoke-Compose logs -f --tail=200
    }
  }
  "seed" {
    $seedArgs = @()
    if ($WithFeedIntake) {
      $seedArgs += "-WithFeedIntake"
    }
    & (Join-Path $PSScriptRoot "run-seeds.ps1") @seedArgs
  }
  "smoke-http" {
    & (Join-Path $PSScriptRoot "edge-smoke-http.ps1")
  }
  "smoke-mqtt" {
    & (Join-Path $PSScriptRoot "edge-smoke-mqtt.ps1")
  }
  "config" {
    Invoke-Compose config
  }
  "validate" {
    Test-RequiredFiles
    Invoke-Compose config | Out-Null
    $services = Invoke-Compose config --services
    if (-not $services) {
      throw "Compose service list is empty"
    }
    if ($WithFeedIntake -and ($services -notcontains "edge-feed-intake")) {
      throw "feed-intake profile requested but edge-feed-intake is missing from compose output"
    }
    Write-Host "Validation OK"
  }
}
