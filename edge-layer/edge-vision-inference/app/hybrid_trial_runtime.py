"""Opt-in adapter for the local Hybrid Trial Model 75Sx25V."""

from __future__ import annotations

from typing import Any, Dict

from app.hybrid_weight_prediction.edge_runtime import EdgeWeightPredictor


class HybridTrialRuntime:
    """Adapts normalized Edge detection metadata to the immutable hybrid package."""

    def __init__(self, package_dir: str):
        self.predictor = EdgeWeightPredictor(package_dir)

    def predict(self, metadata: Dict[str, Any]) -> Dict[str, Any] | None:
        features = self._numeric_features(metadata)
        context = metadata.get("batch_context") if isinstance(metadata.get("batch_context"), dict) else {}
        event: Dict[str, Any] = {
            "record_id": metadata.get("record_id") or metadata.get("capture_id") or metadata.get("session_id"),
            "breed": metadata.get("breed") or context.get("breed") or context.get("breed_code"),
            "sex": metadata.get("sex") or context.get("sex"),
            "age_days": metadata.get("age_days") or context.get("age_days"),
            **features,
        }
        required = set(self.predictor.features) | {"breed", "sex", "age_days"}
        if any(event.get(name) is None for name in required):
            return None
        return self.predictor.predict(event)

    @staticmethod
    def _numeric_features(metadata: Dict[str, Any]) -> Dict[str, Any]:
        raw = metadata.get("features") or metadata.get("normalized_features") or metadata.get("normalizedFeatures") or {}
        if not isinstance(raw, dict):
            return {}
        aliases = {
            "selected_area_mm2": "area_mm2",
            "selected_length_mm": "length_mm",
            "selected_width_mm": "width_mm",
            "selected_height_mm": "height_mm",
            "selected_depth_mm": "depth_mm",
            "selected_confidence": "confidence",
        }
        values: Dict[str, Any] = {aliases.get(key, key): value for key, value in raw.items()}
        try:
            values.setdefault("volume_proxy_area_height_mm3", float(values["area_mm2"]) * float(values["height_mm"]))
            values.setdefault("volume_proxy_lwh_mm3", float(values["length_mm"]) * float(values["width_mm"]) * float(values["height_mm"]))
            values.setdefault("length_width_ratio", float(values["length_mm"]) / float(values["width_mm"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
        for name in (
            "area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm",
            "bbox_area_px", "bbox_aspect_ratio", "mask_fill_ratio",
        ):
            try:
                if float(values[name]) <= 0:
                    return {}
            except (KeyError, TypeError, ValueError):
                return {}
        if int(values.get("is_height_outlier", 1)) != 0:
            return {}
        return values
