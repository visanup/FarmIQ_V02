$ErrorActionPreference = 'Stop'
$serviceRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$package = Join-Path $serviceRoot 'ml_weight_prediction/artifacts/shadow-package-approved'
if (-not (Test-Path (Join-Path $package 'manifest.json'))) {
    docker run --rm --mount "type=bind,source=$serviceRoot,target=/work" farmiq-allocation-shadow:local python /work/ml_weight_prediction/scripts/package_model.py --artifact-dir /work/ml_weight_prediction/artifacts/session_20260919_weak_candidate_approved --output-dir /work/ml_weight_prediction/artifacts/shadow-package-approved --performance-standard /work/ml_weight_prediction/docs/performance_standards/arbor_acres_plus/approved/Arbor_Acres_Plus_Male_Performance_Standard.xlsx --version aa-male-20260919-shadow-v1
    if ($LASTEXITCODE -ne 0) { throw 'Model packaging failed' }
}
$env:ALLOCATION_SHADOW_MANIFEST_SHA256 = (Get-FileHash (Join-Path $package 'manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Trusted local package SHA256: $env:ALLOCATION_SHADOW_MANIFEST_SHA256"
