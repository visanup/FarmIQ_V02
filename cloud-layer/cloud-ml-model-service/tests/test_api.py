from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://test")

from app.config import Settings
from app.main import create_app
from app.routes import model_response_from_row, package_response_from_row


def make_app():
    return create_app(Settings(database_url="postgresql://test", testing=True))


def auth_headers(tenant_id: str = "tenant-batch4") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tenant_id}",
        "x-request-id": "req-batch4",
        "x-trace-id": "trace-batch4",
    }


def test_dataset_contract_is_available():
    with TestClient(make_app()) as client:
        res = client.get("/api/v1/ml/weighvision/dataset-contract", headers=auth_headers())

        assert res.status_code == 200
        body = res.json()
        assert body["contractName"] == "farmiq.weighvision.weight-prediction-training-dataset"
        assert body["featureSchemaVersion"] == "wv-feature-schema-v1"
        assert any(field["name"] == "selected_depth_mm" for field in body["featureFields"])
        assert any(field["name"] == "final_weight_kg" for field in body["labelFields"])


def test_bootstrap_baseline_creates_model_and_package():
    with TestClient(make_app()) as client:
        res = client.post("/api/v1/ml/weighvision/bootstrap-baseline", headers=auth_headers())

        assert res.status_code == 201
        body = res.json()
        assert body["model"]["name"] == "weighvision-weight-shadow-baseline"
        assert body["model"]["status"] == "trained"
        assert body["package"]["approvalState"] == "published"
        assert body["package"]["manifest"]["channel"] == "stable"
        assert body["package"]["manifest"]["featureSchemaVersion"] == "wv-feature-schema-v1"


def test_subscription_resolve_and_ack_flow():
    with TestClient(make_app()) as client:
        bootstrap = client.post("/api/v1/ml/weighvision/bootstrap-baseline", headers=auth_headers()).json()
        package_id = bootstrap["package"]["id"]

        upsert_res = client.put(
            "/api/v1/ml/weighvision/model-subscriptions/sites/site-a",
            headers=auth_headers(),
            json={
                "tenantId": "tenant-batch4",
                "siteId": "site-a",
                "farmId": "farm-a",
                "barnId": "barn-a",
                "channel": "pinned",
                "pinnedPackageId": package_id,
                "fallbackPackageId": package_id,
                "notes": "Batch 4 local control-plane proof",
            },
        )
        assert upsert_res.status_code == 200
        assert upsert_res.json()["channel"] == "pinned"

        resolve_res = client.get(
            "/api/v1/ml/weighvision/model-subscriptions/sites/site-a/resolve",
            headers=auth_headers(),
        )
        assert resolve_res.status_code == 200
        resolved = resolve_res.json()
        assert resolved["activePackage"]["id"] == package_id
        assert resolved["fallbackPackage"]["id"] == package_id
        assert resolved["activationPolicy"]["require_checksum_validation"] is True

        ack_res = client.post(
            "/api/v1/ml/weighvision/model-subscriptions/sites/site-a/ack",
            headers=auth_headers(),
            json={
                "tenantId": "tenant-batch4",
                "packageId": package_id,
                "ackType": "validated",
                "status": "ok",
                "detail": "manifest checksum and feature schema accepted",
                "payload": {"edgeRuntime": "1.0.0"},
            },
        )
        assert ack_res.status_code == 201
        ack = ack_res.json()
        assert ack["siteId"] == "site-a"
        assert ack["packageId"] == package_id
        assert ack["ackType"] == "validated"
        assert ack["status"] == "ok"


def test_train_baseline_creates_artifact_and_download():
    tmp_dir = Path(__file__).resolve().parent / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = tmp_dir / "baseline-dataset.csv"
    dataset_path.write_text(
        "\n".join(
            [
                "metadata_file,session_id,capture_id,timestamp,weight_kg,selected_area_mm2,selected_confidence,selected_depth_mm,selected_height_mm,selected_width_mm,selected_length_mm,floor_depth_mm,roi_count,detection_count",
                "a.json,s1,c1,2026-02-10T07:31:43,1.10,1000,0.90,1200,50,80,150,1300,1,1",
                "b.json,s2,c2,2026-02-10T07:32:43,1.25,1100,0.91,1220,55,81,152,1300,1,1",
                "c.json,s3,c3,2026-02-10T07:33:43,1.30,1200,0.92,1240,58,85,154,1300,1,1",
                "d.json,s4,c4,2026-02-10T07:34:43,1.38,1300,0.93,1260,61,89,156,1300,1,1",
                "e.json,s5,c5,2026-02-10T07:35:43,1.45,1400,0.94,1280,64,91,158,1300,1,1",
                "f.json,s6,c6,2026-02-10T07:36:43,1.52,1500,0.95,1300,68,94,160,1300,1,1",
                "g.json,s7,c7,2026-02-10T07:37:43,1.60,1600,0.96,1320,71,98,162,1300,1,1",
                "h.json,s8,c8,2026-02-10T07:38:43,1.72,1700,0.97,1340,76,101,165,1300,1,1",
                "i.json,s9,c9,2026-02-10T07:39:43,1.80,1800,0.98,1360,80,105,168,1300,1,1",
                "j.json,s10,c10,2026-02-10T07:40:43,1.92,1900,0.99,1380,85,110,170,1300,1,1",
            ]
        ),
        encoding="utf-8",
    )

    with TestClient(make_app()) as client:
        train_res = client.post(
            "/api/v1/ml/weighvision/train-baseline",
            headers=auth_headers(),
            json={"datasetPath": str(dataset_path), "packageVersion": "wv-shadow-test-1.0.0"},
        )

        assert train_res.status_code == 201
        body = train_res.json()
        assert body["package"]["packageVersion"] == "wv-shadow-test-1.0.0"
        assert body["package"]["manifest"]["entrypoint"] == "model/model.json"
        assert body["datasetRows"] >= 8
        assert any(metric["name"] == "mae_kg" for metric in body["validationMetrics"])

        package_id = body["package"]["id"]
        download_res = client.get(
            f"/api/v1/ml/weighvision/model-packages/{package_id}/download",
            headers=auth_headers(),
        )
        assert download_res.status_code == 200
        assert len(download_res.content) > 0


def test_row_serializers_accept_json_string_fields():
    now = datetime.now(tz=timezone.utc)
    model = model_response_from_row(
        {
            "id": "model-1",
            "tenant_id": "tenant-batch4",
            "name": "shadow-model",
            "type": "regression",
            "description": "test",
            "algorithm": "linear-regression",
            "hyperparameters": json.dumps([{"name": "ridge_lambda", "value": 1e-6, "type": "number"}]),
            "features": json.dumps(["selected_area_mm2", "selected_depth_mm"]),
            "target_variable": "final_weight_kg",
            "status": "trained",
            "metrics": json.dumps([{"name": "mae_kg", "value": 0.1, "unit": "kg"}]),
            "metadata": json.dumps(
                {"author": "tester", "description": "desc", "tags": ["shadow"], "version": "1.0.0"}
            ),
            "training_data_start": now,
            "training_data_end": now,
            "trained_at": now,
            "created_at": now,
            "updated_at": now,
        }
    )
    package = package_response_from_row(
        {
            "id": "pkg-1",
            "tenant_id": "tenant-batch4",
            "model_id": "model-1",
            "package_version": "wv-shadow-test-1.0.0",
            "runtime_family": "python-linear-regression",
            "runtime_version": "1.0.0",
            "feature_schema_version": "wv-feature-schema-v1",
            "checksum_sha256": "abc123",
            "package_uri": "http://example.test/model.tar.gz",
            "channel": "stable",
            "approval_state": "published",
            "manifest": json.dumps(
                {
                    "packageVersion": "wv-shadow-test-1.0.0",
                    "modelFamily": "weighvision-weight-predictor",
                    "runtimeFamily": "python-linear-regression",
                    "runtimeVersion": "1.0.0",
                    "featureSchemaVersion": "wv-feature-schema-v1",
                    "checksumSha256": "abc123",
                    "packageUri": "http://example.test/model.tar.gz",
                    "entrypoint": "model/model.json",
                    "channel": "stable",
                    "activationPolicy": {"activation_mode": "shadow"},
                    "fallbackPolicy": {"order": ["last_known_good"]},
                    "metadata": {"shadow_mode_only": True},
                }
            ),
            "created_at": now,
            "updated_at": now,
        }
    )

    assert model.hyperparameters[0].name == "ridge_lambda"
    assert model.features == ["selected_area_mm2", "selected_depth_mm"]
    assert model.metrics[0].name == "mae_kg"
    assert package.manifest.entrypoint == "model/model.json"
