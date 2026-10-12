"""Predict manually verified single-bird images and compare scale readings."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction import VISUAL_FEATURE_COLUMNS  # noqa: E402
from weight_prediction.edge_runtime import EdgeWeightPredictor  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard  # noqa: E402
from weight_prediction.weak_supervision import build_weak_dataset  # noqa: E402


ML_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    """Load project training settings without adding a runtime dependency."""
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
    parser = argparse.ArgumentParser(description="Evaluate the visual model on manually verified single-bird images.")
    parser.add_argument("--images-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    feature_source = parser.add_mutually_exclusive_group(required=True)
    feature_source.add_argument("--features", type=Path, help="Existing derived visual-feature CSV.")
    feature_source.add_argument("--captures", type=Path, help="Full session_capture_metadata CSV used to derive geometry on demand.")
    parser.add_argument("--performance-standard", type=Path)
    parser.add_argument("--breed")
    parser.add_argument("--sex", choices=("male", "female", "as_hatched"))
    parser.add_argument("--age-start-date", help="YYYY-MM-DD capture date whose flock age is known.")
    parser.add_argument("--age-days-at-start", type=int)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary-output", required=True, type=Path)
    parser.add_argument(
        "--max-standard-relative-diff-pct",
        type=float,
        default=float(os.getenv("SINGLE_BIRD_QUALITY_GATE_MAX_STANDARD_RELATIVE_DIFF_PCT", "50")),
        help=(
            "Reject a scale label when it differs from the approved breed/sex/age "
            "standard by more than this percentage. Set a negative value to disable."
        ),
    )
    parser.add_argument(
        "--use-standard-plausibility-gate",
        action=argparse.BooleanOptionalAction,
        default=env_bool("SINGLE_BIRD_QUALITY_GATE_ENABLED", True),
        help="Apply the configured Standard-vs-scale plausibility gate before scoring.",
    )
    parser.add_argument(
        "--use-weight-error-quality-gate",
        action=argparse.BooleanOptionalAction,
        default=env_bool("WEIGHT_ERROR_QUALITY_GATE_ENABLED", True),
        help="Reject captures whose raw metadata contains scale.weight_error before scoring.",
    )
    parser.add_argument(
        "--use-nonpositive-height-quality-gate",
        action=argparse.BooleanOptionalAction,
        default=env_bool("NONPOSITIVE_HEIGHT_QUALITY_GATE_ENABLED", True),
        help="Reject captures whose inferred height_mm is zero or negative before scoring.",
    )
    parser.add_argument("--exclude-image", action="append", default=[], help="Image filename or stem rejected during manual review. May be supplied more than once.")
    args = parser.parse_args()

    image_stems = {path.stem for path in args.images_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}}
    excluded_stems = {Path(value).stem for value in args.exclude_image}
    excluded_found = sorted(image_stems & excluded_stems)
    image_stems -= excluded_stems
    manifest = pd.read_csv(args.manifest)
    manifest["image_stem"] = manifest.object_key.map(lambda value: Path(value).stem)
    selected = manifest[manifest.image_stem.isin(image_stems)].copy()
    if args.features:
        features = pd.read_csv(args.features)
    else:
        context = {"breed": args.breed, "sex": args.sex, "age_start_date": args.age_start_date, "age_days_at_start": args.age_days_at_start}
        missing_context = [name for name, value in {"performance_standard": args.performance_standard, **context}.items() if value is None]
        if missing_context:
            parser.error(f"--captures requires: {', '.join(missing_context)}")
        features = build_weak_dataset(
            args.captures,
            PerformanceStandard(args.performance_standard),
            context,
            reject_weight_error=args.use_weight_error_quality_gate,
            reject_nonpositive_height=args.use_nonpositive_height_quality_gate,
        )
    excluded_by_weight_error_gate = pd.DataFrame()
    if args.use_weight_error_quality_gate:
        if "weight_error" not in features.columns:
            parser.error("The weight-error quality gate requires --captures so raw capture metadata can be inspected.")
        rejected_session_ids = set(features.loc[features.weight_error.notna(), "session_id"])
        excluded_by_weight_error_gate = selected[selected.session_id.isin(rejected_session_ids)].copy()
        selected = selected[~selected.session_id.isin(rejected_session_ids)].copy()
    excluded_by_nonpositive_height_gate = pd.DataFrame()
    if args.use_nonpositive_height_quality_gate:
        if "height_mm" not in features.columns:
            parser.error("The nonpositive-height quality gate requires features with height_mm (use --captures).")
        rejected_session_ids = set(features.loc[features.height_mm.le(0), "session_id"])
        excluded_by_nonpositive_height_gate = selected[selected.session_id.isin(rejected_session_ids)].copy()
        selected = selected[~selected.session_id.isin(rejected_session_ids)].copy()
    if features.session_id.duplicated().any():
        # A verified candidate must have exactly one detection. Keep the source
        # data explicit rather than silently choosing one detection.
        duplicated = features[features.session_id.duplicated(keep=False)].session_id.unique().tolist()
        selected = selected[~selected.session_id.isin(duplicated)].copy()
    feature_columns = ["session_id", *VISUAL_FEATURE_COLUMNS]
    if "standard_weight_g" in features.columns:
        feature_columns.append("standard_weight_g")
    feature_rows = features[features.session_id.isin(selected.session_id)][feature_columns]
    merged = selected.merge(feature_rows, on="session_id", how="left", validate="one_to_one")
    missing_feature_sessions = merged[merged[VISUAL_FEATURE_COLUMNS].isna().any(axis=1)].session_id.tolist()
    scored = merged.dropna(subset=VISUAL_FEATURE_COLUMNS).copy()

    excluded_by_standard_gate = pd.DataFrame()
    if args.use_standard_plausibility_gate:
        if args.max_standard_relative_diff_pct < 0:
            parser.error("--max-standard-relative-diff-pct must be zero or greater when the gate is enabled.")
        if "standard_weight_g" not in scored.columns:
            parser.error("The standard plausibility gate requires --captures with performance-standard context.")
        if (scored.standard_weight_g <= 0).any():
            parser.error("The standard plausibility gate requires positive standard_weight_g values.")
        scored["standard_relative_diff_pct"] = (
            (scored.displayed_weight_g - scored.standard_weight_g).abs()
            / scored.standard_weight_g
            * 100
        )
        rejected = scored.standard_relative_diff_pct > args.max_standard_relative_diff_pct
        excluded_by_standard_gate = scored.loc[rejected].copy()
        scored = scored.loc[~rejected].copy()

    predictor = EdgeWeightPredictor(args.package_dir)
    predictions = []
    for _, row in scored.iterrows():
        event = {name: float(row[name]) for name in VISUAL_FEATURE_COLUMNS}
        response = predictor.predict(event)
        predictions.append(float(response["predicted_weight_g"]))
    scored["predicted_weight_g"] = predictions
    scored["display_error_g"] = scored.predicted_weight_g - scored.displayed_weight_g
    scored["absolute_display_error_g"] = scored.display_error_g.abs()
    scored["absolute_display_error_pct"] = scored.absolute_display_error_g / scored.displayed_weight_g * 100
    scored["within_100g"] = scored.absolute_display_error_g <= 100
    columns = ["session_id", "media_id", "object_key", "captured_at", "displayed_weight_g", "scale_resolution_g", "predicted_weight_g", "display_error_g", "absolute_display_error_g", "absolute_display_error_pct", "within_100g"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scored[columns].sort_values("captured_at").to_csv(args.output, index=False)
    rejected_output = args.output.with_name(f"{args.output.stem}_excluded_by_standard_gate.csv")
    weight_error_rejected_output = args.output.with_name(f"{args.output.stem}_excluded_by_weight_error_gate.csv")
    height_rejected_output = args.output.with_name(f"{args.output.stem}_excluded_by_nonpositive_height_gate.csv")
    excluded_by_weight_error_gate.assign(exclusion_reason="scale_weight_error_present").to_csv(weight_error_rejected_output, index=False)
    excluded_by_nonpositive_height_gate.assign(exclusion_reason="height_mm_nonpositive").to_csv(height_rejected_output, index=False)
    if not excluded_by_standard_gate.empty:
        excluded_by_standard_gate.assign(
            exclusion_reason="scale_weight_differs_from_standard_over_threshold",
        )[
            [
                "session_id", "media_id", "object_key", "captured_at", "displayed_weight_g",
                "standard_weight_g", "standard_relative_diff_pct", "scale_resolution_g", "exclusion_reason",
            ]
        ].sort_values("captured_at").to_csv(rejected_output, index=False)
    elif rejected_output.exists():
        rejected_output.unlink()
    summary = {
        "images_found": len(image_stems) + len(excluded_found),
        "excluded_after_manual_review": excluded_found,
        "images_selected_for_prediction": len(image_stems),
        "matched_manifest_rows": len(selected),
        "feature_source": str(args.features or args.captures),
        "predictions_completed": len(scored),
        "missing_feature_sessions": missing_feature_sessions,
        "standard_plausibility_gate": {
            "enabled": args.use_standard_plausibility_gate,
            "max_standard_relative_diff_pct": args.max_standard_relative_diff_pct,
            "excluded_count": len(excluded_by_standard_gate),
            "excluded_output": str(rejected_output) if len(excluded_by_standard_gate) else None,
        },
        "weight_error_quality_gate": {
            "enabled": args.use_weight_error_quality_gate,
            "excluded_count": len(excluded_by_weight_error_gate),
            "excluded_output": str(weight_error_rejected_output),
        },
        "nonpositive_height_quality_gate": {
            "enabled": args.use_nonpositive_height_quality_gate,
            "excluded_count": len(excluded_by_nonpositive_height_gate),
            "excluded_output": str(height_rejected_output),
        },
        "display_error_metrics": {
            "mae_g": float(scored.absolute_display_error_g.mean()) if len(scored) else None,
            "rmse_g": float(np.sqrt(np.mean(scored.display_error_g ** 2))) if len(scored) else None,
            "mape_pct": float(scored.absolute_display_error_pct.mean()) if len(scored) else None,
            "mean_error_g": float(scored.display_error_g.mean()) if len(scored) else None,
            "within_100g_pct": float(scored.within_100g.mean() * 100) if len(scored) else None,
        },
        "note": "Scale resolution is 100 g. Metrics compare to the displayed scale value; they do not claim sub-step ground-truth precision.",
    }
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
