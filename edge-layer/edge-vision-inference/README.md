# Edge Vision Inference

Python/FastAPI service that creates weight-inference jobs and records their
results. It does not run YOLO or perform image-pixel classification.

## Runtime flow

```
media event → inference job → download media for linkage/provenance
            → load session/capture metadata → normalized geometry features
            → active weight-model package (or controlled fallback)
            → inference result + outbox event
```

The image is retained as a linked media artifact. Model inputs are normalized
detection metadata, such as area, dimensions, depth and confidence. The
service can activate a subscribed JSON model package; when none is active, its
explicit fallback behavior remains available for compatibility.

## Hybrid Trial 75Sx25V

The Hybrid Trial path is disabled by default and does not alter legacy
inference. To opt in on a test Edge site, set:

```bash
HYBRID_TRIAL_ENABLED=true
HYBRID_TRIAL_MODEL_DIR=/app/runtime-models/hybrid-trial-75s25v-v1-edge
```

It calculates `0.75 × approved growth standard + 0.25 × Visual Standard Proxy`
from normalized geometry plus batch breed, sex and age. If these inputs are
not available, the existing inference path is used unchanged.

## Quick start

```bash
pip install -r requirements.txt
cp env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API

- `POST /api/v1/inference/jobs` — create an inference job
- `GET /api/v1/inference/jobs/{job_id}` — retrieve job state
- `GET /api/v1/inference/results?sessionId=...` — retrieve results
- `GET /api/v1/inference/models` — active model/runtime information
- `POST /api/v1/inference/models/refresh` — refresh subscribed package
- `GET /api/health` — health check

## Docker

```bash
docker build -t edge-vision-inference .
docker run -p 8000:8000 --env-file .env edge-vision-inference
```
