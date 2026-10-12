"""Prepare and train an individual visual model from manually reviewed single-bird images."""

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
    parser = argparse.ArgumentParser(description="Prepare and train a quality-gated individual visual weight candidate.")
    parser.add_argument("--images-dir", type=Path, default=env_path("SINGLE_BIRD_TRAIN_IMAGES_DIR"))
    parser.add_argument("--manifest", type=Path, default=env_path("SINGLE_BIRD_TRAIN_MANIFEST"))
    parser.add_argument("--captures", type=Path, default=env_path("SINGLE_BIRD_TRAIN_CAPTURES"))
    parser.add_argument("--output-dir", type=Path, default=env_path("SINGLE_BIRD_TRAIN_OUTPUT_DIR"))
    parser.add_argument("--performance-standard", type=Path, default=env_path("SINGLE_BIRD_TRAIN_PERFORMANCE_STANDARD"))
    parser.add_argument("--breed", default=os.getenv("SINGLE_BIRD_TRAIN_BREED"))
    parser.add_argument("--sex", choices=("male", "female", "as_hatched"), default=os.getenv("SINGLE_BIRD_TRAIN_SEX"))
    parser.add_argument("--age-start-date", default=os.getenv("SINGLE_BIRD_TRAIN_AGE_START_DATE"))
    parser.add_argument("--age-days-at-start", type=int, default=os.getenv("SINGLE_BIRD_TRAIN_AGE_DAYS_AT_START"))
    parser.add_argument("--use-standard-plausibility-gate", action=argparse.BooleanOptionalAction, default=env_bool("SINGLE_BIRD_QUALITY_GATE_ENABLED", True))
    parser.add_argument("--max-standard-relative-diff-pct", type=float, default=float(os.getenv("SINGLE_BIRD_QUALITY_GATE_MAX_STANDARD_RELATIVE_DIFF_PCT", "50")))
    parser.add_argument("--use-weight-error-quality-gate", action=argparse.BooleanOptionalAction, default=env_bool("WEIGHT_ERROR_QUALITY_GATE_ENABLED", True), help="Reject captures whose raw metadata contains scale.weight_error.")
    parser.add_argument("--use-nonpositive-height-quality-gate", action=argparse.BooleanOptionalAction, default=env_bool("NONPOSITIVE_HEIGHT_QUALITY_GATE_ENABLED", True), help="Reject captures whose inferred height_mm is zero or negative.")
    args = parser.parse_args()
    required = {"images_dir": args.images_dir, "manifest": args.manifest, "captures": args.captures, "output_dir": args.output_dir, "performance_standard": args.performance_standard, "breed": args.breed, "sex": args.sex, "age_start_date": args.age_start_date, "age_days_at_start": args.age_days_at_start}
    missing = [name for name, value in required.items() if value is None]
    if missing:
        parser.error(f"Missing arguments and .env values: {', '.join(missing)}")
    if args.use_standard_plausibility_gate and args.max_standard_relative_diff_pct < 0:
        parser.error("--max-standard-relative-diff-pct must be zero or greater when the gate is enabled")

    image_stems = {path.stem for path in args.images_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    manifest = pd.read_csv(args.manifest)
    manifest["image_stem"] = manifest.object_key.map(lambda value: Path(value).stem)
    selected = manifest[manifest.image_stem.isin(image_stems)].copy()
    selected_duplicates = selected[selected.session_id.duplicated(keep=False)].copy()
    selected = selected.drop_duplicates(subset="session_id", keep=False).copy()
    context = {"breed": args.breed, "sex": args.sex, "age_start_date": args.age_start_date, "age_days_at_start": args.age_days_at_start}
    features = build_weak_dataset(
        args.captures,
        PerformanceStandard(args.performance_standard),
        context,
        reject_weight_error=args.use_weight_error_quality_gate,
        reject_nonpositive_height=args.use_nonpositive_height_quality_gate,
    )
    excluded_by_weight_error_gate = pd.DataFrame(columns=selected.columns)
    if args.use_weight_error_quality_gate:
        rejected_session_ids = set(features.loc[features.weight_error.notna(), "session_id"])
        excluded_by_weight_error_gate = selected[selected.session_id.isin(rejected_session_ids)].copy()
        selected = selected[~selected.session_id.isin(rejected_session_ids)].copy()
    excluded_by_nonpositive_height_gate = pd.DataFrame(columns=selected.columns)
    if args.use_nonpositive_height_quality_gate:
        rejected_session_ids = set(features.loc[features.height_mm.le(0), "session_id"])
        excluded_by_nonpositive_height_gate = selected[selected.session_id.isin(rejected_session_ids)].copy()
        selected = selected[~selected.session_id.isin(rejected_session_ids)].copy()
    features = features.drop_duplicates(subset="session_id", keep=False)
    columns = ["session_id", *VISUAL_FEATURE_COLUMNS, "standard_weight_g"]
    dataset = selected.merge(features[columns], on="session_id", how="left", validate="one_to_one")
    missing_features = dataset[dataset[VISUAL_FEATURE_COLUMNS].isna().any(axis=1)].copy()
    dataset = dataset.dropna(subset=VISUAL_FEATURE_COLUMNS + ["standard_weight_g"]).copy()
    dataset["record_id"] = dataset.media_id
    dataset["standard_relative_diff_pct"] = (dataset.displayed_weight_g - dataset.standard_weight_g).abs() / dataset.standard_weight_g * 100
    rejected = pd.DataFrame(columns=dataset.columns)
    if args.use_standard_plausibility_gate:
        rejected = dataset[dataset.standard_relative_diff_pct > args.max_standard_relative_diff_pct].copy()
        dataset = dataset[dataset.standard_relative_diff_pct <= args.max_standard_relative_diff_pct].copy()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.output_dir / "training_features.csv", index=False)
    rejected.assign(exclusion_reason="scale_weight_differs_from_standard_over_threshold").to_csv(args.output_dir / "excluded_by_standard_gate.csv", index=False)
    excluded_by_weight_error_gate.assign(exclusion_reason="scale_weight_error_present").to_csv(args.output_dir / "excluded_by_weight_error_gate.csv", index=False)
    excluded_by_nonpositive_height_gate.assign(exclusion_reason="height_mm_nonpositive").to_csv(args.output_dir / "excluded_by_nonpositive_height_gate.csv", index=False)
    missing_features.assign(exclusion_reason="missing_visual_features").to_csv(args.output_dir / "excluded_missing_features.csv", index=False)
    selected_duplicates.assign(exclusion_reason="multiple_selected_images_per_session").to_csv(args.output_dir / "excluded_duplicate_sessions.csv", index=False)
    summary = {
        "images_found": len(image_stems), "matched_manifest_rows": len(selected), "usable_training_rows": len(dataset),
        "excluded_by_standard_gate": len(rejected), "excluded_missing_features": len(missing_features), "excluded_duplicate_sessions": len(selected_duplicates),
        "excluded_by_weight_error_gate": len(excluded_by_weight_error_gate),
        "excluded_by_nonpositive_height_gate": len(excluded_by_nonpositive_height_gate),
        "standard_plausibility_gate": {"enabled": args.use_standard_plausibility_gate, "max_standard_relative_diff_pct": args.max_standard_relative_diff_pct},
        "weight_error_quality_gate": {"enabled": args.use_weight_error_quality_gate},
        "nonpositive_height_quality_gate": {"enabled": args.use_nonpositive_height_quality_gate},
        "target": "displayed_weight_g", "target_note": "Scale resolution is 100 g; labels are displayed scale values, not sub-step ground truth.",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if len(dataset) < 15:
        raise SystemExit(f"Only {len(dataset)} quality-passing rows; need at least 15 independent sessions before training.")
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(VENDOR_DIR) + os.pathsep + child_env.get("PYTHONPATH", "")
    subprocess.run([sys.executable, str(Path(__file__).with_name("train_single_bird_visual_xgboost.py")), "--dataset", str(args.output_dir / "training_features.csv"), "--output-dir", str(args.output_dir / "candidate")], check=True, env=child_env)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
