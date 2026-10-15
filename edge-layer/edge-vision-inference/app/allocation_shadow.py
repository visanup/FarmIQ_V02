"""Optional, observation-only XGBoost branch. Never writes the scalar result."""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path


class AllocationShadow:
    def __init__(self):
        self.enabled = os.getenv("ALLOCATION_SHADOW_ENABLED", "false").lower() == "true"
        self.model = None
        self.manifest = {}
        self.load_error = None
        if not self.enabled:
            return
        try:
            import joblib
            from app.weight_prediction import FEATURE_COLUMNS
            from app.weight_prediction.performance_standard import PerformanceStandard
            package = Path(os.environ["ALLOCATION_SHADOW_PACKAGE_DIR"]).resolve()
            manifest_path = package / "manifest.json"
            # Trust anchor comes from deployment configuration, not from the package itself.
            self.checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            if self.checksum != os.environ.get("ALLOCATION_SHADOW_MANIFEST_SHA256"):
                raise ValueError("manifest_checksum_mismatch")
            self.manifest = json.loads(manifest_path.read_text())
            if self.manifest.get("prediction_mode") != "weak_group_allocation":
                raise ValueError("wrong_prediction_mode")
            if self.manifest.get("individual_accuracy_validated") is not False:
                raise ValueError("weak_model_must_be_unvalidated")
            if self.manifest.get("feature_columns") != FEATURE_COLUMNS:
                raise ValueError("feature_schema_mismatch")
            reference = self.manifest["performance_standard"]["filename"]
            for name in ("model.joblib", "metrics.json", reference):
                target = (package / name).resolve()
                if not target.is_relative_to(package):
                    raise ValueError("unsafe_package_path")
                if hashlib.sha256(target.read_bytes()).hexdigest() != self.manifest["files"][name]:
                    raise ValueError("file_checksum_mismatch:" + name)
            self.standard = PerformanceStandard(package / reference)
            # Load only after the trusted manifest and all files were verified.
            self.model = joblib.load(package / "model.joblib")
        except Exception as exc:
            self.load_error = str(exc)

    def predict(self, event):
        from app.weight_prediction import FEATURE_COLUMNS
        from app.weight_prediction.weak_supervision import _derive_row
        import numpy as np
        import pandas as pd
        start = time.monotonic()
        result = {
            "schema_version": "1.0", "event_type": "weighvision.group_allocation.completed",
            "session_id": event.get("session_id"), "capture_id": event.get("capture_id"),
            "model_version": self.manifest.get("model_version", "unavailable"),
            "prediction_mode": "weak_group_allocation", "shadow_only": True,
            "individual_accuracy_validated": False, "decision_use_allowed": False,
            "manifest_sha256": getattr(self, "checksum", None),
            "allocations": [], "quality_reasons": [],
        }
        try:
            if self.model is None:
                result["prediction_status"] = "REJECTED_MODEL_UNAVAILABLE"
                raise ValueError(self.load_error or "model_not_loaded")
            document = event.get("raw_metadata") or {}
            if not event.get("session_id") or not event.get("capture_id"):
                raise ValueError("missing_capture_identity")
            if document.get("image_id") != event["capture_id"] or document.get("session_id") != event["session_id"]:
                raise ValueError("capture_identity_mismatch")
            scale = document.get("scale") or {}
            if scale.get("weight_stable") is not True:
                raise ValueError("scale_not_stable")
            if not scale.get("scale_id") or not scale.get("calibration_version") or scale.get("tare_verified") is not True:
                raise ValueError("missing_scale_calibration_or_tare")
            total = float(scale["weight_kg"]) * 1000
            if not math.isfinite(total) or total <= 0:
                raise ValueError("invalid_scale_total")
            result["group_total_weight_g"] = total
            detections = document.get("detections") or []
            if not detections or len(detections) != document.get("roi_count"):
                raise ValueError("incomplete_roi_detections")
            ids = [d.get("detection_index") for d in detections]
            if any(type(i) is not int or i < 0 for i in ids) or len(set(ids)) != len(ids):
                raise ValueError("invalid_or_duplicate_detection_index")
            width, height = float(document["image_width_px"]), float(document["image_height_px"])
            if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                raise ValueError("invalid_image_dimensions")
            rows = []
            for detection in detections:
                points = detection.get("mask_xy") or []
                if not points or not all(0 <= x <= width and 0 <= y <= height for x, y in points):
                    raise ValueError("mask_outside_image")
                row = _derive_row(document, detection, {"session_id": event["session_id"], "captured_at": event.get("captured_at")}, self.standard, {})
                if not row["quality_pass"]:
                    raise ValueError(f"detection_{detection['detection_index']}:{row['quality_reasons']}")
                rows.append(row)
            # Preserve the trained feature definition, including missing centroids.
            frame = pd.DataFrame(rows)[FEATURE_COLUMNS].astype(float)
            raw = np.maximum(self.model.predict(frame), 0.001)
            if not np.isfinite(raw).all():
                raise ValueError("non_finite_model_output")
            allocated = total * raw.astype(float) / float(raw.astype(float).sum())
            result.update(prediction_status="WEAK_ALLOCATION", raw_sum_g=float(raw.sum()),
                          reconciliation_error_g=float(allocated.sum() - total),
                          allocations=[{"detection_index": i, "allocated_weight_g": float(w), "raw_score_g": float(s),
                                        "prediction_status": "WEAK_ALLOCATION"} for i, w, s in zip(ids, allocated, raw)])
        except Exception as exc:
            result.setdefault("prediction_status", "REJECTED_QUALITY")
            result["quality_reasons"] = [str(exc)]
            result["allocations"] = []
        result["latency_ms"] = (time.monotonic() - start) * 1000
        return result
