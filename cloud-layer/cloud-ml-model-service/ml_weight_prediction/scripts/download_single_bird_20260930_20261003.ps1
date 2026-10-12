<#!
.SYNOPSIS
Downloads the approved candidate image objects for 2026-09-30 through
2026-10-03 according to the single-bird export runbook.

.DESCRIPTION
Requires interactive SSH authentication for qi67@100.69.28.16.  The script
downloads only object keys present in the generated candidate manifest.
#>

$ErrorActionPreference = 'Stop'

$serviceRoot = Split-Path -Parent $PSScriptRoot
$manifest = Join-Path $serviceRoot 'data\processed\single_bird_export_candidates_20260930_20261003.csv'
$destination = Join-Path $serviceRoot 'data\raw\single_bird_candidates'
$downloader = Join-Path $PSScriptRoot 'download_minio_objects.py'
$remote = 'qi67@100.69.28.16'
$remoteRoot = '/home/qi67/FarmIQ_Filter/clean'

foreach ($path in @($manifest, $downloader)) {
  if (-not (Test-Path $path)) { throw "Required file not found: $path" }
}

function Sync-FarmIQSingleBirdDayToRemote([string]$dateDir) {
  $datePath = $dateDir.Replace('-', '/')
  $keysFile = "$env:TEMP\farmiq_object_keys_$dateDir.txt"
  $remoteKeys = "/tmp/farmiq_object_keys_$dateDir.txt"
  $remoteScript = '/tmp/download_minio_objects.py'
  $keys = @(
    Import-Csv $manifest |
      Where-Object { $_.object_key -like "*/images/$datePath/*" } |
      Select-Object -ExpandProperty object_key -Unique
  )
  if ($keys.Count -eq 0) {
    Write-Warning "No candidates for $dateDir; skipping."
    return $false
  }

  [IO.File]::WriteAllLines($keysFile, $keys, (New-Object System.Text.UTF8Encoding($false)))
  scp $downloader "${remote}:$remoteScript"
  if ($LASTEXITCODE -ne 0) { throw "Could not copy MinIO downloader for $dateDir" }
  scp $keysFile "${remote}:$remoteKeys"
  if ($LASTEXITCODE -ne 0) { throw "Could not copy object-key list for $dateDir" }
  ssh $remote "python3 '$remoteScript' --keys-file '$remoteKeys' --destination '$remoteRoot/$dateDir'"
  if ($LASTEXITCODE -ne 0) { throw "Could not download MinIO candidate objects for $dateDir" }
  return $true
}

function Get-FarmIQSingleBirdDay([string]$dateDir) {
  $datePath = $dateDir.Replace('-', '/')
  $list = "$env:TEMP\farmiq_single_bird_$dateDir.txt"
  $remoteList = "/tmp/farmiq_single_bird_$dateDir.txt"
  $remoteArchive = "/tmp/farmiq_single_bird_$dateDir.tar"
  $localArchive = "$env:TEMP\farmiq_single_bird_$dateDir.tar"
  $outputDay = Join-Path $destination $dateDir
  $names = @(
    Import-Csv $manifest |
      Where-Object { $_.object_key -like "*/images/$datePath/*" } |
      ForEach-Object { [IO.Path]::GetFileName($_.object_key) } |
      Sort-Object -Unique
  )
  if ($names.Count -eq 0) {
    Write-Warning "No candidates for $dateDir; skipping."
    return
  }

  [IO.File]::WriteAllText($list, (($names -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
  New-Item -ItemType Directory -Force -Path $outputDay | Out-Null
  scp $list "${remote}:$remoteList"
  if ($LASTEXITCODE -ne 0) { throw "Could not copy tar list for $dateDir" }
  ssh $remote "tar --ignore-failed-read -C '$remoteRoot/$dateDir' -cf '$remoteArchive' -T '$remoteList'"
  if ($LASTEXITCODE -ne 0) { throw "Could not create remote archive for $dateDir" }
  scp "${remote}:$remoteArchive" $localArchive
  if ($LASTEXITCODE -ne 0) { throw "Could not download remote archive for $dateDir" }
  tar -xf $localArchive -C $outputDay
  if ($LASTEXITCODE -ne 0) { throw "Could not extract archive for $dateDir" }
  $count = (Get-ChildItem $outputDay -File -Filter '*.jpg').Count
  Write-Host "Completed ${dateDir}: $count image(s) in $outputDay"
}

foreach ($dateDir in '2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03') {
  if (Sync-FarmIQSingleBirdDayToRemote $dateDir) {
    Get-FarmIQSingleBirdDay $dateDir
  }
}
