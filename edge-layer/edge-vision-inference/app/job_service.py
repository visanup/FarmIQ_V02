"""Job service for managing inference jobs."""
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
        from app.allocation_shadow import AllocationShadow
        self.allocation_shadow = AllocationShadow()
        self.shadow_tasks = set()
        self.shadow_lock = asyncio.Lock()
        self.historical_semaphore = asyncio.Semaphore(
            max(1, Config.HISTORICAL_REPROCESS_CONCURRENCY)
        )
        self.active_realtime_jobs = 0
    
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
        trace_id: Optional[str] = None,
        job_type: str = "inference",
        historical_job_id: Optional[str] = None,
        revision_of: Optional[str] = None,
        historical_context: Optional[Dict[str, Any]] = None,
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
            "job_type": job_type,
            "historical_job_id": historical_job_id,
            "revision_of": revision_of,
            "historical_context": historical_context,
            "status": "queued" if job_type == "historical-reprocess" else "pending",
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
        is_historical = job.get("job_type") == "historical-reprocess"
        acquired_historical_slot = False
        if is_historical:
            # Historical work waits whenever realtime is active, then takes a
            # dedicated low-concurrency slot. It never queues ahead of live
            # capture processing.
            while True:
                if job.get("status") == "cancelled":
                    return
                if self.active_realtime_jobs >= Config.HISTORICAL_PAUSE_REALTIME_ACTIVE:
                    job["status"] = "paused"
                    job["pause_reason"] = "realtime_capacity"
                    job["updated_at"] = _utc_now_iso_z()
                    await asyncio.sleep(0.25)
                    continue
                await self.historical_semaphore.acquire()
                acquired_historical_slot = True
                if self.active_realtime_jobs < Config.HISTORICAL_PAUSE_REALTIME_ACTIVE:
                    break
                self.historical_semaphore.release()
                acquired_historical_slot = False
        else:
            self.active_realtime_jobs += 1
        try:
            if job.get("status") == "cancelled":
                return
            job["status"] = "processing"
            job["updated_at"] = _utc_now_iso_z()
            if Config.TEST_PROCESSING_DELAY_MS > 0:
                await asyncio.sleep(Config.TEST_PROCESSING_DELAY_MS / 1000)
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
                        "inference_kind": job.get("job_type", "inference"),
                        "historical_job_id": job.get("historical_job_id"),
                        "revision_of": job.get("revision_of"),
                        **{key: value for key, value in session_features.items() if key != "allocation_capture"},
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
            provenance = inference_result.get("metadata", {}).get("batch_context_provenance")
            provenance_context = provenance.get("context") if isinstance(provenance, dict) else None
            station_id = job.get("station_id") or (
                provenance_context.get("stationId") if isinstance(provenance_context, dict) else None
            )
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
                    "fallback_reason": inference_result.get("metadata", {}).get("fallback_reason"),
                    "prediction_mode": inference_result.get("metadata", {}).get("prediction_mode"),
                    "features_used": inference_result.get("metadata", {}).get("features_used"),
                    "batch_id": inference_result.get("metadata", {}).get("batch_id"),
                    "batch_context_revision": inference_result.get("metadata", {}).get("batch_context_revision"),
                    "batch_context_resolution": inference_result.get("metadata", {}).get("batch_context_resolution"),
                    "batch_context_reason": inference_result.get("metadata", {}).get("batch_context_reason"),
                    "batch_context_provenance": inference_result.get("metadata", {}).get("batch_context_provenance"),
                    # Media completion does not carry a station field.  When a
                    # job is session-scoped, forward the immutable session
                    # provenance so Cloud can materialize the same station scope.
                    "station_id": station_id,
                    "species": inference_result.get("metadata", {}).get("species"),
                    "breed_code": inference_result.get("metadata", {}).get("breed_code"),
                    "sex": inference_result.get("metadata", {}).get("sex"),
                    "age_days": inference_result.get("metadata", {}).get("age_days"),
                    "model_selection": inference_result.get("metadata", {}).get("model_selection"),
                    "inference_kind": job.get("job_type", "inference"),
                    "historical_job_id": job.get("historical_job_id"),
                    "revision_of": job.get("revision_of"),
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
            if self.allocation_shadow.enabled and len(self.shadow_tasks) < 8:
                task = asyncio.create_task(self._run_allocation_shadow(job, session_features))
                self.shadow_tasks.add(task)
                task.add_done_callback(self.shadow_tasks.discard)
            elif self.allocation_shadow.enabled:
                logger.warning("Shadow allocation skipped: bounded queue full", extra={"job_id": job_id})
            
            logger.info("Job completed", extra={"job_id": job_id, "result_id": result_id, "trace_id": job.get("trace_id")})
            
        except Exception as e:
            logger.error("Job failed", extra={"job_id": job_id, "error": str(e)}, exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            job["updated_at"] = _utc_now_iso_z()
        finally:
            if acquired_historical_slot:
                self.historical_semaphore.release()
            if not is_historical:
                self.active_realtime_jobs = max(0, self.active_realtime_jobs - 1)

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
            latest_capture = capture_metadata[-1] if capture_metadata else None
            normalized_features = self._build_shadow_features(latest_capture) if latest_capture else {}
            return {
                "features": normalized_features,
                "feature_schema_version": latest_capture.get("featureSchemaVersion") if latest_capture else None,
                "capture_metadata_id": latest_capture.get("captureId") if latest_capture else None,
                "allocation_capture": self._select_allocation_capture(capture_metadata, job),
                # A session without optional capture metadata still has immutable
                # batch provenance.  Its start time is the best available event
                # timestamp for deriving age at inference time.
                "session_started_at": payload.get("startAt") or payload.get("start_at"),
                "batch_id": payload.get("batchId") or payload.get("batch_id"),
                "session_batch_context": {
                    "revision": payload.get("batchContextRevision") or payload.get("batch_context_revision"),
                    "resolution": payload.get("batchContextResolution") or payload.get("batch_context_resolution"),
                    "reason": payload.get("batchContextReason") or payload.get("batch_context_reason"),
                    "provenance": payload.get("batchContextProvenance") or payload.get("batch_context_provenance"),
                },
            }

        try:
            features = await asyncio.to_thread(_load)
            snapshot = job.get("historical_context")
            if job.get("job_type") == "historical-reprocess" and isinstance(snapshot, dict):
                features["batch_id"] = snapshot.get("batchId")
                features["session_batch_context"] = {
                    "revision": snapshot.get("revision"),
                    "resolution": "resolved",
                    "reason": None,
                    "provenance": {"source": "cloud-historical-dispatcher", "context": snapshot},
                }
            allocation_capture = features.get("allocation_capture") or {}
            if Config().BATCH_CONTEXT_INFERENCE_ENABLED:
                batch_context = self._batch_context_from_session(
                    features.get("batch_id"),
                    features.get("session_batch_context") or {},
                    job,
                    allocation_capture.get("captured_at") or features.get("session_started_at"),
                )
            else:
                # Legacy path retained behind the feature flag for rollback only.
                batch_context = await self._fetch_batch_context(
                    job,
                    features.get("batch_id"),
                    allocation_capture.get("captured_at") or features.get("session_started_at"),
                )
            if batch_context:
                features["batch_context"] = batch_context
                raw_metadata = dict(allocation_capture.get("raw_metadata") or {})
                # Batch master data is authoritative at inference time. Detection-level
                # values, when explicitly present, retain their documented override role.
                raw_metadata.update(batch_context)
                features["allocation_capture"] = {**allocation_capture, "raw_metadata": raw_metadata}
            return features
        except Exception as exc:
            logger.warning("Unable to fetch session features for shadow inference: %s", exc)
            return {}

    @staticmethod
    def _batch_context_from_session(
        batch_id: Optional[str],
        session_context: Dict[str, Any],
        job: Dict[str, Any],
        captured_at: Optional[str],
    ) -> Dict[str, Any]:
        """Use immutable local session provenance; do not call Cloud from inference."""
        resolution = session_context.get("resolution")
        reason = session_context.get("reason")
        provenance = session_context.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
        context = provenance.get("context")
        if not isinstance(context, dict):
            context = {}

        base = {
            "batch_id": batch_id,
            "batch_context_revision": session_context.get("revision"),
            "batch_context_resolution": resolution or "unassigned",
            "batch_context_reason": reason,
            "batch_context_provenance": provenance,
            "model_policy": context.get("modelPolicy") or {},
            "fallback_engaged": False,
            "fallback_reason": None,
        }
        if resolution != "resolved" or not batch_id:
            return {
                **base,
                "fallback_engaged": True,
                "fallback_reason": reason or "BATCH_CONTEXT_UNASSIGNED",
            }

        if (
            context.get("tenantId") != job.get("tenant_id")
            or context.get("farmId") != job.get("farm_id")
            or context.get("barnId") != job.get("barn_id")
            or context.get("batchId") != batch_id
        ):
            return {**base, "fallback_engaged": True, "fallback_reason": "BATCH_CONTEXT_SCOPE_MISMATCH"}

        breed = context.get("breedCode")
        sex = context.get("sex")
        start_date = context.get("startDate")
        if not breed or not sex or not start_date or not captured_at:
            return {**base, "fallback_engaged": True, "fallback_reason": "BATCH_ML_CONTEXT_INCOMPLETE"}

        try:
            farm_timezone = ZoneInfo(Config.FARM_TIMEZONE)
            start = datetime.fromisoformat(str(start_date).replace("Z", "+00:00")).astimezone(farm_timezone).date()
            captured = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00")).astimezone(farm_timezone).date()
            age_days = (captured - start).days
        except (TypeError, ValueError):
            return {**base, "fallback_engaged": True, "fallback_reason": "BATCH_CONTEXT_DATE_INVALID"}
        if age_days < 0:
            return {**base, "fallback_engaged": True, "fallback_reason": "BATCH_START_AFTER_CAPTURE"}

        model_policy = base["model_policy"]
        fallback_reason = model_policy.get("fallbackReason") if isinstance(model_policy, dict) else None
        fallback_only = bool(model_policy.get("fallbackOnly")) if isinstance(model_policy, dict) else True
        return {
            **base,
            "species": context.get("species"),
            "breed_code": breed,
            "breed": breed,
            "sex": sex,
            "age_days": age_days,
            "fallback_engaged": fallback_only,
            "fallback_reason": fallback_reason if fallback_only else None,
        }

    async def _fetch_batch_context(
        self,
        job: Dict[str, Any],
        batch_id: Optional[str],
        captured_at: Optional[str],
    ) -> Dict[str, Any]:
        """Resolve ML context from the cloud batch record without persisting a copy on edge."""
        config = Config()
        tenant_id = job.get("tenant_id")
        if not batch_id or not tenant_id or not config.MODEL_CONTROL_BFF_URL:
            return {}

        url = (
            f"{config.MODEL_CONTROL_BFF_URL.rstrip('/')}"
            f"/api/v1/batches/{urllib.parse.quote(str(batch_id))}?"
            f"{urllib.parse.urlencode({'tenantId': tenant_id})}"
        )
        headers = {
            "x-tenant-id": tenant_id,
            "x-request-id": job.get("job_id", Config.new_id()),
            "x-trace-id": job.get("trace_id", Config.new_id()),
        }
        if config.MODEL_CONTROL_TOKEN:
            headers["Authorization"] = f"Bearer {config.MODEL_CONTROL_TOKEN}"

        def _load() -> Dict[str, Any]:
            request = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(request, timeout=config.MODEL_CONTROL_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            batch = payload.get("data", payload) if isinstance(payload, dict) else {}
            return self._batch_context_from_record(batch, job, captured_at)

        try:
            return await asyncio.to_thread(_load)
        except Exception as exc:
            logger.warning("Unable to resolve batch ML context for %s: %s", batch_id, exc)
            return {}

    @staticmethod
    def _batch_context_from_record(batch: Dict[str, Any], job: Dict[str, Any], captured_at: Optional[str]) -> Dict[str, Any]:
        if (
            batch.get("tenantId") != job.get("tenant_id")
            or batch.get("farmId") != job.get("farm_id")
            or batch.get("barnId") != job.get("barn_id")
        ):
            raise ValueError("batch_scope_mismatch")
        breed = batch.get("breedCode") or batch.get("breed_code")
        sex = batch.get("sex")
        start_date = batch.get("startDate") or batch.get("start_date")
        if not breed or not sex or not start_date or not captured_at:
            raise ValueError("batch_ml_context_incomplete")
        farm_timezone = ZoneInfo(Config.FARM_TIMEZONE)
        start = datetime.fromisoformat(str(start_date).replace("Z", "+00:00")).astimezone(farm_timezone).date()
        captured = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00")).astimezone(farm_timezone).date()
        age_days = (captured - start).days
        if age_days < 1:
            raise ValueError("batch_start_date_not_before_capture")
        return {
            "batch_id": batch.get("id"),
            "species": batch.get("species"),
            "breed": breed,
            "sex": sex,
            "age_days": age_days,
        }

    @staticmethod
    def _select_allocation_capture(captures, job):
        # Media-to-capture linkage is mandatory. Never use an arbitrary latest capture.
        matches = [c for c in captures if job.get("media_id") and job["media_id"] in (c.get("mediaIds") or [])]
        if len(matches) != 1:
            return {"session_id": job.get("session_id"), "capture_id": None, "raw_metadata": {}}
        capture = matches[0]
        return {"session_id": job.get("session_id"), "capture_id": capture.get("captureId"),
                "captured_at": capture.get("occurredAt"), "raw_metadata": capture.get("rawMetadata") or {}}

    async def _run_allocation_shadow(self, job, session_features):
        try:
            event = session_features.get("allocation_capture") or {"session_id": job.get("session_id")}
            async with self.shadow_lock:
                result = await asyncio.to_thread(self.allocation_shadow.predict, event)
                await self.db.save_shadow_allocation(job, result)
        except Exception:
            logger.exception("Shadow allocation failed; legacy job remains completed", extra={"job_id": job["job_id"]})

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
            "fallbackReason": metadata.get("fallback_reason"),
            "predictionMode": metadata.get("prediction_mode"),
            "featuresUsed": metadata.get("features_used"),
            "batchId": metadata.get("batch_id"),
            "batchContextRevision": metadata.get("batch_context_revision"),
            "batchContextResolution": metadata.get("batch_context_resolution"),
            "batchContextReason": metadata.get("batch_context_reason"),
            "batchContextProvenance": metadata.get("batch_context_provenance"),
            "species": metadata.get("species"),
            "breedCode": metadata.get("breed_code"),
            "sex": metadata.get("sex"),
            "ageDays": metadata.get("age_days"),
            "modelSelection": metadata.get("model_selection"),
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

    async def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.get("job_type") != "historical-reprocess":
            return False
        if job.get("status") not in {"queued", "paused"}:
            return False
        job["status"] = "cancelled"
        job["updated_at"] = _utc_now_iso_z()
        return True

    async def resume_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.get("job_type") != "historical-reprocess":
            return False
        if job.get("status") != "paused":
            return False
        job["status"] = "queued"
        job.pop("pause_reason", None)
        job["updated_at"] = _utc_now_iso_z()
        return True

    def scheduler_state(self) -> Dict[str, Any]:
        return {
            "realtime_active": self.active_realtime_jobs,
            "historical_concurrency": Config.HISTORICAL_REPROCESS_CONCURRENCY,
            "historical_pause_realtime_active": Config.HISTORICAL_PAUSE_REALTIME_ACTIVE,
            "historical_enabled": Config.HISTORICAL_REPROCESS_ENABLED,
        }
    
    async def get_results_by_session(
        self, session_id: str, limit: int = 100
    ) -> list:
        """Get inference results by session ID."""
        return await self.db.get_inference_results_by_session(session_id, limit)
