"""Inference service for running ML models."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import Config

logger = logging.getLogger(__name__)


class InferenceService:
    """Service for running inference on images."""

    def __init__(self, config: Config):
        self.config = config
        self.model_version = config.MODEL_VERSION
        self.confidence_threshold = config.CONFIDENCE_THRESHOLD
        self.cache_dir = Path(config.MODEL_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.active_manifest: Optional[Dict[str, Any]] = self._load_manifest(config.MODEL_MANIFEST_PATH)
        self.fallback_manifest: Optional[Dict[str, Any]] = self._load_manifest(config.FALLBACK_MODEL_MANIFEST_PATH)
        self.active_model_payload: Optional[Dict[str, Any]] = None
        self.activation_source = "env"
        self.fallback_engaged = False

        self._load_runtime_from_current_manifests()

    def _load_manifest(self, path_str: str) -> Optional[Dict[str, Any]]:
        if not path_str:
            return None
        manifest_path = Path(path_str)
        if not manifest_path.exists():
            logger.warning("Model manifest path does not exist: %s", manifest_path)
            return None
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["_manifest_path"] = str(manifest_path)
            return payload
        except Exception as exc:
            logger.warning("Failed to load model manifest %s: %s", manifest_path, exc)
            return None

    def _load_runtime_from_current_manifests(self) -> None:
        if self.active_manifest:
            self._set_active_runtime(self.active_manifest, activation_source="manifest", fallback_engaged=False)
            return
        if self.fallback_manifest:
            self._set_active_runtime(
                self.fallback_manifest,
                activation_source="fallback_manifest",
                fallback_engaged=True,
            )

    def _set_active_runtime(
        self,
        manifest: Dict[str, Any],
        *,
        activation_source: str,
        fallback_engaged: bool,
    ) -> None:
        manifest_meta = manifest.get("metadata") or {}
        self.active_manifest = manifest
        self.model_version = str(
            manifest_meta.get("model_version")
            or manifest.get("packageVersion")
            or self.config.MODEL_VERSION
        )
        self.active_model_payload = self._load_model_payload(manifest)
        self.activation_source = activation_source
        self.fallback_engaged = fallback_engaged

    def _load_model_payload(self, manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        manifest_path_raw = manifest.get("_manifest_path")
        extracted_root_raw = manifest.get("_extracted_root")
        entrypoint = manifest.get("entrypoint")
        if not entrypoint:
            return None
        if extracted_root_raw:
            model_path = Path(str(extracted_root_raw)) / str(entrypoint)
        elif manifest_path_raw:
            model_path = Path(str(manifest_path_raw)).parent / str(entrypoint)
        else:
            return None
        if not model_path.exists():
            logger.warning("Model entrypoint does not exist: %s", model_path)
            return None
        try:
            payload = json.loads(model_path.read_text(encoding="utf-8"))
            payload["_model_path"] = str(model_path)
            return payload
        except Exception as exc:
            logger.warning("Failed to load model payload %s: %s", model_path, exc)
            return None

    async def ensure_subscription_activation(self) -> None:
        if (
            not self.config.MODEL_SYNC_ENABLED
            or not self.config.POLICY_SYNC_URL
            or not self.config.EDGE_TENANT_ID
            or not self.config.EDGE_SITE_ID
        ):
            return

        resolved = await self._fetch_effective_subscription()
        if not resolved:
            return

        active_package = resolved.get("activePackage") or {}
        fallback_package = resolved.get("fallbackPackage") or {}
        active_package_id = str(active_package.get("id") or "")
        current_package_id = str((self.active_manifest or {}).get("id") or "")
        if active_package_id and active_package_id == current_package_id and self.active_model_payload:
            if fallback_package:
                await self._cache_package_manifest(fallback_package, fallback_only=True)
            return

        try:
            await self._activate_package(active_package, activation_source="manifest")
            await self._ack_subscription(active_package_id, "downloaded", "ok", "package downloaded and verified")
            await self._ack_subscription(active_package_id, "validated", "ok", "package manifest and checksum validated")
            await self._ack_subscription(active_package_id, "activated", "ok", "package activated for shadow inference")
            if fallback_package:
                await self._cache_package_manifest(fallback_package, fallback_only=True)
        except Exception as exc:
            detail = f"activation failed for package {active_package_id}: {exc}"
            logger.warning(detail)
            await self._ack_subscription(active_package_id, "failed", "failed", detail)
            if fallback_package:
                fallback_id = str(fallback_package.get("id") or "")
                try:
                    await self._activate_package(
                        fallback_package,
                        activation_source="fallback_manifest",
                        fallback_engaged=True,
                        fallback_only=True,
                    )
                    await self._ack_subscription(
                        fallback_id,
                        "rollback",
                        "ok",
                        f"fallback package {fallback_id} activated after primary failure",
                    )
                except Exception as fallback_exc:
                    logger.warning(
                        "fallback activation failed for package %s: %s",
                        fallback_id,
                        fallback_exc,
                    )

    async def _fetch_effective_subscription(self) -> Optional[Dict[str, Any]]:
        base_url = self.config.POLICY_SYNC_URL.rstrip("/")
        query = urllib.parse.urlencode(
            {
                "tenantId": self.config.EDGE_TENANT_ID,
                "siteId": self.config.EDGE_SITE_ID,
            }
        )
        url = f"{base_url}/model-subscription/effective?{query}"

        def _load() -> Optional[Dict[str, Any]]:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=self.config.MODEL_CONTROL_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload.get("data", {}).get("resolved_json") or payload.get("resolved_json")

        try:
            return await asyncio.to_thread(_load)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.info("No effective model subscription cached yet for tenant=%s site=%s", self.config.EDGE_TENANT_ID, self.config.EDGE_SITE_ID)
                return None
            raise

    async def _activate_package(
        self,
        package_payload: Dict[str, Any],
        *,
        activation_source: str,
        fallback_engaged: bool = False,
        fallback_only: bool = False,
    ) -> None:
        package_id = str(package_payload.get("id") or "")
        manifest_payload = dict(package_payload.get("manifest") or {})
        package_uri = str(package_payload.get("packageUri") or manifest_payload.get("packageUri") or "")
        expected_checksum = str(package_payload.get("checksumSha256") or manifest_payload.get("checksumSha256") or "")
        package_version = str(package_payload.get("packageVersion") or manifest_payload.get("packageVersion") or "")
        if not package_id or not package_uri or not package_version:
            raise ValueError("Incomplete package payload for activation")

        package_bytes = await asyncio.to_thread(self._download_package_bytes, package_uri)
        actual_checksum = hashlib.sha256(package_bytes).hexdigest()
        if expected_checksum and expected_checksum != actual_checksum:
            raise ValueError(f"Checksum mismatch for package {package_id}")

        package_root = self.cache_dir / package_id
        if package_root.exists():
            shutil.rmtree(package_root)
        package_root.mkdir(parents=True, exist_ok=True)
        extracted_root = await asyncio.to_thread(self._extract_package, package_root, package_bytes)

        package_manifest_path = extracted_root / "manifest.json"
        package_manifest = (
            json.loads(package_manifest_path.read_text(encoding="utf-8"))
            if package_manifest_path.exists()
            else {}
        )
        runtime_manifest = {
            **package_manifest,
            **manifest_payload,
            "id": package_id,
            "packageVersion": package_version or package_manifest.get("packageVersion"),
            "checksumSha256": expected_checksum or actual_checksum,
            "packageUri": package_uri,
            "_extracted_root": str(extracted_root),
            "entrypoint": manifest_payload.get("entrypoint") or package_manifest.get("entrypoint"),
        }

        manifest_target_path = self._resolve_manifest_target_path(fallback_only)
        manifest_target_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_target_path.write_text(json.dumps(runtime_manifest, indent=2), encoding="utf-8")
        runtime_manifest["_manifest_path"] = str(manifest_target_path)

        if fallback_only:
            self.fallback_manifest = runtime_manifest
            if fallback_engaged:
                self._set_active_runtime(
                    runtime_manifest,
                    activation_source=activation_source,
                    fallback_engaged=True,
                )
        else:
            self._set_active_runtime(
                runtime_manifest,
                activation_source=activation_source,
                fallback_engaged=fallback_engaged,
            )

    async def _cache_package_manifest(
        self,
        package_payload: Dict[str, Any],
        *,
        fallback_only: bool,
    ) -> None:
        try:
            await self._activate_package(
                package_payload,
                activation_source="fallback_manifest" if fallback_only else "manifest",
                fallback_engaged=False,
                fallback_only=fallback_only,
            )
        except Exception as exc:
            logger.warning("Failed to cache fallback package manifest: %s", exc)

    def _resolve_manifest_target_path(self, fallback_only: bool) -> Path:
        configured = (
            self.config.FALLBACK_MODEL_MANIFEST_PATH
            if fallback_only
            else self.config.MODEL_MANIFEST_PATH
        )
        if configured:
            return Path(configured)
        return self.cache_dir / ("fallback-manifest.json" if fallback_only else "active-manifest.json")

    def _download_package_bytes(self, package_uri: str) -> bytes:
        if package_uri.startswith("file://"):
            parsed = urllib.parse.urlparse(package_uri)
            local_path = urllib.request.url2pathname(parsed.path)
            return Path(local_path).read_bytes()

        package_path = Path(package_uri)
        if package_path.exists():
            return package_path.read_bytes()

        headers = {}
        if self.config.MODEL_CONTROL_TOKEN:
            headers["Authorization"] = f"Bearer {self.config.MODEL_CONTROL_TOKEN}"
        request = urllib.request.Request(package_uri, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=self.config.MODEL_CONTROL_TIMEOUT_SECONDS) as response:
            return response.read()

    def _extract_package(self, package_root: Path, package_bytes: bytes) -> Path:
        with tarfile.open(fileobj=io.BytesIO(package_bytes), mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                target = (package_root / member.name).resolve()
                if not str(target).startswith(str(package_root.resolve())):
                    raise ValueError("Unsafe tar archive member detected")
            for member in members:
                target = package_root / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                file_obj = archive.extractfile(member)
                if file_obj is None:
                    continue
                with file_obj, target.open("wb") as output:
                    shutil.copyfileobj(file_obj, output)

        child_dirs = [child for child in package_root.iterdir() if child.is_dir()]
        if len(child_dirs) == 1:
            return child_dirs[0]
        return package_root

    async def _ack_subscription(
        self,
        package_id: str,
        ack_type: str,
        status: str,
        detail: str,
    ) -> None:
        if (
            not package_id
            or not self.config.MODEL_CONTROL_BFF_URL
            or not self.config.MODEL_CONTROL_TOKEN
            or not self.config.EDGE_SITE_ID
            or not self.config.EDGE_TENANT_ID
        ):
            return

        url = (
            f"{self.config.MODEL_CONTROL_BFF_URL.rstrip('/')}"
            f"/api/v1/weighvision/model-subscriptions/sites/{urllib.parse.quote(self.config.EDGE_SITE_ID)}/ack"
        )
        body = json.dumps(
            {
                "tenantId": self.config.EDGE_TENANT_ID,
                "packageId": package_id,
                "ackType": ack_type,
                "status": status,
                "detail": detail,
                "payload": {
                    "activationSource": self.activation_source,
                    "fallbackEngaged": self.fallback_engaged,
                },
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.MODEL_CONTROL_TOKEN}",
        }

        def _post() -> None:
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=self.config.MODEL_CONTROL_TIMEOUT_SECONDS):
                return None

        try:
            await asyncio.to_thread(_post)
        except Exception as exc:
            logger.warning("Failed to acknowledge model subscription: %s", exc)

    async def run_inference(
        self,
        image_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run inference on an image.
        """
        await self.ensure_subscription_activation()

        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        features = self._extract_features(metadata or {})
        if self.active_model_payload and features:
            try:
                return self._run_shadow_model_inference(image_file, features, metadata or {})
            except Exception as exc:
                logger.warning("Shadow model inference failed, falling back to stub mode: %s", exc)

        return self._run_stub_inference(image_file, metadata or {})

    def _run_shadow_model_inference(
        self,
        image_file: Path,
        features: Dict[str, float],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        model_payload = self.active_model_payload or {}
        feature_order = list(model_payload.get("feature_order") or [])
        feature_means = list(model_payload.get("feature_means") or [])
        feature_stds = list(model_payload.get("feature_stds") or [])
        coefficients = list(model_payload.get("coefficients") or [])
        intercept = float(model_payload.get("intercept") or 0.0)
        if not feature_order or len(feature_order) != len(coefficients):
            raise ValueError("Active model payload is incomplete")

        scaled_values = []
        for index, feature_name in enumerate(feature_order):
            if feature_name not in features:
                raise ValueError(f"Missing feature {feature_name}")
            std = float(feature_stds[index] or 1.0)
            scaled_values.append((float(features[feature_name]) - float(feature_means[index])) / std)

        predicted_weight = intercept + sum(
            float(coefficients[index]) * scaled_values[index]
            for index in range(len(coefficients))
        )
        predicted_weight = max(0.0, round(predicted_weight, 4))
        confidence = round(min(0.99, 0.7 + (1.0 / max(1, len(feature_order)))), 4)

        runtime_metadata = self._runtime_metadata(image_file, metadata)
        runtime_metadata.update(
            {
                "stub_mode": False,
                "prediction_mode": "shadow",
                "features_used": {name: features[name] for name in feature_order},
            }
        )

        logger.info("Running inference (shadow baseline) model_version=%s", self.model_version)
        return {
            "predicted_weight_kg": predicted_weight,
            "confidence": confidence,
            "model_version": self.model_version,
            "metadata": runtime_metadata,
        }

    def _run_stub_inference(self, image_file: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        file_size = image_file.stat().st_size
        predicted_weight = float(file_size % 1000) / 100.0
        confidence = min(0.95, 0.5 + (file_size % 100) / 200.0)

        logger.info("Running inference (stub mode) model_version=%s", self.model_version)
        return {
            "predicted_weight_kg": round(predicted_weight, 2),
            "confidence": round(confidence, 4),
            "model_version": self.model_version,
            "metadata": {
                **self._runtime_metadata(image_file, metadata),
                "stub_mode": True,
                "prediction_mode": "shadow_stub",
            },
        }

    def _runtime_metadata(self, image_file: Path, metadata: Dict[str, Any]) -> Dict[str, Any]:
        active_manifest = self.active_manifest or {}
        return {
            "image_path": str(image_file),
            "file_size_bytes": image_file.stat().st_size,
            "package_id": active_manifest.get("id"),
            "package_version": active_manifest.get("packageVersion"),
            "feature_schema_version": active_manifest.get("featureSchemaVersion"),
            "activation_source": self.activation_source,
            "fallback_engaged": self.fallback_engaged,
            **metadata,
        }

    def _extract_features(self, metadata: Dict[str, Any]) -> Dict[str, float]:
        raw_features = (
            metadata.get("features")
            or metadata.get("normalized_features")
            or metadata.get("normalizedFeatures")
            or {}
        )
        if not isinstance(raw_features, dict):
            return {}
        features: Dict[str, float] = {}
        for key, value in raw_features.items():
            if isinstance(value, (int, float)):
                features[str(key)] = float(value)
            elif isinstance(value, str) and value.strip():
                try:
                    features[str(key)] = float(value)
                except ValueError:
                    continue
        return features

    def get_model_info(self) -> Dict[str, Any]:
        active_manifest = self.active_manifest or {}
        fallback_manifest = self.fallback_manifest or {}
        return {
            "model_version": self.model_version,
            "model_path": self.config.MODEL_PATH or "shadow_baseline_or_stub",
            "confidence_threshold": self.config.CONFIDENCE_THRESHOLD,
            "nms_threshold": self.config.NMS_THRESHOLD,
            "status": "ready" if self.active_model_payload else "stub_mode",
            "activation_source": self.activation_source,
            "fallback_engaged": self.fallback_engaged,
            "package_id": active_manifest.get("id"),
            "package_version": active_manifest.get("packageVersion"),
            "feature_schema_version": active_manifest.get("featureSchemaVersion"),
            "manifest_path": active_manifest.get("_manifest_path"),
            "activation_policy": active_manifest.get("activationPolicy"),
            "fallback_policy": active_manifest.get("fallbackPolicy"),
            "fallback_package_id": fallback_manifest.get("id"),
            "fallback_manifest_path": fallback_manifest.get("_manifest_path"),
            "active_model_path": (self.active_model_payload or {}).get("_model_path"),
        }
