from pathlib import Path

import pytest

from app.config import Config
from app.inference_service import InferenceService
from app.job_service import JobService


def test_hybrid_trial_is_disabled_by_default():
    config = Config()
    config.HYBRID_TRIAL_ENABLED = False
    service = InferenceService(config)
    assert service.hybrid_trial is None


@pytest.mark.asyncio
async def test_hybrid_trial_runs_when_explicitly_enabled(tmp_path: Path):
    image_path = tmp_path / "capture.jpg"
    image_path.write_bytes(b"image")
    config = Config()
    config.MODEL_SYNC_ENABLED = False
    config.HYBRID_TRIAL_ENABLED = True
    config.HYBRID_TRIAL_MODEL_DIR = str(
        Path(__file__).resolve().parents[1] / "runtime-models" / "hybrid-trial-75s25v-v1-edge"
    )
    service = InferenceService(config)
    result = await service.run_inference(
        str(image_path),
        {
            "session_id": "hybrid-edge-test",
            "batch_context": {"breed_code": "Arbor Acres Plus", "sex": "male", "age_days": 11},
            "features": {
                "selected_area_mm2": 7000,
                "selected_length_mm": 110,
                "selected_width_mm": 80,
                "selected_height_mm": 50,
                "selected_depth_mm": 950,
                "selected_confidence": 0.9,
                "bbox_area_px": 30000,
                "bbox_aspect_ratio": 1.2,
                "mask_fill_ratio": 0.7,
                "is_height_outlier": 0,
            },
        },
    )
    assert result["model_version"] == "hybrid-trial-75s25v-v1"
    assert result["metadata"]["prediction_mode"] == "hybrid_trial_75s25v"
    assert result["metadata"]["hybrid_weights"] == {"standard": 0.75, "visual": 0.25}
    assert result["metadata"]["hybrid_predicted_weight_g"] == pytest.approx(
        result["predicted_weight_kg"] * 1000,
        abs=0.1,
    )
    assert result["predicted_weight_kg"] > 0


def test_single_detection_geometry_is_derived_for_hybrid_trial():
    features = JobService._build_shadow_features({
        "normalizedFeatures": {
            "area_mm2": 7000, "confidence_score": 0.9, "distance_mm": 950,
            "height_mm": 50, "width_mm": 80, "length_mm": 110,
        },
        "rawMetadata": {
            "detections": [{
                "bbox": {"x1": 10, "y1": 10, "x2": 110, "y2": 160},
                "mask_area_px2": 12000,
            }],
        },
    })
    assert features["bbox_area_px"] == 15000
    assert features["bbox_aspect_ratio"] == 100 / 150
    assert features["mask_fill_ratio"] == 0.8
    assert features["is_height_outlier"] == 0


def test_single_detection_uses_normalized_mask_area_from_real_capture_contract():
    features = JobService._build_shadow_features({
        "normalizedFeatures": {
            "area_mm2": 8064.97, "confidence_score": 0.9239,
            "distance_mm": 984.09, "object_height_mm": 30.84,
            "object_width_mm": 97.0, "object_length_mm": 110.62,
            "bbox": {"x1": 1905, "y1": 280, "x2": 2161, "y2": 520},
            "mask_area_px2": 37195.59, "detection_count": 1,
        },
        "rawMetadata": {"detections": [{"bbox_xyxy": [1905, 280, 2161, 520]}]},
    })
    assert features["bbox_area_px"] == 61440
    assert features["mask_fill_ratio"] == pytest.approx(37195.59 / 61440)
    assert features["is_height_outlier"] == 0
