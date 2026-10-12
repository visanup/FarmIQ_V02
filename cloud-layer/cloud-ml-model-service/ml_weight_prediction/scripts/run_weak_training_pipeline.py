"""Build, audit, and optionally train a weak-allocation candidate from farm exports."""

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
from weight_prediction.performance_standard import PerformanceStandard, REFERENCE_WORKBOOK_FILENAME  # noqa: E402
from weight_prediction.weak_supervision import build_weak_dataset  # noqa: E402


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
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


def env_bool(name: str, default: bool = False) -> bool:
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
    parser = argparse.ArgumentParser(description="Prepare and optionally train a leakage-safe weak allocation model.")
    parser.add_argument("--captures", type=Path, default=env_path("WEAK_TRAIN_CAPTURES"), help="Original or sampled session_capture_metadata CSV.")
    parser.add_argument("--output-dir", type=Path, default=env_path("WEAK_TRAIN_OUTPUT_DIR"))
    parser.add_argument("--performance-standard", type=Path, default=env_path("WEAK_TRAIN_PERFORMANCE_STANDARD") or ML_ROOT / "docs" / "sample_data" / REFERENCE_WORKBOOK_FILENAME)
    parser.add_argument("--breed", default=os.getenv("WEAK_TRAIN_BREED"))
    parser.add_argument("--sex", choices=("male", "female", "as_hatched"), default=os.getenv("WEAK_TRAIN_SEX"))
    parser.add_argument("--age-start-date", default=os.getenv("WEAK_TRAIN_AGE_START_DATE"), help="YYYY-MM-DD capture date used as the flock age baseline.")
    parser.add_argument("--age-days-at-start", type=int, default=os.getenv("WEAK_TRAIN_AGE_DAYS_AT_START"))
    parser.add_argument("--min-eligible-sessions", type=int, default=os.getenv("WEAK_TRAIN_MIN_ELIGIBLE_SESSIONS", "100"), help="Minimum quality-passing sessions required before --train is allowed.")
    parser.add_argument("--use-weight-error-quality-gate", action=argparse.BooleanOptionalAction, default=env_bool("WEIGHT_ERROR_QUALITY_GATE_ENABLED", True), help="Reject captures whose raw metadata contains scale.weight_error.")
    parser.add_argument("--use-nonpositive-height-quality-gate", action=argparse.BooleanOptionalAction, default=env_bool("NONPOSITIVE_HEIGHT_QUALITY_GATE_ENABLED", True), help="Reject detections whose inferred height_mm is zero or negative.")
    parser.add_argument("--train", action="store_true", default=env_bool("WEAK_TRAIN_RUN_TRAIN"), help="Train a candidate after the audit succeeds.")
    parser.add_argument("--prepare-only", action="store_false", dest="train", help="Create the audit and dataset but never train a candidate.")
    args = parser.parse_args()
    missing = [name for name, value in {"captures": args.captures, "output_dir": args.output_dir, "breed": args.breed, "sex": args.sex, "age_start_date": args.age_start_date, "age_days_at_start": args.age_days_at_start}.items() if value is None]
    if missing:
        parser.error(f"Missing arguments and .env values: {', '.join(missing)}")

    context_defaults = {
        "breed": args.breed,
        "sex": args.sex,
        "age_start_date": args.age_start_date,
        "age_days_at_start": args.age_days_at_start,
    }
    dataset = build_weak_dataset(
        args.captures,
        PerformanceStandard(args.performance_standard),
        context_defaults,
        reject_weight_error=args.use_weight_error_quality_gate,
        reject_nonpositive_height=args.use_nonpositive_height_quality_gate,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "weak_data_audit.csv"
    dataset_path = args.output_dir / "weak_group_features.csv"
    dataset.to_csv(audit_path, index=False)
    eligible = dataset[dataset.quality_pass].copy()
    eligible.to_csv(dataset_path, index=False)
    summary = {
        "captures_file": str(args.captures),
        "audited_detections": int(len(dataset)),
        "eligible_detections": int(len(eligible)),
        "eligible_sessions": int(eligible.session_id.nunique()) if not eligible.empty else 0,
        "eligible_collection_days": int(pd.to_datetime(eligible.captured_at, utc=True).dt.date.nunique()) if not eligible.empty else 0,
        "context": context_defaults,
        "weight_error_quality_gate": {"enabled": args.use_weight_error_quality_gate},
        "nonpositive_height_quality_gate": {"enabled": args.use_nonpositive_height_quality_gate, "excluded_detections": int((dataset.height_mm.le(0)).sum()) if args.use_nonpositive_height_quality_gate else 0},
        "trained": False,
    }
    if eligible.empty:
        (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        raise SystemExit("No quality-passing group-scale detections. Read weak_data_audit.csv; no model was trained.")
    if args.train:
        if summary["eligible_sessions"] < args.min_eligible_sessions:
            (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            raise SystemExit(
                f"Only {summary['eligible_sessions']} eligible sessions; need at least {args.min_eligible_sessions} before training. "
                "Export more quality-passing source sessions or use an explicitly approved lower threshold."
            )
        candidate_dir = args.output_dir / "candidate"
        command = [sys.executable, str(Path(__file__).with_name("train_weak_xgboost.py")), "--dataset", str(dataset_path), "--output-dir", str(candidate_dir)]
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = str(VENDOR_DIR) + os.pathsep + child_env.get("PYTHONPATH", "")
        subprocess.run(command, check=True, env=child_env)
        summary["trained"] = True
        summary["candidate_dir"] = str(candidate_dir)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
