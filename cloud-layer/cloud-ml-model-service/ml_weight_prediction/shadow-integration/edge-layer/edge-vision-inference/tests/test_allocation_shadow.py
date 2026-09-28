import copy
import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.allocation_shadow import AllocationShadow
from app.job_service import JobService


def mock_capture():
    """Synthetic measurements, not a labelled bird or accuracy benchmark."""
    return {
        "session_id": "mock-session", "capture_id": "mock-capture", "captured_at": "2026-09-19T05:00:00Z",
        "raw_metadata": {
            "fixture_only": True, "session_id": "mock-session", "image_id": "mock-capture",
            "breed": "Arbor Acres Plus", "sex": "male", "age_days": 10,
            "image_width_px": 640, "image_height_px": 480, "roi": {"xyxy": [0, 0, 640, 480]},
            "roi_count": 2, "scale": {"weight_kg": 0.8, "weight_stable": True,
                "scale_id": "mock-scale", "calibration_version": "mock-cal-v1", "tare_verified": True},
            "detections": [
                {"detection_index": i, "area_xy_mm2": 7000 + i*500, "length_mm": 120,
                 "width_mm": 85, "height_mm": 65, "depth_mm": 950, "confidence": 0.93,
                 "bbox_xyxy": [10+i*200, 10, 110+i*200, 110],
                 "mask_xy": [[20+i*200, 20], [100+i*200, 20], [100+i*200, 100], [20+i*200, 100]]}
                for i in range(2)
            ],
        },
    }


@pytest.fixture
def runtime():
    if not os.getenv("ALLOCATION_SHADOW_PACKAGE_DIR"):
        pytest.skip("Set shadow package env for real-model integration tests")
    runner = AllocationShadow()
    assert runner.model is not None, runner.load_error
    return runner


def test_real_model_reconciles(runtime):
    result = runtime.predict(mock_capture())
    assert result["prediction_status"] == "WEAK_ALLOCATION", result
    assert len(result["allocations"]) == 2
    assert sum(r["allocated_weight_g"] for r in result["allocations"]) == pytest.approx(800, abs=0.1)
    assert result["individual_accuracy_validated"] is False
    assert result["decision_use_allowed"] is False


@pytest.mark.parametrize("failure", ["unstable", "calibration", "roi", "height", "confidence", "age", "missing", "duplicate", "identity", "nan"])
def test_reject_whole_group(runtime, failure):
    event = mock_capture()
    raw = event["raw_metadata"]
    if failure == "unstable": raw["scale"]["weight_stable"] = False
    if failure == "calibration": del raw["scale"]["calibration_version"]
    if failure == "roi": raw["detections"][0]["mask_xy"][0] = [-1, 0]
    if failure == "height": raw["detections"][0]["height_mm"] = -2
    if failure == "confidence": raw["detections"][0]["confidence"] = .2
    if failure == "age": raw["age_days"] = 1000
    if failure == "missing": raw["detections"].pop()
    if failure == "duplicate": raw["detections"][1]["detection_index"] = 0
    if failure == "identity": raw["image_id"] = "another-image"
    if failure == "nan": raw["scale"]["weight_kg"] = float("nan")
    result = runtime.predict(event)
    assert result["prediction_status"] == "REJECTED_QUALITY"
    assert result["allocations"] == []
    json.dumps(result, allow_nan=False)


def test_bad_checksum(monkeypatch, runtime):
    monkeypatch.setenv("ALLOCATION_SHADOW_MANIFEST_SHA256", "0"*64)
    rejected = AllocationShadow().predict(mock_capture())
    assert rejected["prediction_status"] == "REJECTED_MODEL_UNAVAILABLE"
    assert rejected["allocations"] == []


def test_capture_match():
    captures = [{"captureId": "wrong", "mediaIds": ["x"]},
                {"captureId": "correct", "mediaIds": ["y"], "rawMetadata": {"detections": [1, 2]}}]
    job = {"session_id": "s", "media_id": "y"}
    assert JobService._select_allocation_capture(captures, job)["capture_id"] == "correct"
    assert JobService._select_allocation_capture(captures + [captures[1]], job)["capture_id"] is None


@pytest.mark.asyncio
async def test_shadow_failure_does_not_change_legacy(tmp_path, runtime):
    import asyncio
    image = tmp_path / "mock.jpg"
    image.write_bytes(b"fixture")
    db = MagicMock()
    db.create_inference_result = AsyncMock(return_value="legacy-result")
    db.create_outbox_event = AsyncMock()
    db.save_shadow_allocation = AsyncMock(side_effect=RuntimeError("mock database failure"))
    inference = MagicMock()
    inference.run_inference = AsyncMock(return_value={"predicted_weight_kg": 1.23, "confidence": .9, "model_version": "legacy", "metadata": {}})
    service = JobService(db, inference)
    service._fetch_session_features = AsyncMock(return_value={"allocation_capture": mock_capture()})
    service._fetch_media_to_tmp = AsyncMock(return_value=str(image))
    service._attach_to_session = AsyncMock()
    service._publish_prediction_outcome_to_session = AsyncMock()
    job = {"job_id": "j", "tenant_id": "t", "farm_id": "f", "barn_id": "b", "device_id": "d", "session_id": "s", "trace_id": "trace"}
    service.jobs["j"] = job
    await service._process_job("j")
    await asyncio.gather(*service.shadow_tasks)
    assert job["status"] == "completed"
    assert db.create_inference_result.await_args.kwargs["predicted_weight_kg"] == 1.23
    assert db.create_outbox_event.await_count == 1
    assert db.save_shadow_allocation.await_count == 1


@pytest.mark.asyncio
async def test_postgres_atomic_idempotent(runtime):
    from app.db import InferenceDb
    url = os.getenv("SHADOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires isolated shadow PostgreSQL")
    db = InferenceDb(url)
    await db.connect()
    try:
        await db.ensure_schema()
        job = {"tenant_id": "mock-tenant", "job_id": str(uuid.uuid4()), "session_id": "mock-session"}
        result = runtime.predict(mock_capture())
        first = await db.save_shadow_allocation(job, result)
        assert await db.save_shadow_allocation(job, result) == first
        async with db.pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM session_bird_allocations WHERE event_id=$1::uuid", first) == 2
            assert await conn.fetchval("SELECT sum(allocated_weight_g) FROM session_bird_allocations WHERE event_id=$1::uuid", first) == pytest.approx(800, abs=.1)
            assert await conn.fetchval("SELECT delivery_status FROM allocation_shadow_events WHERE event_id=$1::uuid", first) == "held_shadow"
        broken = copy.deepcopy(result)
        broken["allocations"][1]["allocated_weight_g"] = -1
        job["job_id"] = str(uuid.uuid4())
        with pytest.raises(Exception):
            await db.save_shadow_allocation(job, broken)
        broken_id = uuid.uuid5(uuid.NAMESPACE_URL, f"allocation:{job['tenant_id']}:{job['job_id']}:{result['model_version']}")
        async with db.pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM allocation_shadow_events WHERE event_id=$1", broken_id) == 0
    finally:
        await db.close()
