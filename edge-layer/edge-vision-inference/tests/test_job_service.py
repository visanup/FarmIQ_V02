import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import InferenceDb
from app.inference_service import InferenceService
from app.job_service import JobService


def _swallow_task(coro):
    coro.close()
    return MagicMock()


def _temp_media_path() -> str:
    fd, path = tempfile.mkstemp(prefix="farmiq-job-service-", suffix=".img")
    os.close(fd)
    return path


@pytest.mark.unit
class TestJobService:
    def test_init(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)

        service = JobService(mock_db, mock_inference_service)

        assert service.db == mock_db
        assert service.inference_service == mock_inference_service
        assert service.jobs == {}

    @pytest.mark.asyncio
    async def test_create_job_returns_job_id(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)
        service = JobService(mock_db, mock_inference_service)

        with patch("app.job_service.asyncio.create_task", side_effect=_swallow_task):
            job = await service.create_job(
                tenant_id="tenant-1",
                farm_id="farm-1",
                barn_id="barn-1",
                device_id="device-1",
                media_id="media-1",
                object_key="object-key-1",
            )

        assert "job_id" in job
        assert job["tenant_id"] == "tenant-1"
        assert job["farm_id"] == "farm-1"
        assert job["barn_id"] == "barn-1"
        assert job["device_id"] == "device-1"
        assert job["media_id"] == "media-1"
        assert job["object_key"] == "object-key-1"
        assert job["status"] == "pending"
        assert job["job_id"] in service.jobs

    @pytest.mark.asyncio
    async def test_create_job_requires_media_id_or_object_key(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)
        service = JobService(mock_db, mock_inference_service)

        with pytest.raises(ValueError, match="media_id or object_key is required"):
            await service.create_job(
                tenant_id="tenant-1",
                farm_id="farm-1",
                barn_id="barn-1",
                device_id="device-1",
            )

    @pytest.mark.asyncio
    async def test_get_job_returns_job(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)
        service = JobService(mock_db, mock_inference_service)

        with patch("app.job_service.asyncio.create_task", side_effect=_swallow_task):
            job = await service.create_job(
                tenant_id="tenant-1",
                farm_id="farm-1",
                barn_id="barn-1",
                device_id="device-1",
                media_id="media-1",
            )

        assert await service.get_job(job["job_id"]) == job
        assert await service.get_job("missing-job-id") is None

    @pytest.mark.asyncio
    async def test_job_completes_with_shadow_sync_back_metadata(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)
        mock_inference_service.run_inference = AsyncMock(
            return_value={
                "predicted_weight_kg": 2.73,
                "confidence": 0.93,
                "model_version": "weighvision-linear-2026.07",
                "metadata": {
                    "package_id": "pkg-001",
                    "package_version": "2026.07.14",
                    "feature_schema_version": "1.0.0",
                    "activation_source": "subscription",
                    "fallback_engaged": False,
                    "prediction_mode": "shadow",
                    "features_used": {
                        "selected_area_mm2": 12500.0,
                        "selected_depth_mm": 412.0,
                    },
                },
            }
        )
        mock_db.create_inference_result = AsyncMock(return_value="result-1")
        mock_db.create_outbox_event = AsyncMock()

        service = JobService(mock_db, mock_inference_service)
        media_path = _temp_media_path()

        with patch("app.job_service.asyncio.create_task", side_effect=_swallow_task):
            job = await service.create_job(
                tenant_id="tenant-1",
                farm_id="farm-1",
                barn_id="barn-1",
                device_id="device-1",
                media_id="media-1",
                session_id="session-1",
                trace_id="trace-1",
            )

        service._fetch_media_to_tmp = AsyncMock(return_value=media_path)
        service._fetch_session_features = AsyncMock(
            return_value={
                "features": {
                    "selected_area_mm2": 12500.0,
                    "selected_depth_mm": 412.0,
                },
                "feature_schema_version": "1.0.0",
                "capture_metadata_id": "capture-1",
            }
        )
        service._attach_to_session = AsyncMock()
        service._publish_prediction_outcome_to_session = AsyncMock()

        await service._process_job(job["job_id"])

        assert job["status"] == "completed"
        assert job["result_id"] == "result-1"
        assert service._attach_to_session.await_count == 1
        assert service._publish_prediction_outcome_to_session.await_count == 1

        inference_call = mock_inference_service.run_inference.await_args
        assert inference_call.args[0] == media_path
        assert inference_call.kwargs["metadata"]["features"]["selected_area_mm2"] == 12500.0
        assert inference_call.kwargs["metadata"]["feature_schema_version"] == "1.0.0"

        outbox_payload = mock_db.create_outbox_event.await_args.kwargs["payload"]
        assert outbox_payload["inference_result_id"] == "result-1"
        assert outbox_payload["package_id"] == "pkg-001"
        assert outbox_payload["package_version"] == "2026.07.14"
        assert outbox_payload["feature_schema_version"] == "1.0.0"
        assert outbox_payload["activation_source"] == "subscription"
        assert outbox_payload["fallback_engaged"] is False
        assert outbox_payload["prediction_mode"] == "shadow"
        assert outbox_payload["features_used"]["selected_depth_mm"] == 412.0
        assert outbox_payload["occurred_at"].endswith("Z")

        publish_call = service._publish_prediction_outcome_to_session.await_args.kwargs
        assert publish_call["occurred_at"].endswith("Z")

        assert not os.path.exists(media_path)

    def test_build_shadow_features_maps_session_metadata_to_model_feature_names(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)
        service = JobService(mock_db, mock_inference_service)

        features = service._build_shadow_features(
            {
                "normalizedFeatures": {
                    "area_mm2": 12345.6,
                    "confidence_score": 0.91,
                    "distance_mm": 805.0,
                    "object_height_mm": 77.7,
                    "object_width_mm": 155.5,
                    "object_length_mm": 288.8,
                    "roi_count": 1,
                    "detection_count": 2,
                },
                "rawMetadata": {
                    "height_estimation": {
                        "floor_depth_mm": 1368.9,
                    }
                },
            }
        )

        assert features == {
            "selected_area_mm2": 12345.6,
            "selected_confidence": 0.91,
            "selected_depth_mm": 805.0,
            "selected_height_mm": 77.7,
            "selected_width_mm": 155.5,
            "selected_length_mm": 288.8,
            "floor_depth_mm": 1368.9,
            "roi_count": 1.0,
            "detection_count": 2.0,
        }

    @pytest.mark.asyncio
    async def test_job_handles_processing_errors(self):
        mock_db = MagicMock(spec=InferenceDb)
        mock_inference_service = MagicMock(spec=InferenceService)
        mock_inference_service.run_inference = AsyncMock(side_effect=Exception("Inference failed"))
        mock_db.create_inference_result = AsyncMock()
        mock_db.create_outbox_event = AsyncMock()

        service = JobService(mock_db, mock_inference_service)
        media_path = _temp_media_path()

        with patch("app.job_service.asyncio.create_task", side_effect=_swallow_task):
            job = await service.create_job(
                tenant_id="tenant-1",
                farm_id="farm-1",
                barn_id="barn-1",
                device_id="device-1",
                media_id="media-1",
            )

        service._fetch_media_to_tmp = AsyncMock(return_value=media_path)
        service._fetch_session_features = AsyncMock(return_value={})
        service._publish_prediction_outcome_to_session = AsyncMock()

        await service._process_job(job["job_id"])

        assert job["status"] == "failed"
        assert job["error"] == "Inference failed"
        assert not mock_db.create_inference_result.called
        assert not mock_db.create_outbox_event.called
        assert not os.path.exists(media_path)
