from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from . import FEATURE_COLUMNS
from .performance_standard import PerformanceStandard, PerformanceStandardError


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _polygon_area(points: Any) -> float | None:
    if not isinstance(points, list) or len(points) < 3:
        return None
    try:
        vertices = [(float(point[0]), float(point[1])) for point in points]
    except (IndexError, TypeError, ValueError):
        return None
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(vertices, vertices[1:] + vertices[:1]))) / 2


def _inside_roi(points: Any, roi: Any) -> bool | None:
    if not isinstance(points, list) or not isinstance(roi, list) or len(roi) != 4:
        return None
    try:
        x1, y1, x2, y2 = map(float, roi)
        return all(x1 <= float(p[0]) <= x2 and y1 <= float(p[1]) <= y2 for p in points)
    except (IndexError, TypeError, ValueError):
        return None


def _context_value(document: dict[str, Any], detection: dict[str, Any], field: str, defaults: dict[str, Any]) -> Any:
    """Use capture context first, then an explicit dataset-level test override."""
    for source in (detection, document, defaults):
        value = source.get(field)
        if value is not None and value != "":
            return value
    return None


def _derive_row(
    document: dict[str, Any],
    detection: dict[str, Any],
    session: dict[str, Any],
    performance_standard: PerformanceStandard,
    context_defaults: dict[str, Any],
) -> dict[str, Any]:
    bbox = detection.get("bbox_xyxy") or [None] * 4
    try:
        x1, y1, x2, y2 = map(float, bbox)
        bbox_width, bbox_height = x2 - x1, y2 - y1
    except (TypeError, ValueError):
        bbox_width = bbox_height = None
    bbox_area = bbox_width * bbox_height if bbox_width and bbox_height and bbox_width > 0 and bbox_height > 0 else None
    roi = (document.get("roi") or {}).get("xyxy")
    contained = _inside_roi(detection.get("mask_xy"), roi)
    scale = document.get("scale") or {}
    group_weight_kg = _num(scale.get("weight_kg") or document.get("group_weight_kg"))
    row: dict[str, Any] = {
        "session_id": session["session_id"], "captured_at": session["captured_at"],
        "detection_index": detection.get("detection_index"), "record_id": detection.get("record_id"),
        "group_total_weight_g": group_weight_kg * 1000 if group_weight_kg is not None else None,
        "weight_stable": scale.get("weight_stable") is True,
        "weight_label_type": "group_total", "camera_id": _context_value(document, detection, "camera_id", context_defaults),
        "batch_id": _context_value(document, detection, "batch_id", context_defaults),
        "age_days": _context_value(document, detection, "age_days", context_defaults),
        "breed": _context_value(document, detection, "breed", context_defaults),
        "sex": _context_value(document, detection, "sex", context_defaults),
        "area_mm2": _num(detection.get("area_xy_mm2")), "length_mm": _num(detection.get("length_mm")),
        "width_mm": _num(detection.get("width_mm")), "height_mm": _num(detection.get("height_mm")),
        "depth_mm": _num(detection.get("depth_mm")), "confidence": _num(detection.get("confidence")),
        "bbox_area_px": bbox_area,
        "bbox_aspect_ratio": bbox_width / bbox_height if bbox_width and bbox_height else None,
        "mask_fill_ratio": _polygon_area(detection.get("mask_xy")) / bbox_area if _polygon_area(detection.get("mask_xy")) and bbox_area else None,
        "is_mask_clipped": contained is False,
        "centroid_x_norm": None, "centroid_y_norm": None,
    }
    for field in ("area_mm2", "length_mm", "width_mm", "height_mm", "depth_mm", "confidence"):
        if row[field] is None or row[field] <= 0:
            row.setdefault("quality_reasons", []).append(f"invalid_{field}")
    if row["confidence"] is not None and row["confidence"] < 0.80:
        row.setdefault("quality_reasons", []).append("confidence_below_0_80")
    if row["is_mask_clipped"]:
        row.setdefault("quality_reasons", []).append("mask_clipped_by_roi")
    if contained is None:
        row.setdefault("quality_reasons", []).append("roi_containment_unknown")
    for field in ("bbox_area_px", "bbox_aspect_ratio", "mask_fill_ratio"):
        if _num(row[field]) is None:
            row.setdefault("quality_reasons", []).append(f"missing_{field}")
    row["volume_proxy_area_height_mm3"] = row["area_mm2"] * row["height_mm"] if row["area_mm2"] and row["height_mm"] else None
    row["volume_proxy_lwh_mm3"] = row["length_mm"] * row["width_mm"] * row["height_mm"] if row["length_mm"] and row["width_mm"] and row["height_mm"] else None
    row["length_width_ratio"] = row["length_mm"] / row["width_mm"] if row["length_mm"] and row["width_mm"] else None
    row["is_height_outlier"] = 0
    try:
        row = performance_standard.add_features(row)
    except PerformanceStandardError as error:
        row.setdefault("quality_reasons", []).append(str(error))
    row["quality_reasons"] = ";".join(row.get("quality_reasons", []))
    row["quality_pass"] = not row["quality_reasons"] and row["weight_stable"] and row["group_total_weight_g"] is not None and row["group_total_weight_g"] > 0
    if not row["weight_stable"]:
        row["quality_reasons"] = ";".join(filter(None, [row["quality_reasons"], "scale_not_stable"]))
        row["quality_pass"] = False
    return row


def build_weak_dataset(
    capture_csv: Path,
    performance_standard: PerformanceStandard,
    context_defaults: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Build weak-label rows, optionally enriching legacy capture metadata.

    Defaults are deliberately caller-supplied rather than inferred from a growth
    standard: a reference curve cannot determine a flock's sex or age.
    """
    context_defaults = context_defaults or {}
    rows: list[dict[str, Any]] = []
    with capture_csv.open(encoding="utf-8-sig", newline="") as handle:
        for source in csv.DictReader(handle):
            document = json.loads(source["raw_metadata"])
            session = {"session_id": source["session_id"], "captured_at": source["occurred_at"]}
            session_rows = [
                _derive_row(document, detection, session, performance_standard, context_defaults)
                for detection in document.get("detections", [])
            ]
            eligible = [row for row in session_rows if row["quality_pass"]]
            # The scale total includes every bird in the ROI. If any detection is
            # rejected, its mass is unknown and must not be silently divided among
            # the remaining birds. Reject that whole session for weak-label train.
            session_pass = bool(session_rows) and len(eligible) == len(session_rows)
            session_reason = "" if session_pass else "not_all_roi_detections_quality_passing"
            count = len(session_rows) if session_pass else 0
            for row in session_rows:
                row["session_quality_pass"] = session_pass
                row["session_quality_reason"] = session_reason
                row["eligible_chicken_count"] = count
                row["pseudo_weight_g"] = row["group_total_weight_g"] / count if session_pass else None
                row["session_sample_weight"] = 1 / count if session_pass else None
                row["quality_pass"] = bool(row["quality_pass"] and session_pass)
                if not session_pass:
                    row["quality_reasons"] = ";".join(filter(None, [row["quality_reasons"], session_reason]))
            rows.extend(session_rows)
    frame = pd.DataFrame(rows)
    for feature in FEATURE_COLUMNS:
        if feature not in frame:
            frame[feature] = float("nan")
    return frame
