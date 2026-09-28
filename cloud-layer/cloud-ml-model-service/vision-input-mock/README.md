# Vision input mock (Dev only)

The service replaces the two HTTP dependencies used by `edge-vision-inference` in a minimal Dev setup:

- `edge-media-store` — streams the submitted image back to inference.
- `edge-weighvision-session` — returns the submitted capture metadata.

Submit a capture to `POST /api/v1/mock/captures` with JSON. `imageBase64` is optional; if absent a valid 1x1 JPEG is used.

```json
{
  "tenantId": "t-001",
  "farmId": "f-001",
  "barnId": "b-001",
  "deviceId": "mock-camera-01",
  "stationId": "mock-station-01",
  "sessionId": "mock-session-001",
  "normalizedFeatures": {"area_mm2": 12000, "confidence_score": 0.91, "distance_mm": 420},
  "rawMetadata": {"height_estimation": {"floor_depth_mm": 420}}
}
```

Every submitted image is uploaded to the Dev-only MinIO bucket `vision-input-mock` before the inference job is created. Capture metadata remains in memory, so restarting the mock clears only its session metadata. The response contains the MinIO bucket/key and inference job ID, which can be checked at `GET /api/v1/inference/jobs/{jobId}` on vision inference.

## Run and stop

The mock submits the built-in capture every 60 seconds by default. Start it with:

```powershell
docker compose -p farmiq-vision-input-mock up -d --build
```

Stop and remove only this mock service with:

```powershell
docker compose -p farmiq-vision-input-mock down
```
