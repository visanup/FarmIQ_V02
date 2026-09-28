from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction.group_allocation import allocate_group_weight  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard, PerformanceStandardError  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Allocate a stable group-scale total across quality-passing detections.")
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--event", required=True, type=Path, help="JSON with group_total_weight_g and detections")
    args = parser.parse_args()
    manifest = json.loads((args.package_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("prediction_mode") != "weak_group_allocation":
        raise SystemExit("package is not a weak group-allocation model")
    event = json.loads(args.event.read_text(encoding="utf-8"))
    if event.get("weight_stable") is not True:
        raise SystemExit("REJECTED_QUALITY: scale weight is not stable")
    reference_file = manifest.get("performance_standard", {}).get("filename")
    if not reference_file:
        raise SystemExit("REJECTED_GROWTH_STANDARD: package is missing the performance standard reference")
    standard = PerformanceStandard(args.package_dir / reference_file)
    detections = []
    for detection in event.get("detections") or []:
        merged = {**event, **detection}
        try:
            detections.append(standard.add_features(merged))
        except PerformanceStandardError as error:
            detections.append({**detection, "growth_standard_error": str(error)})
    invalid = [row for row in detections if "growth_standard_error" in row]
    if invalid:
        allocation = [{"detection_index": row.get("detection_index"), "prediction_status": "REJECTED_GROWTH_STANDARD", "allocated_weight_g": None, "reason": row["growth_standard_error"], "model_version": manifest["model_version"]} for row in invalid]
    else:
        allocation = allocate_group_weight(joblib.load(args.package_dir / "model.joblib"), float(event.get("group_total_weight_g", 0)), detections, manifest["model_version"])
    print(json.dumps({"session_id": event.get("session_id"), "group_total_weight_g": event.get("group_total_weight_g"), "prediction_mode": manifest["prediction_mode"], "allocations": allocation}, allow_nan=False))


if __name__ == "__main__":
    main()
