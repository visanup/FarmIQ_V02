"""A dependency-free Dev mock for feeding images and capture metadata to vision inference."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError


VISION_INFERENCE_URL = os.getenv("VISION_INFERENCE_URL", "http://edge-vision-inference:8000")
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

        if parsed.path.endswith("/attach"):
            self.read_json()
            self.json_response(HTTPStatus.OK, {"attached": True})
            return

        self.json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

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
        f"auto_submit={AUTO_SUBMIT_ENABLED}, interval={MOCK_INTERVAL_SECONDS}s",
        flush=True,
    )
    if AUTO_SUBMIT_ENABLED:
        threading.Thread(target=submit_periodic_captures, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
