"""A dependency-free Dev mock for feeding images and capture metadata to vision inference."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse
from urllib.request import Request, urlopen

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError


VISION_INFERENCE_URL = os.getenv("VISION_INFERENCE_URL", "http://edge-vision-inference:8000")
MEDIA_STORE_URL = os.getenv("MEDIA_STORE_URL", "").rstrip("/")
EDGE_SESSION_URL = os.getenv("EDGE_SESSION_URL", "").rstrip("/")
REAL_EDGE_INTEGRATION = os.getenv("REAL_EDGE_INTEGRATION", "false").lower() == "true"
EDGE_MINIO_INTERNAL_URL = os.getenv("EDGE_MINIO_INTERNAL_URL", "http://minio:9000").rstrip("/")
PORT = int(os.getenv("PORT", "3000"))
AUTO_SUBMIT_ENABLED = os.getenv("AUTO_SUBMIT_ENABLED", "true").lower() == "true"
MOCK_INTERVAL_SECONDS = max(1, int(os.getenv("MOCK_INTERVAL_SECONDS", "60")))
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "vision-input-mock")

# A valid 1x1 JPEG; useful for proving the full request path without a camera file.
DEFAULT_IMAGE_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/Aaf/"
    "xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/Aaf/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Ap//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/Iaf/"
    "2gAMAwEAAgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/"
    "2gAIAQEAAT8QH//Z"
)

media_by_id: dict[str, dict[str, Any]] = {}
captures_by_session: dict[str, list[dict[str, Any]]] = {}


def minio_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name="us-east-1",
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def upload_to_minio(object_key: str, image: bytes, content_type: str) -> None:
    client = minio_client()
    try:
        client.head_bucket(Bucket=MINIO_BUCKET)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket"}:
            raise
        client.create_bucket(Bucket=MINIO_BUCKET)
    client.put_object(Bucket=MINIO_BUCKET, Key=object_key, Body=image, ContentType=content_type)

PERIODIC_CAPTURE = {
    "tenantId": "t-001",
    "farmId": "f-001",
    "barnId": "b-001",
    "deviceId": "mock-camera-01",
    "stationId": "mock-station-01",
    "sessionId": "mock-periodic-session",
    "normalizedFeatures": {
        "area_mm2": 12000,
        "confidence_score": 0.91,
        "distance_mm": 420,
        "roi_count": 1,
        "detection_count": 1,
    },
    "rawMetadata": {"height_estimation": {"floor_depth_mm": 420}},
}


def get_value(payload: dict[str, Any], snake: str, camel: str, default: Any = None) -> Any:
    return payload.get(snake, payload.get(camel, default))


def current_utc_iso() -> str:
    """Default captures must be visible in the Dashboard's 24-hour filter."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def json_request(url: str, payload: dict[str, Any], *, method: str = "POST", headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", **(headers or {})},
        method=method,
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


class Handler(BaseHTTPRequestHandler):
    server_version = "FarmIQVisionInputMock/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, flush=True)

    def json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        try:
            size = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(size) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON body"})
            raise

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/api/health"):
            self.json_response(HTTPStatus.OK, {"status": "healthy"})
            return

        # A 404 has a defined meaning to vision inference: no cached model
        # subscription yet, so it may continue with its local/fallback model.
        if parsed.path == "/api/v1/edge-config/model-subscription/effective":
            self.json_response(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND"}})
            return

        media_prefix = "/api/v1/media/objects/"
        if parsed.path.startswith(media_prefix):
            media_id = parsed.path[len(media_prefix):]
            if media_id == "by-key":
                key = parse_qs(parsed.query).get("object_key", [""])[0]
                media = next((item for item in media_by_id.values() if item["object_key"] == key), None)
            else:
                media = media_by_id.get(media_id)
            if not media:
                self.json_response(HTTPStatus.NOT_FOUND, {"error": {"code": "NOT_FOUND"}})
                return
            body = media["image"]
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", media["content_type"])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        prefix = "/api/v1/weighvision/sessions/"
        if parsed.path.startswith(prefix):
            session_id = parsed.path[len(prefix):].split("/")[0]
            self.json_response(HTTPStatus.OK, {
                "sessionId": session_id,
                "captureMetadata": captures_by_session.get(session_id, []),
            })
            return

        self.json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/mock/captures":
            try:
                self.create_capture()
            except (ValueError, json.JSONDecodeError) as exc:
                self.json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:  # Keep Dev diagnostics at the caller boundary.
                self.json_response(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
            return

        if parsed.path == "/api/v1/mock/captures/object-sequence":
            try:
                self.create_object_sequence()
            except (ValueError, json.JSONDecodeError) as exc:
                self.json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:  # Keep Dev diagnostics at the caller boundary.
                self.json_response(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
            return

        if parsed.path.endswith("/attach"):
            self.read_json()
            self.json_response(HTTPStatus.OK, {"attached": True})
            return

        self.json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def create_object_sequence(self) -> None:
        """Submit three independent captures with 1, 2, then 3 detections.

        Each set gets a unique session so the session table's one-capture
        semantics and the downstream outbox can be verified independently.
        """
        payload = self.read_json()
        tenant_id = get_value(payload, "tenant_id", "tenantId")
        if not tenant_id:
            raise ValueError("tenant_id (or tenantId) is required")
        session_prefix = get_value(payload, "session_prefix", "sessionPrefix", f"mock-object-sequence-{uuid.uuid4().hex[:8]}")
        results: list[dict[str, Any]] = []
        for object_count in (1, 2, 3):
            capture_payload = {
                **payload,
                "sessionId": f"{session_prefix}-{object_count}",
                "captureId": str(uuid.uuid4()),
                "objectCount": object_count,
            }
            # Reuse the real capture implementation, but collect its response
            # rather than writing three HTTP responses to the caller.
            result = self.create_real_edge_capture_result(capture_payload, tenant_id)
            results.append({"objectCount": object_count, **result})
        self.json_response(HTTPStatus.ACCEPTED, {"mode": "object-sequence", "captures": results})

    def create_capture(self) -> None:
        payload = self.read_json()
        tenant_id = get_value(payload, "tenant_id", "tenantId")
        session_id = get_value(payload, "session_id", "sessionId")
        if not tenant_id or not session_id:
            raise ValueError("tenant_id (or tenantId) and session_id (or sessionId) are required")

        image_base64 = get_value(payload, "image_base64", "imageBase64", DEFAULT_IMAGE_BASE64)
        try:
            image = base64.b64decode(image_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("image_base64 must be valid Base64") from exc
        if not image:
            raise ValueError("image_base64 must not be empty")

        if REAL_EDGE_INTEGRATION:
            self.create_real_edge_capture(payload, image, tenant_id, session_id)
            return

        media_id = str(uuid.uuid4())
        capture_id = get_value(payload, "capture_id", "captureId", str(uuid.uuid4()))
        object_key = get_value(payload, "object_key", "objectKey", f"mock/{session_id}/{media_id}.jpg")
        content_type = get_value(payload, "content_type", "contentType", "image/jpeg")
        upload_to_minio(object_key, image, content_type)
        raw_metadata = get_value(payload, "raw_metadata", "rawMetadata", {}) or {}
        raw_metadata = {**raw_metadata, "image_id": capture_id, "session_id": session_id}
        capture = {
            "captureId": capture_id,
            "mediaIds": [media_id],
            "occurredAt": get_value(payload, "occurred_at", "occurredAt", "2026-09-22T00:00:00Z"),
            "featureSchemaVersion": get_value(payload, "feature_schema_version", "featureSchemaVersion", "mock-v1"),
            "normalizedFeatures": get_value(payload, "normalized_features", "normalizedFeatures", {}) or {},
            "rawMetadata": raw_metadata,
        }
        media_by_id[media_id] = {
            "image": image,
            "content_type": content_type,
            "object_key": object_key,
            "tenant_id": tenant_id,
        }

        # The production inference path reads media through edge-media-store,
        # not from this mock's in-memory endpoint.  When MEDIA_STORE_URL is
        # configured, complete the real media-store handshake before enqueueing
        # inference and use the authoritative media id returned by that service.
        inference_job_id = None
        if MEDIA_STORE_URL:
            complete_payload = {
                "tenant_id": tenant_id,
                "farm_id": get_value(payload, "farm_id", "farmId", "mock-farm"),
                "barn_id": get_value(payload, "barn_id", "barnId", "mock-barn"),
                "device_id": get_value(payload, "device_id", "deviceId", "mock-camera"),
                "session_id": session_id,
                "object_key": object_key,
                "mime_type": content_type,
                "size_bytes": len(image),
                "captured_at": get_value(payload, "occurred_at", "occurredAt", "2026-09-22T00:00:00Z"),
            }
            complete_body = json.dumps(complete_payload).encode("utf-8")
            complete_request = Request(
                f"{MEDIA_STORE_URL}/api/v1/media/images/complete",
                data=complete_body,
                headers={"content-type": "application/json", "x-tenant-id": tenant_id},
                method="POST",
            )
            with urlopen(complete_request, timeout=15) as response:
                completed = json.loads(response.read().decode("utf-8"))
            media_id = completed["media_id"]
            inference_job_id = completed.get("inference_job_id")
            capture["mediaIds"] = [media_id]
        captures_by_session.setdefault(session_id, []).append(capture)

        job_payload = {
            "tenant_id": tenant_id,
            "farm_id": get_value(payload, "farm_id", "farmId", "mock-farm"),
            "barn_id": get_value(payload, "barn_id", "barnId", "mock-barn"),
            "device_id": get_value(payload, "device_id", "deviceId", "mock-camera"),
            "station_id": get_value(payload, "station_id", "stationId", "mock-station"),
            "session_id": session_id,
            "media_id": media_id,
        }
        if inference_job_id:
            # edge-media-store already triggered inference as part of the
            # completion handshake. Submitting again here would create two
            # predictions for the same media object.
            job = {"job_id": inference_job_id, "status": "queued", "triggered_by": "media-store"}
        else:
            body = json.dumps(job_payload).encode("utf-8")
            request = Request(
                f"{VISION_INFERENCE_URL}/api/v1/inference/jobs",
                data=body,
                headers={"content-type": "application/json", "x-tenant-id": tenant_id, "x-request-id": str(uuid.uuid4())},
                method="POST",
            )
            with urlopen(request, timeout=15) as response:
                job = json.loads(response.read().decode("utf-8"))
        self.json_response(HTTPStatus.ACCEPTED, {
            "mediaId": media_id,
            "captureId": capture_id,
            "bucket": MINIO_BUCKET,
            "objectKey": object_key,
            "inferenceJob": job,
        })

    def create_real_edge_capture(self, payload: dict[str, Any], image: bytes, tenant_id: str, session_id: str) -> None:
        """Exercise actual Edge Session, Media Store and Inference services.

        This mode deliberately does not use the mock's service aliases.  It is a
        Dev integration harness, not a camera or MQTT emulator.
        """
        if not MEDIA_STORE_URL or not EDGE_SESSION_URL:
            raise ValueError("REAL_EDGE_INTEGRATION requires MEDIA_STORE_URL and EDGE_SESSION_URL")
        result = self.create_real_edge_capture_result(payload, tenant_id, image, session_id)
        self.json_response(HTTPStatus.ACCEPTED, result)

    def create_real_edge_capture_result(self, payload: dict[str, Any], tenant_id: str, image: bytes | None = None, session_id: str | None = None) -> dict[str, Any]:
        """Create one Edge capture and return its response payload without writing HTTP."""
        if not MEDIA_STORE_URL or not EDGE_SESSION_URL:
            raise ValueError("REAL_EDGE_INTEGRATION requires MEDIA_STORE_URL and EDGE_SESSION_URL")
        if session_id is None:
            session_id = get_value(payload, "session_id", "sessionId")
        if not session_id:
            raise ValueError("session_id (or sessionId) is required")
        if image is None:
            image_base64 = get_value(payload, "image_base64", "imageBase64", DEFAULT_IMAGE_BASE64)
            image = base64.b64decode(image_base64, validate=True)
        farm_id = get_value(payload, "farm_id", "farmId", "mock-farm")
        barn_id = get_value(payload, "barn_id", "barnId", "mock-barn")
        device_id = get_value(payload, "device_id", "deviceId", "mock-camera")
        station_id = get_value(payload, "station_id", "stationId", "mock-station")
        occurred_at = get_value(payload, "occurred_at", "occurredAt", current_utc_iso())
        content_type = get_value(payload, "content_type", "contentType", "image/jpeg")
        capture_id = get_value(payload, "capture_id", "captureId", str(uuid.uuid4()))
        object_count = int(get_value(payload, "object_count", "objectCount", 1))
        if object_count < 1:
            raise ValueError("object_count (or objectCount) must be at least 1")
        raw_metadata = {**(get_value(payload, "raw_metadata", "rawMetadata", {}) or {}), "image_id": capture_id, "session_id": session_id}
        normalized_features = get_value(payload, "normalized_features", "normalizedFeatures", {}) or {}
        # Match edge-weighvision-session's canonical input contract.  It
        # derives scalar columns from top-level detections, not from a nested
        # `normalizedFeatures` object.
        detections = [{
            "area_xy_mm2": normalized_features.get("area_mm2", 12000) + (index * 1000),
            "mask_area_px2": normalized_features.get("mask_area_px2", 12000) + (index * 1000),
            "confidence": normalized_features.get("confidence_score", 0.91),
            "distance_mm": normalized_features.get("distance_mm", 420) + (index * 5),
            "height_mm": normalized_features.get("height_mm", 50),
            "width_mm": normalized_features.get("width_mm", 80),
            "length_mm": normalized_features.get("length_mm", 150),
            "bbox": {"x1": 10 + (index * 120), "y1": 10, "x2": 110 + (index * 120), "y2": 160},
        } for index in range(object_count)]
        canonical_metadata = {
            **raw_metadata,
            "metadata_schema": {"name": "farmiq.weighvision.capture", "version": "1.0"},
            "roi_count": normalized_features.get("roi_count", 1),
            # A capture has one scale reading, while it can contain multiple
            # detected objects.  Preserve a supplied scale payload or provide
            # a deterministic value for the 1/2/3-object test sequence.
            "scale": raw_metadata.get("scale", {
                "weight_kg": normalized_features.get("scale_weight_kg", round(1.85 * object_count, 2)),
            }),
            "detections": detections,
        }
        scale_weight_kg = float(canonical_metadata["scale"]["weight_kg"])

        # The session service publishes its OpenAPI paths without the gateway
        # prefix, but the running Edge service is mounted below /api.
        session_base = f"{EDGE_SESSION_URL}/api"
        json_request(f"{session_base}/v1/weighvision/sessions", {
            "sessionId": session_id, "tenantId": tenant_id, "farmId": farm_id,
            "barnId": barn_id, "deviceId": device_id, "stationId": station_id,
            "startAt": occurred_at,
        })
        presign = json_request(f"{MEDIA_STORE_URL}/api/v1/media/images/presign", {
            "tenant_id": tenant_id, "farm_id": farm_id, "barn_id": barn_id,
            "device_id": device_id, "content_type": content_type, "filename": f"{capture_id}.jpg",
        }, headers={"x-tenant-id": tenant_id})
        upload_headers = {str(k): str(v) for k, v in (presign.get("headers") or {}).items()}
        upload_headers.setdefault("content-type", content_type)
        upload_url = presign["upload_url"]
        parsed_upload = urlparse(upload_url)
        if parsed_upload.hostname in {"localhost", "127.0.0.1"}:
            # Media Store signs the host-facing localhost URL. Inside Docker,
            # reach MinIO by its network hostname while preserving that signed Host.
            internal = urlparse(EDGE_MINIO_INTERNAL_URL)
            upload_headers["Host"] = parsed_upload.netloc
            upload_url = urlunparse(parsed_upload._replace(scheme=internal.scheme, netloc=internal.netloc))
        with urlopen(Request(upload_url, data=image, headers=upload_headers, method="PUT"), timeout=20):
            pass
        completed = json_request(f"{MEDIA_STORE_URL}/api/v1/media/images/complete", {
            "tenant_id": tenant_id, "farm_id": farm_id, "barn_id": barn_id,
            "device_id": device_id, "object_key": presign["object_key"],
            "mime_type": content_type, "size_bytes": len(image), "captured_at": occurred_at,
        }, headers={"x-tenant-id": tenant_id})
        media_id = completed["media_id"]
        json_request(f"{session_base}/v1/weighvision/sessions/{session_id}/metadata", {
            "tenantId": tenant_id, "farmId": farm_id, "barnId": barn_id,
            "deviceId": device_id, "stationId": station_id, "eventId": str(uuid.uuid4()),
            "occurredAt": occurred_at, "captureId": capture_id, "mediaIds": [media_id],
            "metadata": canonical_metadata,
            "eventSchemaVersion": "mock-v1", "sourceEventType": "mock.capture",
        })
        json_request(f"{session_base}/v1/weighvision/sessions/{session_id}/bind-media", {
            "tenantId": tenant_id, "mediaObjectId": media_id, "occurredAt": occurred_at, "eventId": str(uuid.uuid4()),
        })
        job = json_request(f"{VISION_INFERENCE_URL}/api/v1/inference/jobs", {
            "tenant_id": tenant_id, "farm_id": farm_id, "barn_id": barn_id,
            "device_id": device_id, "station_id": station_id, "session_id": session_id, "media_id": media_id,
        }, headers={"x-tenant-id": tenant_id, "x-request-id": str(uuid.uuid4())})

        # Analytics and Distribution intentionally derive their statistics from
        # finalized session measurements, not from capture metadata alone.
        # Exercise the same Edge contract an IoT scale uses, then publish the
        # final session event that the Cloud read model consumes.
        json_request(f"{session_base}/v1/weighvision/sessions/{session_id}/bind-weight", {
            "tenantId": tenant_id, "weightKg": scale_weight_kg,
            "occurredAt": occurred_at, "eventId": str(uuid.uuid4()),
        })
        json_request(f"{session_base}/v1/weighvision/sessions/{session_id}/finalize", {
            "tenantId": tenant_id, "eventId": str(uuid.uuid4()),
            "occurredAt": occurred_at, "finalWeightKg": scale_weight_kg,
            "payload": {"scale": {"weight_kg": scale_weight_kg}, "source": "vision-input-mock"},
        })
        return {
            "mode": "real-edge-integration", "mediaId": media_id, "captureId": capture_id,
            "sessionId": session_id, "objectCount": object_count,
            "objectKey": presign["object_key"], "inferenceJob": job,
        }


if __name__ == "__main__":
    def submit_periodic_captures() -> None:
        url = f"http://127.0.0.1:{PORT}/api/v1/mock/captures"
        body = json.dumps(PERIODIC_CAPTURE).encode("utf-8")
        while True:
            time.sleep(MOCK_INTERVAL_SECONDS)
            try:
                request = Request(url, data=body, headers={"content-type": "application/json"}, method="POST")
                with urlopen(request, timeout=20) as response:
                    response.read()
                print("periodic mock capture submitted", flush=True)
            except Exception as exc:
                print(f"periodic mock capture failed: {exc}", flush=True)

    print(
        f"vision-input-mock listening on :{PORT}; submitting to {VISION_INFERENCE_URL}; "
        f"media_store={MEDIA_STORE_URL or 'mock-local'}, "
        f"auto_submit={AUTO_SUBMIT_ENABLED}, interval={MOCK_INTERVAL_SECONDS}s",
        flush=True,
    )
    if AUTO_SUBMIT_ENABLED:
        threading.Thread(target=submit_periodic_captures, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
