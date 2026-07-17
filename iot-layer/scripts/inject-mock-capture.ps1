param(
    [Parameter(Mandatory = $true)]
    [string]$SourceMetadataPath,
    [string]$SessionId = "",
    [decimal]$OverrideWeightKg = 0,
    [switch]$UseOverrideWeight,
    [string]$TenantId = "tenant-mock-inject",
    [string]$FarmId = "farm-mock-inject",
    [string]$BarnId = "barn-mock-inject",
    [string]$DeviceId = "wv-mock-inject",
    [string]$StationId = "station-mock-inject",
    [string]$EdgeMediaStoreBaseUrl = "http://localhost:5106",
    [string]$EdgeSessionBaseUrl = "http://localhost:5105",
    [string]$EdgeVisionInferenceBaseUrl = "http://localhost:5107",
    [string]$MqttHosts = "127.0.0.1:5100",
    [string]$MediaUploadHost = "localhost:9000",
    [string]$CaptureRoot = "",
    [string]$LogPath = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$iotRoot = Split-Path -Parent $scriptRoot
$repoRoot = Split-Path -Parent $iotRoot
$serviceDir = Join-Path $iotRoot "weight-vision-service"
$evidenceDir = Join-Path $repoRoot "docs/iot-layer/evidence"

$sourceMetadataFullPath = (Resolve-Path -LiteralPath $SourceMetadataPath).Path
if ([string]::IsNullOrWhiteSpace($SessionId)) {
    $SessionId = "sess-mock-$([System.Guid]::NewGuid().ToString('N'))"
}

$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($CaptureRoot)) {
    $CaptureRoot = Join-Path ([System.IO.Path]::GetTempPath()) "farmiq-mock-capture-$runStamp-$SessionId"
}

$metadataDir = Join-Path $CaptureRoot "metadata"
$imagesDir = Join-Path $CaptureRoot "images"
$stateDir = Join-Path $CaptureRoot "state"
$bufferDir = Join-Path $CaptureRoot "buffer"

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
    $LogPath = Join-Path $evidenceDir "inject-mock-capture-$runStamp.log"
}

New-Item -ItemType Directory -Force -Path $metadataDir, $imagesDir, $stateDir, $bufferDir | Out-Null

$metadata = Get-Content -LiteralPath $sourceMetadataFullPath -Raw | ConvertFrom-Json
$sourceImageId = [string]($metadata.image_id)
if ([string]::IsNullOrWhiteSpace($sourceImageId)) {
    $sourceImageId = [System.IO.Path]::GetFileNameWithoutExtension($sourceMetadataFullPath)
}

$timestampIso = (Get-Date).ToUniversalTime().ToString("o")
$metadata.image_id = $SessionId
if ($metadata.PSObject.Properties.Name -contains "session_id") {
    $metadata.session_id = $SessionId
}
else {
    Add-Member -InputObject $metadata -NotePropertyName "session_id" -NotePropertyValue $SessionId
}
if ($metadata.PSObject.Properties.Name -contains "timestamp") {
    $metadata.timestamp = $timestampIso
}
else {
    Add-Member -InputObject $metadata -NotePropertyName "timestamp" -NotePropertyValue $timestampIso
}

if ($UseOverrideWeight) {
    if (-not $metadata.scale) {
        Add-Member -InputObject $metadata -NotePropertyName "scale" -NotePropertyValue ([pscustomobject]@{})
    }
    if ($metadata.scale.PSObject.Properties.Name -contains "weight_kg") {
        $metadata.scale.weight_kg = [double]$OverrideWeightKg
    }
    else {
        Add-Member -InputObject $metadata.scale -NotePropertyName "weight_kg" -NotePropertyValue ([double]$OverrideWeightKg)
    }
    if ($metadata.scale.PSObject.Properties.Name -contains "weight_source") {
        $metadata.scale.weight_source = "inject_mock_capture"
    }
    else {
        Add-Member -InputObject $metadata.scale -NotePropertyName "weight_source" -NotePropertyValue "inject_mock_capture"
    }
}

$targetMetadataPath = Join-Path $metadataDir "$SessionId.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $targetMetadataPath,
    ($metadata | ConvertTo-Json -Depth 100),
    $utf8NoBom
)

$sourceImageDir = Join-Path (Split-Path (Split-Path $sourceMetadataFullPath -Parent) -Parent) "images"
$sourceFiles = Get-ChildItem -LiteralPath $sourceImageDir -File | Where-Object {
    $_.Name -like "$sourceImageId`_*"
}
if (-not $sourceFiles) {
    throw "No source images found for image_id=$sourceImageId in $sourceImageDir"
}

$copiedImages = @()
foreach ($file in $sourceFiles) {
    $suffix = $file.Name.Substring($sourceImageId.Length)
    $target = Join-Path $imagesDir "$SessionId$suffix"
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    $copiedImages += $target
}

$savedEnv = @{}
function Set-ScopedEnv {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if (-not $savedEnv.ContainsKey($Name)) {
        $savedEnv[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Restore-Env {
    foreach ($entry in $savedEnv.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
}

Set-ScopedEnv -Name "TENANT_ID" -Value $TenantId
Set-ScopedEnv -Name "FARM_ID" -Value $FarmId
Set-ScopedEnv -Name "BARN_ID" -Value $BarnId
Set-ScopedEnv -Name "DEVICE_ID" -Value $DeviceId
Set-ScopedEnv -Name "STATION_ID" -Value $StationId
Set-ScopedEnv -Name "MQTT_HOSTS" -Value $MqttHosts
Set-ScopedEnv -Name "EDGE_MEDIA_STORE_BASE_URL" -Value $EdgeMediaStoreBaseUrl
Set-ScopedEnv -Name "EDGE_SESSION_BASE_URL" -Value $EdgeSessionBaseUrl
Set-ScopedEnv -Name "EDGE_VISION_INFERENCE_BASE_URL" -Value $EdgeVisionInferenceBaseUrl
Set-ScopedEnv -Name "CAPTURE_DATA_DIR" -Value $CaptureRoot
Set-ScopedEnv -Name "STATE_DIR" -Value $stateDir
Set-ScopedEnv -Name "EVENT_BUFFER_DIR" -Value $bufferDir
Set-ScopedEnv -Name "STATUS_PUBLISH_ENABLED" -Value "false"
Set-ScopedEnv -Name "METADATA_FILE_ONCE" -Value $targetMetadataPath
Set-ScopedEnv -Name "MEDIA_UPLOAD_HOST" -Value $MediaUploadHost
Set-ScopedEnv -Name "NO_PROXY" -Value "localhost,127.0.0.1"
Set-ScopedEnv -Name "no_proxy" -Value "localhost,127.0.0.1"
Set-ScopedEnv -Name "DRY_RUN" -Value $(if ($DryRun) { "true" } else { "false" })

Push-Location $serviceDir
try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & python run_service.py 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}
finally {
    Pop-Location
    Restore-Env
}

@($output | ForEach-Object { $_.ToString() }) | Set-Content -Path $LogPath -Encoding UTF8
if ($exitCode -ne 0) {
    throw "weight-vision-service exited with code $exitCode. See log: $LogPath"
}

$summary = [ordered]@{
    session_id = $SessionId
    source_metadata_path = $sourceMetadataFullPath
    generated_metadata_path = $targetMetadataPath
    capture_root = $CaptureRoot
    copied_images = $copiedImages
    dry_run = [bool]$DryRun
    edge_media_store_base_url = $EdgeMediaStoreBaseUrl
    edge_session_base_url = $EdgeSessionBaseUrl
    edge_vision_inference_base_url = $EdgeVisionInferenceBaseUrl
    mqtt_hosts = $MqttHosts
    log_path = $LogPath
    temp_files_retained = $true
}

$summary | ConvertTo-Json -Depth 20
