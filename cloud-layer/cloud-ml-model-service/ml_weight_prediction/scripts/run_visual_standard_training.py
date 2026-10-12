"""Build and train the visual-only standard-proxy experiment from .env."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ML_ROOT / ".vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

import pandas as pd

sys.path.insert(0, str(ML_ROOT / "src"))
from weight_prediction import VISUAL_FEATURE_COLUMNS  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard  # noqa: E402
from weight_prediction.weak_supervision import build_weak_dataset  # noqa: E402


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid .env line in {path}: {line!r}")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else ML_ROOT / path


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true/false, 1/0, yes/no, or on/off")


def main() -> None:
    load_dotenv(ML_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Train visual-only weight prediction with approved-standard proxy labels.")
    parser.add_argument("--captures", type=Path, default=env_path("VISUAL_TRAIN_CAPTURES"))
    parser.add_argument("--output-dir", type=Path, default=env_path("VISUAL_TRAIN_OUTPUT_DIR"))
    parser.add_argument("--performance-standard", type=Path, default=env_path("VISUAL_TRAIN_PERFORMANCE_STANDARD"))
    parser.add_argument("--breed", default=os.getenv("VISUAL_TRAIN_BREED"))
    parser.add_argument("--sex", choices=("male", "female", "as_hatched"), default=os.getenv("VISUAL_TRAIN_SEX"))
    parser.add_argument("--age-start-date", default=os.getenv("VISUAL_TRAIN_AGE_START_DATE"))
    parser.add_argument("--age-days-at-start", type=int, default=os.getenv("VISUAL_TRAIN_AGE_DAYS_AT_START"))
    parser.add_argument("--use-weight-error-quality-gate", action=argparse.BooleanOptionalAction, default=env_bool("WEIGHT_ERROR_QUALITY_GATE_ENABLED", True), help="Reject captures whose raw metadata contains scale.weight_error.")
    parser.add_argument("--use-nonpositive-height-quality-gate", action=argparse.BooleanOptionalAction, default=env_bool("NONPOSITIVE_HEIGHT_QUALITY_GATE_ENABLED", True), help="Reject detections whose inferred height_mm is zero or negative.")
    args = parser.parse_args()
    missing = [name for name, value in {
        "captures": args.captures, "output_dir": args.output_dir, "performance_standard": args.performance_standard,
        "breed": args.breed, "sex": args.sex, "age_start_date": args.age_start_date,
        "age_days_at_start": args.age_days_at_start,
    }.items() if value is None]
    if missing:
        parser.error(f"Missing arguments and .env values: {', '.join(missing)}")
    context = {"breed": args.breed, "sex": args.sex, "age_start_date": args.age_start_date, "age_days_at_start": args.age_days_at_start}
    dataset = build_weak_dataset(
        args.captures,
        PerformanceStandard(args.performance_standard),
        context,
        reject_weight_error=args.use_weight_error_quality_gate,
        reject_nonpositive_height=args.use_nonpositive_height_quality_gate,
    )
    before = len(dataset)
    excluded_by_weight_error_gate = pd.DataFrame(columns=dataset.columns)
    if args.use_weight_error_quality_gate:
        excluded_by_weight_error_gate = dataset[dataset.weight_error.notna()].copy()
        dataset = dataset[dataset.weight_error.isna()].copy()
    excluded_by_nonpositive_height_gate = pd.DataFrame(columns=dataset.columns)
    if args.use_nonpositive_height_quality_gate:
        excluded_by_nonpositive_height_gate = dataset[dataset.height_mm.le(0)].copy()
        dataset = dataset[dataset.height_mm.gt(0)].copy()
    dataset = dataset.dropna(subset=VISUAL_FEATURE_COLUMNS + ["standard_weight_g"]).copy()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = args.output_dir / "visual_standard_training_features.csv"
    dataset.to_csv(dataset_path, index=False)
    excluded_by_weight_error_gate.assign(exclusion_reason="scale_weight_error_present").to_csv(
        args.output_dir / "excluded_by_weight_error_gate.csv", index=False
    )
    excluded_by_nonpositive_height_gate.assign(exclusion_reason="height_mm_nonpositive").to_csv(
        args.output_dir / "excluded_by_nonpositive_height_gate.csv", index=False
    )
    summary = {
        "source_detections": before,
        "usable_visual_detections": len(dataset),
        "excluded_by_weight_error_gate": len(excluded_by_weight_error_gate),
        "excluded_by_nonpositive_height_gate": len(excluded_by_nonpositive_height_gate),
        "capture_dates": sorted(pd.to_datetime(dataset.captured_at, utc=True, format="mixed").dt.date.astype(str).unique().tolist()),
        "visual_features_only": VISUAL_FEATURE_COLUMNS,
        "target_source": str(args.performance_standard),
        "estimator_receives_date_or_age": False,
        "weight_error_quality_gate": {"enabled": args.use_weight_error_quality_gate},
        "nonpositive_height_quality_gate": {"enabled": args.use_nonpositive_height_quality_gate},
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(VENDOR_DIR) + os.pathsep + child_env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, str(Path(__file__).with_name("train_visual_standard_xgboost.py")), "--dataset", str(dataset_path), "--output-dir", str(args.output_dir / "candidate")], check=True, env=child_env)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
