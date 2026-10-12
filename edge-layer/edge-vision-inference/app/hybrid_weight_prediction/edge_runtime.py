from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .performance_standard import PerformanceStandard, PerformanceStandardError


class EdgeWeightPredictor:
    """Validated, decision-free inference wrapper for the immutable edge package."""

    def __init__(self, package_dir: str | Path):
        package = Path(package_dir)
        self.manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        self.model = joblib.load(package / "model.joblib")
        self.prediction_mode = self.manifest.get("prediction_mode", "individual_regression")
        self.features: list[str] = self.manifest["feature_columns"]
        self.min_confidence = self.manifest["quality_contract"]["min_confidence"]
        reference_file = self.manifest.get("performance_standard", {}).get("filename")
        if not reference_file:
            raise ValueError("package is missing the performance standard reference")
        self.performance_standard = PerformanceStandard(package / reference_file)

    def predict(self, event: dict[str, Any]) -> dict[str, Any]:
        visual_only_model = self.prediction_mode in {"individual_visual_standard_proxy", "individual_visual_scale_regression"}
        if visual_only_model:
            # This experiment intentionally receives only per-image geometry.
            # The approved standard was used only to construct training targets.
            enriched_event = event
        else:
            try:
                enriched_event = self.performance_standard.add_features(event)
            except PerformanceStandardError as error:
                return self._rejected(event, str(error), "REJECTED_GROWTH_STANDARD")
        if self.prediction_mode == "individual_standard_baseline":
            standard_weight_g = float(enriched_event["standard_weight_g"])
            return {
                "record_id": event.get("record_id"),
                "model_version": self.manifest["model_version"],
                "prediction_status": "STANDARD_BASELINE",
                "predicted_weight_g": standard_weight_g,
                "standard_weight_g": standard_weight_g,
                "growth_performance_pct": 100.0,
                "reason": "approved_growth_standard_by_breed_sex_and_age; individual_accuracy_not_validated",
            }
        values: dict[str, float] = {}
        for name in self.features:
            try:
                value = float(enriched_event[name])
            except (KeyError, TypeError, ValueError):
                return self._rejected(event, f"missing_or_non_numeric_{name}")
            if not math.isfinite(value):
                return self._rejected(event, f"non_finite_{name}")
            values[name] = value
        if values["confidence"] < self.min_confidence:
            return self._rejected(event, "confidence_below_minimum")
        raw_prediction = float(self.model.predict(pd.DataFrame([values], columns=self.features))[0])
        prediction = raw_prediction + values["standard_weight_g"] if self.manifest.get("target_transform") == "standard_weight_residual" else raw_prediction
        if self.prediction_mode == "individual_hybrid_standard_visual":
            standard_weight_g = float(enriched_event["standard_weight_g"])
            standard_weight = float(self.manifest["hybrid"]["standard_weight"])
            visual_weight = float(self.manifest["hybrid"]["visual_weight"])
            hybrid_prediction = standard_weight * standard_weight_g + visual_weight * prediction
            return {
                "record_id": event.get("record_id"),
                "model_version": self.manifest["model_version"],
                "prediction_status": "ACCEPTED",
                "predicted_weight_g": hybrid_prediction,
                "standard_weight_g": standard_weight_g,
                "visual_standard_proxy_g": prediction,
                "growth_performance_pct": hybrid_prediction / standard_weight_g * 100,
                "reason": "hybrid_trial; 75pct_approved_growth_standard_plus_25pct_visual_standard_proxy",
            }
        if visual_only_model:
            reason = "visual_geometry_only; capture_date_and_age_not_used_at_inference"
            if self.prediction_mode == "individual_visual_scale_regression":
                reason = "visual_geometry_only; trained_from_quality_gated_individual_scale_labels; capture_date_and_age_not_used_at_inference"
            return {"record_id": event.get("record_id"), "model_version": self.manifest["model_version"], "prediction_status": "ACCEPTED", "predicted_weight_g": prediction, "standard_weight_g": None, "growth_performance_pct": None, "reason": reason}
        return {"record_id": event.get("record_id"), "model_version": self.manifest["model_version"], "prediction_status": "ACCEPTED", "predicted_weight_g": prediction, "standard_weight_g": values["standard_weight_g"], "growth_performance_pct": prediction / values["standard_weight_g"] * 100, "reason": None}

    def _rejected(self, event: dict[str, Any], reason: str, status: str = "REJECTED_QUALITY") -> dict[str, Any]:
        return {"record_id": event.get("record_id"), "model_version": self.manifest["model_version"], "prediction_status": status, "predicted_weight_g": None, "reason": reason}
