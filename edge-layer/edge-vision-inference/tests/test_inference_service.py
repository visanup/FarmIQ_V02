import json
import tarfile
from pathlib import Path
import uuid

import pytest

from app.config import Config
from app.inference_service import InferenceService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_inference_returns_expected_shape():
    tmp_dir = Path(__file__).resolve().parent / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    image_path = tmp_dir / f"sample-{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    config = Config()
    service = InferenceService(config)

    result = await service.run_inference(str(image_path), {"session_id": "sess-1"})

    assert "predicted_weight_kg" in result
    assert "confidence" in result
    assert "model_version" in result
    assert result["metadata"]["session_id"] == "sess-1"
    image_path.unlink(missing_ok=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_run_inference_uses_activated_shadow_package():
    tmp_dir = Path(__file__).resolve().parent / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    package_version = "wv-shadow-test-1.0.0"
    package_root = tmp_dir / f"package-src-{uuid.uuid4().hex}"
    (package_root / package_version / "model").mkdir(parents=True, exist_ok=True)
    (package_root / package_version).mkdir(parents=True, exist_ok=True)

    model_payload = {
        "model_type": "linear_regression",
        "feature_order": [
            "selected_area_mm2",
            "selected_confidence",
            "selected_depth_mm",
        ],
        "feature_means": [1000.0, 0.9, 1200.0],
        "feature_stds": [100.0, 0.05, 100.0],
        "coefficients": [0.2, 0.1, 0.05],
        "intercept": 1.0,
    }
    (package_root / package_version / "model" / "model.json").write_text(
        json.dumps(model_payload),
        encoding="utf-8",
    )
    (package_root / package_version / "manifest.json").write_text(
        json.dumps({"entrypoint": "model/model.json", "packageVersion": package_version}),
        encoding="utf-8",
    )

    tarball_path = tmp_dir / f"{package_version}.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as archive:
        archive.add(package_root / package_version, arcname=package_version)

    checksum = __import__("hashlib").sha256(tarball_path.read_bytes()).hexdigest()

    config = Config()
    config.MODEL_SYNC_ENABLED = False
    config.MODEL_CACHE_DIR = str(tmp_dir / f"runtime-cache-{uuid.uuid4().hex}")
    config.MODEL_MANIFEST_PATH = str(tmp_dir / f"active-runtime-manifest-{uuid.uuid4().hex}.json")
    service = InferenceService(config)

    await service._activate_package(  # type: ignore[attr-defined]
        {
            "id": "pkg-shadow-test",
            "packageVersion": package_version,
            "checksumSha256": checksum,
            "packageUri": tarball_path.as_uri(),
            "manifest": {
                "packageVersion": package_version,
                "featureSchemaVersion": "wv-feature-schema-v1",
                "entrypoint": "model/model.json",
                "metadata": {"model_version": package_version},
            },
        },
        activation_source="manifest",
    )

    image_path = tmp_dir / f"sample-{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"fake-image-bytes-shadow")
    result = await service.run_inference(
        str(image_path),
        {
            "session_id": "sess-shadow-1",
            "features": {
                "selected_area_mm2": 1100,
                "selected_confidence": 0.95,
                "selected_depth_mm": 1300,
            },
        },
    )

    assert result["metadata"]["stub_mode"] is False
    assert result["metadata"]["prediction_mode"] == "shadow"
    assert result["metadata"]["package_id"] == "pkg-shadow-test"
    assert result["predicted_weight_kg"] > 1.0
    image_path.unlink(missing_ok=True)


@pytest.mark.unit
def test_get_model_info_uses_manifest_when_present():
    tmp_dir = Path(__file__).resolve().parent / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = tmp_dir / f"active-manifest-{uuid.uuid4().hex}.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "pkg-active",
                "packageVersion": "wv-shadow-baseline-1.0.0",
                "featureSchemaVersion": "wv-feature-schema-v1",
                "activationPolicy": {"require_checksum_validation": True},
                "fallbackPolicy": {"order": ["last_known_good", "stub_mode"]},
                "metadata": {"model_version": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )

    config = Config()
    config.MODEL_MANIFEST_PATH = str(manifest_path)
    service = InferenceService(config)

    info = service.get_model_info()

    assert info["activation_source"] == "manifest"
    assert info["package_id"] == "pkg-active"
    assert info["package_version"] == "wv-shadow-baseline-1.0.0"
    assert info["feature_schema_version"] == "wv-feature-schema-v1"
    assert info["activation_policy"]["require_checksum_validation"] is True
    manifest_path.unlink(missing_ok=True)


@pytest.mark.unit
def test_get_model_info_falls_back_to_fallback_manifest():
    tmp_dir = Path(__file__).resolve().parent / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fallback_path = tmp_dir / f"fallback-manifest-{uuid.uuid4().hex}.json"
    fallback_path.write_text(
        json.dumps(
            {
                "id": "pkg-fallback",
                "packageVersion": "wv-shadow-baseline-0.9.0",
                "featureSchemaVersion": "wv-feature-schema-v1",
                "metadata": {"model_version": "0.9.0"},
            }
        ),
        encoding="utf-8",
    )

    config = Config()
    config.MODEL_MANIFEST_PATH = str(tmp_dir / "missing.json")
    config.FALLBACK_MODEL_MANIFEST_PATH = str(fallback_path)
    service = InferenceService(config)

    info = service.get_model_info()

    assert info["activation_source"] == "fallback_manifest"
    assert info["fallback_engaged"] is True
    assert info["package_id"] == "pkg-fallback"
    assert info["model_version"] == "0.9.0"
    fallback_path.unlink(missing_ok=True)
