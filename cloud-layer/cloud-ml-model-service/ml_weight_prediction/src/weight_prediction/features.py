from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from . import FEATURE_COLUMNS
from .performance_standard import PerformanceStandard, PerformanceStandardError


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _polygon_area(points: Any) -> float | None:
    if not isinstance(points, list) or len(points) < 3:
        return None
    try:
        pairs = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        return None
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pairs, pairs[1:] + pairs[:1]))) / 2


def _reason(row: dict[str, Any], height_bounds: tuple[float, float] | None, performance_error: str | None) -> list[str]:
    reasons: list[str] = []
    if row.get("weight_label_type") != "individual":
        reasons.append("label_not_individual")
    if row.get("weight_stable") is not True:
        reasons.append("scale_not_marked_stable")
    if _number(row.get("actual_weight_g")) is None or _number(row.get("actual_weight_g")) <= 0:
        reasons.append("missing_or_invalid_actual_weight_g")
    if _number(row.get("confidence")) is None or float(row["confidence"]) < 0.80:
        reasons.append("confidence_below_0_80")
    for field in ("area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm"):
        if _number(row.get(field)) is None or float(row[field]) <= 0:
            reasons.append(f"invalid_{field}")
    if row.get("image_width") is None or row.get("image_height") is None:
        reasons.append("missing_image_dimensions")
    for field in ("bbox_area_px", "bbox_aspect_ratio", "mask_fill_ratio", "centroid_x_norm", "centroid_y_norm"):
        if _number(row.get(field)) is None:
            reasons.append(f"missing_{field}")
    if height_bounds is None:
        reasons.append("height_qc_bounds_not_configured")
    elif row["is_height_outlier"]:
        reasons.append("height_outside_configured_bounds")
    if performance_error:
        reasons.append(performance_error)
    return reasons


def build_rows(metadata_path: Path, labels: pd.DataFrame, height_bounds: tuple[float, float] | None, performance_standard: PerformanceStandard) -> list[dict[str, Any]]:
    document = json.loads(metadata_path.read_text(encoding="utf-8"))
    label_by_id = labels.set_index("record_id").to_dict("index") if not labels.empty else {}
    detections = {d.get("detection_index"): d for d in document.get("detections", [])}
    image_width = document.get("image_width") or document.get("frame_width")
    image_height = document.get("image_height") or document.get("frame_height")
    rows: list[dict[str, Any]] = []
    for record in document.get("per_chicken_records", []):
        detection = detections.get(record.get("detection_index"), {})
        label = label_by_id.get(record.get("record_id"), {})
        bbox = detection.get("bbox_xyxy") or record.get("bbox_xyxy") or [None] * 4
        try:
            x1, y1, x2, y2 = map(float, bbox)
            bbox_width, bbox_height = x2 - x1, y2 - y1
        except (TypeError, ValueError):
            bbox_width = bbox_height = None
        bbox_area = bbox_width * bbox_height if bbox_width and bbox_height and bbox_width > 0 and bbox_height > 0 else None
        mask_area = _polygon_area(detection.get("mask_xy"))
        pixel = detection.get("pixel_xy", [None, None])
        row: dict[str, Any] = {
            "record_id": record.get("record_id"), "session_id": record.get("session_id") or document.get("image_id"),
            "captured_at": document.get("timestamp"), "detection_index": record.get("detection_index"),
            "actual_weight_g": label.get("actual_weight_g"), "weight_stable": label.get("weight_stable"),
            "weight_label_type": label.get("weight_label_type", record.get("weight_label_type")),
            "camera_id": label.get("camera_id", document.get("camera_id")), "batch_id": label.get("batch_id"), "age_days": label.get("age_days", document.get("age_days")),
            "breed": label.get("breed", document.get("breed")), "sex": label.get("sex", document.get("sex")),
            "area_mm2": record.get("area_mm2", detection.get("area_xy_mm2")),
            "length_mm": record.get("object_length_mm", detection.get("length_mm")),
            "width_mm": record.get("object_width_mm", detection.get("width_mm")),
            "height_mm": detection.get("height_mm"), "depth_mm": record.get("average_depth_mm", detection.get("depth_mm")),
            "confidence": record.get("confidence_score", detection.get("confidence")),
            "bbox_width_px": bbox_width, "bbox_height_px": bbox_height, "bbox_area_px": bbox_area,
            "bbox_aspect_ratio": bbox_width / bbox_height if bbox_width and bbox_height else None,
            "mask_fill_ratio": mask_area / bbox_area if mask_area and bbox_area else None,
            "image_width": image_width, "image_height": image_height,
            "centroid_x_norm": _number(pixel[0]) / float(image_width) if image_width and _number(pixel[0]) is not None else None,
            "centroid_y_norm": _number(pixel[1]) / float(image_height) if image_height and _number(pixel[1]) is not None else None,
        }
        for key in ("area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm", "confidence"):
            row[key] = _number(row[key])
        row["volume_proxy_area_height_mm3"] = row["area_mm2"] * row["height_mm"] if row["area_mm2"] and row["height_mm"] else None
        row["volume_proxy_lwh_mm3"] = row["length_mm"] * row["width_mm"] * row["height_mm"] if row["length_mm"] and row["width_mm"] and row["height_mm"] else None
        row["length_width_ratio"] = row["length_mm"] / row["width_mm"] if row["length_mm"] and row["width_mm"] else None
        row["is_height_outlier"] = int(height_bounds is not None and (row["height_mm"] is None or not height_bounds[0] <= row["height_mm"] <= height_bounds[1]))
        performance_error = None
        try:
            row = performance_standard.add_features(row)
        except PerformanceStandardError as error:
            performance_error = str(error)
        row["quality_reasons"] = ";".join(_reason(row, height_bounds, performance_error))
        row["quality_pass"] = not row["quality_reasons"]
        rows.append(row)
    return rows


def required_feature_columns() -> list[str]:
    return FEATURE_COLUMNS.copy()
