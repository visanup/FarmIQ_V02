<#
.SYNOPSIS
Downloads only the original single-bird candidate JPEGs listed in a manifest.

.DESCRIPTION
Copies selected MinIO objects to the qi67 Linux host through its S3-compatible
MinIO endpoint, then archives and downloads them to Windows. Interactive SSH
authentication is expected.
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string]$Manifest,

  [Parameter(Mandatory)]
  [ValidateNotNullOrEmpty()]
  [string[]]$Dates,

  [string]$Destination,

  [string]$Remote = 'qi67@100.69.28.16',

  [string]$RemoteRoot = '/home/qi67/FarmIQ_Filter/clean'
)

$ErrorActionPreference = 'Stop'
$serviceRoot = Split-Path -Parent $PSScriptRoot
$downloader = Join-Path $PSScriptRoot 'download_minio_objects.py'

if ([string]::IsNullOrWhiteSpace($Destination)) {
  $Destination = Join-Path $serviceRoot 'data\raw\single_bird_candidates'
}

foreach ($path in @($Manifest, $downloader)) {
  if (-not (Test-Path -LiteralPath $path)) { throw "Required file not found: $path" }
}

$manifestRows = @(Import-Csv -LiteralPath $Manifest)
if ($manifestRows.Count -eq 0) { throw "Manifest has no candidates: $Manifest" }

$remoteScript = '/tmp/download_minio_objects.py'
scp $downloader "${Remote}:$remoteScript"
if ($LASTEXITCODE -ne 0) { throw 'Could not copy the MinIO downloader to SSH host' }

foreach ($dateDir in $Dates) {
  if ($dateDir -notmatch '^\d{4}-\d{2}-\d{2}$') {
    throw "Invalid date format: $dateDir (expected YYYY-MM-DD)"
  }

  $datePath = $dateDir.Replace('-', '/')
  $rowsForDay = @($manifestRows | Where-Object { $_.object_key -like "*/images/$datePath/*" })
  if ($rowsForDay.Count -eq 0) {
    Write-Warning "No candidates for $dateDir; skipping"
    continue
  }

  $keysFile = Join-Path $env:TEMP "farmiq_object_keys_$dateDir.txt"
  $remoteKeys = "/tmp/farmiq_object_keys_$dateDir.txt"
  $keys = @($rowsForDay | Select-Object -ExpandProperty object_key -Unique)
  [IO.File]::WriteAllLines($keysFile, $keys, (New-Object System.Text.UTF8Encoding($false)))

  Write-Host "[$dateDir] Downloading $($keys.Count) images from MinIO to qi67..."
  scp $keysFile "${Remote}:$remoteKeys"
  if ($LASTEXITCODE -ne 0) { throw "Could not copy object-key list: $dateDir" }
  ssh $Remote "python3 '$remoteScript' --keys-file '$remoteKeys' --destination '$RemoteRoot/$dateDir'"
  if ($LASTEXITCODE -ne 0) { throw "Could not download MinIO objects: $dateDir" }

  $namesFile = Join-Path $env:TEMP "farmiq_single_bird_$dateDir.txt"
  $remoteNames = "/tmp/farmiq_single_bird_$dateDir.txt"
  $remoteArchive = "/tmp/farmiq_single_bird_$dateDir.tar"
  $localArchive = Join-Path $env:TEMP "farmiq_single_bird_$dateDir.tar"
  $outputDay = Join-Path $Destination $dateDir
  $names = @($rowsForDay | ForEach-Object { [IO.Path]::GetFileName($_.object_key) } | Sort-Object -Unique)

  [IO.File]::WriteAllText($namesFile, (($names -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
  New-Item -ItemType Directory -Force -Path $outputDay | Out-Null

  Write-Host "[$dateDir] Downloading archive to Windows..."
  scp $namesFile "${Remote}:$remoteNames"
  if ($LASTEXITCODE -ne 0) { throw "Could not copy archive list: $dateDir" }
  ssh $Remote "tar --ignore-failed-read -C '$RemoteRoot/$dateDir' -cf '$remoteArchive' -T '$remoteNames'"
  if ($LASTEXITCODE -ne 0) { throw "Could not create remote archive: $dateDir" }
  scp "${Remote}:$remoteArchive" $localArchive
  if ($LASTEXITCODE -ne 0) { throw "Could not download remote archive: $dateDir" }
  tar -xf $localArchive -C $outputDay
  if ($LASTEXITCODE -ne 0) { throw "Could not extract archive: $dateDir" }

  $count = (Get-ChildItem -LiteralPath $outputDay -File -Filter '*.jpg').Count
  Write-Host "Completed ${dateDir}: $count image(s) in $outputDay"
}
