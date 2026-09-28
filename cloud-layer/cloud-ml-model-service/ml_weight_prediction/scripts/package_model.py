from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction import FEATURE_COLUMNS  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard, REFERENCE_WORKBOOK_FILENAME  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser(description="Create an immutable edge model package from a candidate artifact.")
    p.add_argument("--artifact-dir", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--version", default=None)
    p.add_argument("--performance-standard", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "sample_data" / REFERENCE_WORKBOOK_FILENAME)
    args = p.parse_args()
    model, metrics = args.artifact_dir / "model.joblib", args.artifact_dir / "metrics.json"
    if not model.exists() or not metrics.exists():
        raise SystemExit("candidate artifact must contain model.joblib and metrics.json")
    if not args.performance_standard.is_file():
        raise SystemExit(f"performance standard not found: {args.performance_standard}")
    performance_standard = PerformanceStandard(args.performance_standard)
    metrics_payload = json.loads(metrics.read_text(encoding="utf-8"))
    if metrics_payload.get("feature_columns") != FEATURE_COLUMNS:
        raise SystemExit("candidate feature schema does not include the current growth-standard features; rebuild the dataset and retrain before packaging")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("output package directory already exists and is non-empty; use a new versioned directory")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(model, args.output_dir / model.name)
    shutil.copy2(metrics, args.output_dir / metrics.name)
    shutil.copy2(args.performance_standard, args.output_dir / REFERENCE_WORKBOOK_FILENAME)
    weak_allocation = metrics_payload.get("model_type") == "WEAKLY_SUPERVISED_GROUP_ALLOCATION"
    manifest = {"package_schema_version": 2, "model_version": args.version or f"candidate-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}", "created_at": datetime.now(timezone.utc).isoformat(), "target_unit": "g", "feature_columns": FEATURE_COLUMNS, "target_transform": metrics_payload.get("target_transform", "none"), "prediction_mode": "weak_group_allocation" if weak_allocation else "individual_regression", "individual_accuracy_validated": not weak_allocation, "performance_standard": {"source": args.performance_standard.name, "filename": REFERENCE_WORKBOOK_FILENAME, **performance_standard.coverage()}, "quality_contract": {"min_confidence": 0.80, "requires_stable_group_total": weak_allocation, "requires_individual_label_for_training": not weak_allocation, "requires_breed_sex_and_age_days": True}, "files": {"model.joblib": sha256(args.output_dir / "model.joblib"), "metrics.json": sha256(args.output_dir / "metrics.json"), REFERENCE_WORKBOOK_FILENAME: sha256(args.output_dir / REFERENCE_WORKBOOK_FILENAME)}}
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"edge package created: {args.output_dir}")


if __name__ == "__main__":
    main()
