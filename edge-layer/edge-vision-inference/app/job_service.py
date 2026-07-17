"""Job service for managing inference jobs."""
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import os
import tempfile
import json
import urllib.request
import urllib.parse
import asyncio
from app.db import InferenceDb
from app.inference_service import InferenceService
from app.config import Config

logger = logging.getLogger(__name__)


def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class JobService:
    """Service for managing inference jobs."""
    
    def __init__(self, db: InferenceDb, inference_service: InferenceService):
        self.db = db
        self.inference_service = inference_service
        self.jobs: Dict[str, Dict[str, Any]] = {}  # In-memory job store (MVP)
    
    async def create_job(
        self,
        tenant_id: str,
        farm_id: str,
        barn_id: str,
        device_id: str,
        station_id: str = "",
        media_id: Optional[str] = None,
        object_key: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new inference job."""
        if not media_id and not object_key:
            raise ValueError("media_id or object_key is required")
        job_id = str(uuid.uuid4())
        
        job = {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "farm_id": farm_id,
            "barn_id": barn_id,
            "device_id": device_id,
            "station_id": station_id,
            "media_id": media_id,
            "object_key": object_key,
            "session_id": session_id,
            "trace_id": trace_id or Config.new_id(),
            "status": "pending",
            "created_at": _utc_now_iso_z(),
            "updated_at": _utc_now_iso_z()
        }
        
        self.jobs[job_id] = job
        
        # Run inference asynchronously (fire and forget for MVP)
        asyncio.create_task(self._process_job(job_id))
        
        return job
    
    async def _process_job(self, job_id: str):
        """Process an inference job."""
        job = self.jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        try:
            job["status"] = "processing"
            job["updated_at"] = _utc_now_iso_z()
            session_features = await self._fetch_session_features(job)

            tmp_path = None
            try:
                tmp_path = await self._fetch_media_to_tmp(job)

                inference_result = await self.inference_service.run_inference(
                    tmp_path,
                    metadata={
                        "job_id": job_id,
                        "media_id": job.get("media_id"),
                        "session_id": job.get("session_id"),
                        **session_features,
                    }
                )
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            
            # Save inference result to database
            result_id = await self.db.create_inference_result(
                result_id=job_id,
                tenant_id=job["tenant_id"],
                farm_id=job["farm_id"],
                barn_id=job["barn_id"],
                device_id=job["device_id"],
                session_id=job.get("session_id"),
                media_id=job.get("media_id") or None,
                predicted_weight_kg=inference_result["predicted_weight_kg"],
                confidence=inference_result["confidence"],
                model_version=inference_result["model_version"],
                metadata=inference_result.get("metadata")
            )
            
            # Create outbox event
            occurred_at = _utc_now_iso_z()
            await self.db.create_outbox_event(
                event_id=job_id,
                tenant_id=job["tenant_id"],
                farm_id=job["farm_id"],
                barn_id=job["barn_id"],
                device_id=job["device_id"],
                session_id=job.get("session_id"),
                event_type="inference.completed",
                payload={
                    "inference_result_id": result_id,
                    "media_id": job.get("media_id") or None,
                    "session_id": job.get("session_id"),
                    "predicted_weight_kg": inference_result["predicted_weight_kg"],
                    "confidence": inference_result["confidence"],
                    "model_version": inference_result["model_version"],
                    "package_id": inference_result.get("metadata", {}).get("package_id"),
                    "package_version": inference_result.get("metadata", {}).get("package_version"),
                    "feature_schema_version": inference_result.get("metadata", {}).get("feature_schema_version"),
                    "activation_source": inference_result.get("metadata", {}).get("activation_source"),
                    "fallback_engaged": inference_result.get("metadata", {}).get("fallback_engaged"),
                    "prediction_mode": inference_result.get("metadata", {}).get("prediction_mode"),
                    "features_used": inference_result.get("metadata", {}).get("features_used"),
                    "occurred_at": occurred_at,
                    "tenant_id": job["tenant_id"] or None,
                    "farm_id": job.get("farm_id") or None,
                    "barn_id": job.get("barn_id") or None,
                    "device_id": job.get("device_id") or None,
                },
                trace_id=job["trace_id"]
            )

            # Best-effort session attach (does not emit outbox).
            if job.get("session_id"):
                await self._attach_to_session(job, result_id)
                await self._publish_prediction_outcome_to_session(
                    job=job,
                    inference_result_id=result_id,
                    inference_result=inference_result,
                    occurred_at=occurred_at,
                )
            
            # Update job status
            job["status"] = "completed"
            job["result_id"] = result_id
            job["updated_at"] = _utc_now_iso_z()
            
            logger.info("Job completed", extra={"job_id": job_id, "result_id": result_id, "trace_id": job.get("trace_id")})
            
        except Exception as e:
            logger.error("Job failed", extra={"job_id": job_id, "error": str(e)}, exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            job["updated_at"] = _utc_now_iso_z()

    async def _fetch_media_to_tmp(self, job: Dict[str, Any]) -> str:
        tenant_id = job.get("tenant_id")
        media_id = job.get("media_id")
        object_key = job.get("object_key")
        if not tenant_id or (not media_id and not object_key):
            raise ValueError("tenant_id and (media_id or object_key) required to fetch media")

        if media_id:
            url = f"{Config().MEDIA_STORE_URL}/api/v1/media/objects/{media_id}"
        else:
            url = f"{Config().MEDIA_STORE_URL}/api/v1/media/objects/by-key?object_key={urllib.parse.quote(str(object_key))}"
        headers = {
            "x-tenant-id": tenant_id,
            "x-request-id": job.get("job_id", Config.new_id()),
            "x-trace-id": job.get("trace_id", Config.new_id()),
        }

        def _download() -> bytes:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()

        data = await asyncio.to_thread(_download)

        fd, path = tempfile.mkstemp(prefix="farmiq_infer_", suffix=".img")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(data)
        return path

    async def _fetch_session_features(self, job: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = job.get("tenant_id")
        session_id = job.get("session_id")
        if not tenant_id or not session_id:
            return {}

        url = f"{Config().WEIGHVISION_SESSION_URL}/api/v1/weighvision/sessions/{session_id}"
        query = urllib.parse.urlencode({"tenantId": tenant_id})
        headers = {
            "x-tenant-id": tenant_id,
            "x-request-id": job.get("job_id", Config.new_id()),
            "x-trace-id": job.get("trace_id", Config.new_id()),
        }

        def _load() -> Dict[str, Any]:
            request = urllib.request.Request(f"{url}?{query}", headers=headers, method="GET")
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))

            capture_metadata = payload.get("captureMetadata") or []
            if not capture_metadata:
                return {}

            latest_capture = capture_metadata[-1]
            normalized_features = self._build_shadow_features(latest_capture)
            return {
                "features": normalized_features,
                "feature_schema_version": latest_capture.get("featureSchemaVersion"),
                "capture_metadata_id": latest_capture.get("captureId"),
            }

        try:
            return await asyncio.to_thread(_load)
        except Exception as exc:
            logger.warning("Unable to fetch session features for shadow inference: %s", exc)
            return {}

    def _build_shadow_features(self, capture_metadata: Dict[str, Any]) -> Dict[str, float]:
        normalized = capture_metadata.get("normalizedFeatures") or {}
        raw_metadata = capture_metadata.get("rawMetadata") or {}
        height_estimation = raw_metadata.get("height_estimation") or {}

        def _to_float(value: Any) -> Optional[float]:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str) and value.strip():
                try:
                    return float(value)
                except ValueError:
                    return None
            return None

        feature_map = {
            "selected_area_mm2": normalized.get("area_mm2"),
            "selected_confidence": normalized.get("confidence_score"),
            "selected_depth_mm": normalized.get("distance_mm")
            or normalized.get("average_depth_mm")
            or normalized.get("median_depth_mm"),
            "selected_height_mm": normalized.get("object_height_mm"),
            "selected_width_mm": normalized.get("object_width_mm"),
            "selected_length_mm": normalized.get("object_length_mm"),
            "floor_depth_mm": height_estimation.get("floor_depth_mm"),
            "roi_count": normalized.get("roi_count"),
            "detection_count": normalized.get("detection_count"),
        }

        result: Dict[str, float] = {}
        for key, value in feature_map.items():
            parsed = _to_float(value)
            if parsed is not None:
                result[key] = parsed
        return result

    async def _attach_to_session(self, job: Dict[str, Any], inference_result_id: str) -> None:
        tenant_id = job.get("tenant_id")
        session_id = job.get("session_id")
        if not tenant_id or not session_id:
            return

        url = f"{Config().WEIGHVISION_SESSION_URL}/api/v1/weighvision/sessions/{session_id}/attach"
        body = json.dumps({
            "media_id": job.get("media_id"),
            "inference_result_id": inference_result_id,
        }).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-tenant-id": tenant_id,
            "x-request-id": job.get("job_id", Config.new_id()),
            "x-trace-id": job.get("trace_id", Config.new_id()),
        }

        def _post():
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()

        try:
            await asyncio.to_thread(_post)
        except Exception as e:
            logger.warning(f"Attach failed: {e}")

    async def _publish_prediction_outcome_to_session(
        self,
        job: Dict[str, Any],
        inference_result_id: str,
        inference_result: Dict[str, Any],
        occurred_at: str,
    ) -> None:
        tenant_id = job.get("tenant_id")
        session_id = job.get("session_id")
        if not tenant_id or not session_id:
            return

        metadata = inference_result.get("metadata") or {}
        url = (
            f"{Config().WEIGHVISION_SESSION_URL}/api/v1/weighvision/sessions/"
            f"{session_id}/inference-outcome"
        )
        payload = {
            "tenantId": tenant_id,
            "farmId": job.get("farm_id"),
            "barnId": job.get("barn_id"),
            "deviceId": job.get("device_id"),
            "stationId": job.get("station_id"),
            "eventId": job.get("job_id", Config.new_id()),
            "occurredAt": occurred_at,
            "inferenceResultId": inference_result_id,
            "mediaId": job.get("media_id"),
            "captureMetadataId": metadata.get("capture_metadata_id"),
            "predictedWeightKg": inference_result.get("predicted_weight_kg"),
            "confidence": inference_result.get("confidence"),
            "modelVersion": inference_result.get("model_version"),
            "packageId": metadata.get("package_id"),
            "packageVersion": metadata.get("package_version"),
            "featureSchemaVersion": metadata.get("feature_schema_version"),
            "activationSource": metadata.get("activation_source"),
            "fallbackEngaged": metadata.get("fallback_engaged"),
            "predictionMode": metadata.get("prediction_mode"),
            "featuresUsed": metadata.get("features_used"),
        }
        body = json.dumps(
            {
                key: value
                for key, value in payload.items()
                if value is not None and (not isinstance(value, str) or value != "")
            }
        ).encode("utf-8")
        headers = {
            "content-type": "application/json",
            "x-tenant-id": tenant_id,
            "x-request-id": job.get("job_id", Config.new_id()),
            "x-trace-id": job.get("trace_id", Config.new_id()),
        }

        def _post():
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()

        try:
            await asyncio.to_thread(_post)
        except Exception as e:
            logger.warning(f"Prediction outcome publish failed: {e}")
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        return self.jobs.get(job_id)
    
    async def get_results_by_session(
        self, session_id: str, limit: int = 100
    ) -> list:
        """Get inference results by session ID."""
        return await self.db.get_inference_results_by_session(session_id, limit)
