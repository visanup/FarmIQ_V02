param(
  [switch]$WithFeedIntake
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EdgeDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$ComposeBase = Join-Path $EdgeDir "docker-compose.yml"
$ComposeDev = Join-Path $EdgeDir "docker-compose.dev.yml"

function Compose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
  $composeArgs = @("-f", $ComposeBase, "-f", $ComposeDev)
  if ($WithFeedIntake) {
    $composeArgs += @("--profile", "feed-intake")
  }
  docker compose @composeArgs @Args
}

$successes = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]

function Run-Step {
  param(
    [string]$Name,
    [scriptblock]$Action
  )
  Write-Host ""
  Write-Host "==> $Name"
  try {
    & $Action
    if ($LASTEXITCODE -ne 0) {
      throw "ExitCode=$LASTEXITCODE"
    }
    Write-Host "OK: $Name"
    $successes.Add($Name) | Out-Null
  } catch {
    Write-Host "FAIL: $Name"
    Write-Host $_
    $failures.Add($Name) | Out-Null
  }
}

Write-Host "Edge seeds runner"
Write-Host "EDGE_DIR=$EdgeDir"

Write-Host ""
Write-Host "==> Starting postgres"
Compose up -d postgres | Out-Null

$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "farmiq" }
$pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "farmiq" }

Write-Host "==> Waiting for postgres readiness"
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  Compose exec -T postgres pg_isready -U $pgUser -d $pgDb | Out-Null
  if ($LASTEXITCODE -eq 0) {
    $ready = $true
    break
  }
  Start-Sleep -Seconds 1
}
if (-not $ready) {
  Write-Host "ERROR: Postgres not ready after 60s"
  exit 2
}

Write-Host "==> Ensuring required extensions"
Compose exec -T postgres psql -U $pgUser -d $pgDb -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS ""uuid-ossp"";" | Out-Null

Write-Host "==> Ensuring required edge databases"
$edgeDbs = @(
  "edge_ingress_gateway",
  "edge_telemetry_timeseries",
  "edge_weighvision_session",
  "edge_media_store",
  "edge_feed_intake",
  "edge_policy_sync",
  "edge_sync_forwarder",
  "edge_vision_inference"
)

foreach ($db in $edgeDbs) {
  $exists = (Compose exec -T postgres psql -U $pgUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${db}'" 2>$null)
  if (($exists | Out-String).Trim() -ne "1") {
    Write-Host "Creating database: $db"
    Compose exec -T postgres psql -U $pgUser -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE ""$db"";" | Out-Null
  }
}

$prismaDbServices = @(
  "edge-ingress-gateway",
  "edge-telemetry-timeseries",
  "edge-weighvision-session",
  "edge-media-store"
)

if ($WithFeedIntake) {
  $prismaDbServices += "edge-feed-intake"
}

foreach ($svc in $prismaDbServices) {
  Run-Step "$svc:db:migrate" { Compose run --rm --no-deps $svc npm run db:migrate }
  Run-Step "$svc:seed" { Compose run --rm --no-deps $svc npm run seed }
}

Run-Step "edge-policy-sync:db:migrate+seed" { Compose run --rm --no-deps edge-policy-sync sh -lc "npm install --no-audit --no-fund >/dev/null && npm run db:migrate && npm run seed" }

Run-Step "edge-sync-forwarder:db:migrate+seed" { Compose run --rm --no-deps edge-sync-forwarder sh -lc "npm install --no-audit --no-fund >/dev/null && npm run db:migrate && npm run seed" }

Run-Step "edge-vision-inference:seed" { Compose run --rm --no-deps edge-vision-inference python app/seed.py }

Write-Host ""
Write-Host "===================="
Write-Host "Seed summary"
Write-Host "===================="
Write-Host ("SUCCESS: {0}" -f $successes.Count)
foreach ($s in $successes) { Write-Host ("  - {0}" -f $s) }
Write-Host ("FAIL: {0}" -f $failures.Count)
foreach ($f in $failures) { Write-Host ("  - {0}" -f $f) }

if ($failures.Count -ne 0) {
  exit 1
}
