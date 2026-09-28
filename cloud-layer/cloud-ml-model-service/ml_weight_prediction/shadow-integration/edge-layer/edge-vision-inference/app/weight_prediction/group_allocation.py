from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import FEATURE_COLUMNS


def allocate_group_weight(model: Any, group_total_weight_g: float, detections: list[dict[str, Any]], model_version: str) -> list[dict[str, Any]]:
    """Allocate a stable scale total across quality-passing detections.

    This output is deliberately labelled WEAK_ALLOCATION: it conserves a known
    group total but is not an independently validated individual weight.
    """
    if not np.isfinite(group_total_weight_g) or group_total_weight_g <= 0:
        return [{"detection_index": row.get("detection_index"), "prediction_status": "REJECTED_QUALITY", "allocated_weight_g": None, "reason": "invalid_group_total_weight_g", "model_version": model_version} for row in detections]
    frame = pd.DataFrame(detections)
    missing = [name for name in FEATURE_COLUMNS if name not in frame]
    if missing:
        return [{"detection_index": row.get("detection_index"), "prediction_status": "REJECTED_QUALITY", "allocated_weight_g": None, "reason": f"missing_features:{','.join(missing)}", "model_version": model_version} for row in detections]
    raw = np.maximum(model.predict(frame[FEATURE_COLUMNS]), 0.001)
    allocation = group_total_weight_g * raw / raw.sum()
    return [{"detection_index": row.get("detection_index"), "prediction_status": "WEAK_ALLOCATION", "allocated_weight_g": float(weight), "raw_score_g": float(score), "reason": None, "model_version": model_version} for row, score, weight in zip(detections, raw, allocation)]
