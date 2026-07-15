from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from statistics import quantiles
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def bbox_area_px2(detection: dict[str, Any]) -> float:
    bbox = as_list(detection.get("bbox_xyxy"))
    if len(bbox) != 4:
        return -1.0
    x1 = to_float(bbox[0]) or 0.0
    y1 = to_float(bbox[1]) or 0.0
    x2 = to_float(bbox[2]) or 0.0
    y2 = to_float(bbox[3]) or 0.0
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def pick_selected_detection_index(detections: list[dict[str, Any]]) -> int | None:
    if not detections:
        return None

    selected_index = 0
    selected_area = float("-inf")
    for index, detection in enumerate(detections):
        area = (
            to_float(detection.get("area_xy_mm2"))
            or to_float(detection.get("mask_area_px2"))
            or bbox_area_px2(detection)
        )
        if area > selected_area:
            selected_area = area
            selected_index = index
    return selected_index


def parse_metadata_file(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    detections = [as_dict(item) for item in as_list(raw.get("detections"))]
    selected_index = pick_selected_detection_index(detections)
    selected = detections[selected_index] if selected_index is not None else {}
    scale = as_dict(raw.get("scale"))
    focus = as_dict(raw.get("focus"))
    height_estimation = as_dict(raw.get("height_estimation"))

    row = {
        "metadata_file": path.name,
        "session_id": str(raw.get("session_id") or raw.get("image_id") or path.stem),
        "capture_id": str(raw.get("image_id") or path.stem),
        "timestamp": raw.get("timestamp"),
        "weight_kg": to_float(scale.get("weight_kg")),
        "weight_source": scale.get("weight_source"),
        "focus_laplacian_var": to_float(focus.get("laplacian_var")),
        "focus_min_laplacian": to_float(focus.get("min_laplacian")),
        "roi_count": to_float(raw.get("roi_count")),
        "detection_count": len(detections),
        "selected_detection_index": selected_index,
        "selected_confidence": to_float(selected.get("confidence")),
        "selected_depth_mm": to_float(selected.get("depth_mm")),
        "selected_height_mm": to_float(selected.get("height_mm")),
        "selected_width_mm": to_float(selected.get("width_mm")),
        "selected_length_mm": to_float(selected.get("length_mm")),
        "selected_area_mm2": to_float(selected.get("area_xy_mm2")),
        "floor_depth_mm": to_float(height_estimation.get("floor_depth_mm")),
        "has_top_level_final_weight": (
            raw.get("final_weight_kg") is not None
            or raw.get("finalWeightKg") is not None
            or raw.get("weight_kg") is not None
            or raw.get("weightKg") is not None
        ),
    }
    return row


def iqr_bounds(values: list[float]) -> tuple[float, float]:
    quartiles = quantiles(sorted(values), n=4, method="inclusive")
    q1 = quartiles[0]
    q3 = quartiles[2]
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def classify_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected_depths = [
        row["selected_depth_mm"]
        for row in rows
        if isinstance(row["selected_depth_mm"], float)
    ]
    depth_low, depth_high = iqr_bounds(selected_depths) if selected_depths else (0.0, 0.0)

    category_counter: Counter[str] = Counter()
    weight_source_counter: Counter[str] = Counter()

    for row in rows:
        flags: list[str] = []
        weight_source = str(row.get("weight_source"))
        weight_kg = row.get("weight_kg")
        selected_confidence = row.get("selected_confidence")
        selected_depth_mm = row.get("selected_depth_mm")
        selected_height_mm = row.get("selected_height_mm")

        weight_source_counter[weight_source] += 1

        if weight_kg is None:
            flags.append("sensor_missing_weight")
        if weight_source == "unstable":
            flags.append("sensor_unstable_weight")
        if isinstance(weight_kg, float) and weight_kg >= 20.0:
            flags.append("sensor_unit_mismatch_candidate")
        if weight_source == "post_capture_window":
            flags.append("timing_post_capture_window")
        if row["detection_count"] > 1:
            flags.append("segmentation_multi_detection")
        if isinstance(selected_confidence, float) and selected_confidence < 0.35:
            flags.append("segmentation_low_confidence")
        if (
            isinstance(selected_depth_mm, float)
            and (selected_depth_mm < depth_low or selected_depth_mm > depth_high)
        ):
            flags.append("depth_outlier")
        if isinstance(selected_height_mm, float) and selected_height_mm < 0:
            flags.append("depth_negative_height")
        if isinstance(selected_height_mm, float) and selected_height_mm > 300:
            flags.append("depth_implausible_height")
        if weight_kg is not None and not row["has_top_level_final_weight"]:
            flags.append("finalize_path_payload_gap")

        if "sensor_unit_mismatch_candidate" in flags:
            dominant = "sensor_unit_mismatch"
        elif "sensor_unstable_weight" in flags or "sensor_missing_weight" in flags:
            dominant = "sensor_or_timing_gap"
        elif "finalize_path_payload_gap" in flags:
            dominant = "finalize_path_fallback_risk"
        elif "depth_outlier" in flags or "depth_negative_height" in flags:
            dominant = "depth_geometry_outlier"
        elif "segmentation_multi_detection" in flags or "segmentation_low_confidence" in flags:
            dominant = "segmentation_selection_risk"
        else:
            dominant = "nominal"

        row["root_cause_flags"] = ";".join(flags)
        row["dominant_root_cause"] = dominant
        category_counter[dominant] += 1

    return {
        "depth_iqr_low_mm": round(depth_low, 2),
        "depth_iqr_high_mm": round(depth_high, 2),
        "weight_source_distribution": dict(weight_source_counter),
        "dominant_root_cause_distribution": dict(category_counter),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict[str, Any]], derived: dict[str, Any]) -> dict[str, Any]:
    flagged_rows = [row for row in rows if row["dominant_root_cause"] != "nominal"]
    return {
        "dataset_scope": {
            "total_metadata_files": len(rows),
            "flagged_rows": len(flagged_rows),
            "metadata_dir": "iot-layer/weight-vision-capture/data/metadata",
        },
        "observed_counts": {
            "weight_present": sum(1 for row in rows if row["weight_kg"] is not None),
            "weight_missing": sum(1 for row in rows if row["weight_kg"] is None),
            "post_capture_window_rows": sum(
                1 for row in rows if row["weight_source"] == "post_capture_window"
            ),
            "unit_mismatch_candidates_ge_20kg": sum(
                1
                for row in rows
                if isinstance(row["weight_kg"], float) and row["weight_kg"] >= 20.0
            ),
            "multi_detection_rows": sum(1 for row in rows if row["detection_count"] > 1),
            "low_confidence_rows": sum(
                1
                for row in rows
                if isinstance(row["selected_confidence"], float)
                and row["selected_confidence"] < 0.35
            ),
            "depth_outlier_rows": sum(
                1 for row in rows if "depth_outlier" in row["root_cause_flags"]
            ),
            "negative_height_rows": sum(
                1
                for row in rows
                if isinstance(row["selected_height_mm"], float) and row["selected_height_mm"] < 0
            ),
            "finalize_path_payload_gap_rows": sum(
                1 for row in rows if "finalize_path_payload_gap" in row["root_cause_flags"]
            ),
        },
        "derived": derived,
        "representative_examples": {
            "sensor_unit_mismatch": [
                {
                    "metadata_file": row["metadata_file"],
                    "weight_kg": row["weight_kg"],
                }
                for row in rows
                if row["dominant_root_cause"] == "sensor_unit_mismatch"
            ][:5],
            "sensor_or_timing_gap": [
                {
                    "metadata_file": row["metadata_file"],
                    "weight_source": row["weight_source"],
                    "weight_kg": row["weight_kg"],
                }
                for row in rows
                if row["dominant_root_cause"] == "sensor_or_timing_gap"
            ][:5],
            "depth_geometry_outlier": [
                {
                    "metadata_file": row["metadata_file"],
                    "selected_depth_mm": row["selected_depth_mm"],
                    "selected_height_mm": row["selected_height_mm"],
                }
                for row in rows
                if row["dominant_root_cause"] == "depth_geometry_outlier"
            ][:5],
            "segmentation_selection_risk": [
                {
                    "metadata_file": row["metadata_file"],
                    "detection_count": row["detection_count"],
                    "selected_confidence": row["selected_confidence"],
                }
                for row in rows
                if row["dominant_root_cause"] == "segmentation_selection_risk"
            ][:5],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build Batch 2 WeighVision field audit dataset from capture metadata."
    )
    parser.add_argument(
        "--metadata-dir",
        default="iot-layer/weight-vision-capture/data/metadata",
        help="Directory containing capture metadata JSON files",
    )
    parser.add_argument(
        "--output-csv",
        default="docs/iot-layer/evidence/batch2-weight-audit-dataset.csv",
        help="CSV output path",
    )
    parser.add_argument(
        "--output-summary",
        default="docs/iot-layer/evidence/batch2-weight-audit-summary.json",
        help="Summary JSON output path",
    )
    args = parser.parse_args()

    metadata_dir = Path(args.metadata_dir)
    files = sorted(metadata_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no metadata JSON files found under {metadata_dir}")

    rows = [parse_metadata_file(path) for path in files]
    derived = classify_rows(rows)
    summary = build_summary(rows, derived)

    write_csv(Path(args.output_csv), rows)
    output_summary = Path(args.output_summary)
    output_summary.parent.mkdir(parents=True, exist_ok=True)
    output_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
