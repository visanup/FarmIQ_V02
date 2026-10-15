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
        self.features: list[str] = self.manifest["feature_columns"]
        self.min_confidence = self.manifest["quality_contract"]["min_confidence"]
        reference_file = self.manifest.get("performance_standard", {}).get("filename")
        if not reference_file:
            raise ValueError("package is missing the performance standard reference")
        self.performance_standard = PerformanceStandard(package / reference_file)

    def predict(self, event: dict[str, Any]) -> dict[str, Any]:
        try:
            enriched_event = self.performance_standard.add_features(event)
        except PerformanceStandardError as error:
            return self._rejected(event, str(error), "REJECTED_GROWTH_STANDARD")
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
        return {"record_id": event.get("record_id"), "model_version": self.manifest["model_version"], "prediction_status": "ACCEPTED", "predicted_weight_g": prediction, "standard_weight_g": values["standard_weight_g"], "growth_performance_pct": prediction / values["standard_weight_g"] * 100, "reason": None}

    def _rejected(self, event: dict[str, Any], reason: str, status: str = "REJECTED_QUALITY") -> dict[str, Any]:
        return {"record_id": event.get("record_id"), "model_version": self.manifest["model_version"], "prediction_status": status, "predicted_weight_g": None, "reason": reason}
