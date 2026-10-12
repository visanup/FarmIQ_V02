"""Replay a recorded chicken capture through the Edge 75S/25V trial model.

Run on the dev host with: python scripts/test_real_chicken_hybrid_75_25.py
The script reads the original image/geometry export and executes the installed
Edge model in its existing container. The model uses recorded geometry and
growth context; it checks the image file but does not process its pixels.
It does not change the running service.
"""

import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path


SESSION_ID = "20260919_000740"
CONTAINER = "farmiq-edge-vision-inference"


def row_for(path, **match):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if all(row.get(key) == value for key, value in match.items()):
                return row
    raise ValueError(f"No matching row in {path.name}: {match}")


def inside():
    sys.path.insert(0, "/app")
    from app.config import Config
    from app.inference_service import InferenceService
    import asyncio

    payload = json.loads(Path("/tmp/real-chicken-75-25.json").read_text())
    config = Config()
    config.MODEL_SYNC_ENABLED = False
    config.BATCH_CONTEXT_INFERENCE_ENABLED = True
    config.HYBRID_TRIAL_ENABLED = True
    config.HYBRID_TRIAL_MODEL_DIR = "/app/runtime-models/hybrid-trial-75s25v-v1-edge"
    result = asyncio.run(InferenceService(config).run_inference("/tmp/real-chicken-75-25.jpg", payload))
    print("RESULT_JSON=" + json.dumps(result, ensure_ascii=False))


def main():
    root = Path(__file__).resolve().parents[3]
    sample = root / "cloud-layer/cloud-ml-model-service/ml_weight_prediction/docs/sample_data/session_id_20260919"
    audit_path = root / "cloud-layer/cloud-ml-model-service/ml_weight_prediction/reports/sampled_export_20260918_20260930_weak_audit.csv"
    audit = row_for(audit_path, session_id=SESSION_ID)
    capture = row_for(sample / "metadata/session_capture_metadata-1789967494963.csv", session_id=SESSION_ID)
    media = row_for(sample / "metadata/media_objects-1789967735311.csv", session_id=SESSION_ID)
    image = sample / "images" / Path(media["object_key"]).name
    if not image.is_file():
        raise FileNotFoundError(image)
    if capture["detection_count"] != "1":
        raise AssertionError("Expected one selected chicken detection in this fixture")
    if not math.isclose(float(capture["area_mm2"]), float(audit["area_mm2"]), rel_tol=1e-6):
        raise AssertionError("Audit geometry does not match capture geometry")

    feature_names = (
        "area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm",
        "confidence", "bbox_area_px", "bbox_aspect_ratio", "mask_fill_ratio",
        "is_height_outlier",
    )
    features = {name: float(audit[name]) for name in feature_names}
    features["is_height_outlier"] = int(features["is_height_outlier"])
    payload = {
        "session_id": SESSION_ID,
        "batch_context": {
            "breed_code": audit["breed"], "sex": audit["sex"],
            "age_days": int(audit["age_days"]),
        },
        "features": features,
    }
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
        fixture = Path(temp) / "real-chicken-75-25.json"
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        subprocess.run(["docker", "cp", str(fixture), f"{CONTAINER}:/tmp/real-chicken-75-25.json"], check=True)
        subprocess.run(["docker", "cp", str(image), f"{CONTAINER}:/tmp/real-chicken-75-25.jpg"], check=True)
        subprocess.run(["docker", "cp", str(Path(__file__).resolve()), f"{CONTAINER}:/tmp/real-chicken-75-25.py"], check=True)
        process = subprocess.run(
            ["docker", "exec", CONTAINER, "python", "/tmp/real-chicken-75-25.py", "--inside"],
            capture_output=True, text=True,
        )
    if process.returncode:
        raise RuntimeError(f"Inference failed ({process.returncode}): {process.stdout}\n{process.stderr}")
    marker = next((line for line in process.stdout.splitlines() if line.startswith("RESULT_JSON=")), None)
    if marker is None:
        raise RuntimeError(f"Inference produced no result: {process.stdout}\n{process.stderr}")
    result = json.loads(marker.removeprefix("RESULT_JSON="))
    metadata = result["metadata"]
    assert result["model_version"] == "hybrid-trial-75s25v-v1", result
    assert metadata["prediction_mode"] == "hybrid_trial_75s25v", result
    assert metadata["stub_mode"] is False, result
    expected_g = 0.75 * metadata["standard_weight_g"] + 0.25 * metadata["visual_standard_proxy_g"]
    assert math.isclose(metadata["hybrid_predicted_weight_g"], expected_g, rel_tol=1e-10)
    assert math.isclose(result["predicted_weight_kg"], expected_g / 1000, abs_tol=0.00005)
    print(json.dumps({
        "session_id": SESSION_ID,
        "tenant_id": media["tenant_id"], "farm_id": media["farm_id"],
        "barn_id": media["barn_id"], "device_id": media["device_id"],
        "image": str(image), "image_bytes": image.stat().st_size,
        "recorded_scale_weight_kg": float(capture["scale_weight_kg"]),
        "recorded_quality_pass": audit["quality_pass"],
        "recorded_quality_reasons": audit["quality_reasons"],
        "quality_gate_enforced_by_model": False if audit["quality_pass"] == "False" else None,
        "image_pixels_used_by_hybrid_model": False,
        "model_version": result["model_version"],
        "prediction_mode": metadata["prediction_mode"], "stub_mode": metadata["stub_mode"],
        "standard_weight_g": metadata["standard_weight_g"],
        "visual_standard_proxy_g": metadata["visual_standard_proxy_g"],
        "hybrid_predicted_weight_g": metadata["hybrid_predicted_weight_g"],
        "predicted_weight_kg": result["predicted_weight_kg"],
        "formula_verified": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--inside" in sys.argv:
        inside()
    else:
        main()
