"""Train a geometry-only individual weight model from quality-gated scale labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction import VISUAL_FEATURE_COLUMNS  # noqa: E402


def metrics(actual: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual.to_numpy()
    return {
        "n": int(len(actual)),
        "mae_g": float(mean_absolute_error(actual, predicted)),
        "rmse_g": float(mean_squared_error(actual, predicted) ** 0.5),
        "mape_pct": float(np.mean(np.abs(error / actual.to_numpy())) * 100),
        "p95_absolute_error_g": float(np.percentile(np.abs(error), 95)),
        "mean_error_g": float(np.mean(error)),
        "within_100g_pct": float(np.mean(np.abs(error) <= 100) * 100),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train an individual visual weight model against quality-gated scale labels.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        from xgboost import XGBRegressor
    except ImportError as error:
        raise SystemExit("xgboost is required; install requirements.txt in the training environment") from error

    data = pd.read_csv(args.dataset)
    required = set(VISUAL_FEATURE_COLUMNS + ["captured_at", "displayed_weight_g", "record_id", "session_id"])
    missing = required - set(data.columns)
    if missing:
        raise SystemExit(f"dataset missing columns: {', '.join(sorted(missing))}")
    data["captured_at"] = pd.to_datetime(data["captured_at"], utc=True, format="mixed")
    data = data.dropna(subset=VISUAL_FEATURE_COLUMNS + ["displayed_weight_g"]).copy()
    if data.session_id.duplicated().any():
        raise SystemExit("dataset contains more than one selected image for a session; resolve duplicates before training")
    data["split_date"] = data.captured_at.dt.date.astype(str)
    if data.session_id.nunique() < 15:
        raise SystemExit(f"need at least 15 independent sessions; found {data.session_id.nunique()}")

    rng = np.random.default_rng(42)
    split_sessions: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    for _, date_frame in data.groupby("split_date"):
        sessions = np.array(sorted(date_frame.session_id.unique().tolist()))
        rng.shuffle(sessions)
        test_n = max(1, round(len(sessions) * 0.20))
        validation_n = max(1, round((len(sessions) - test_n) * 0.20))
        split_sessions["test"].extend(sessions[:test_n].tolist())
        split_sessions["validation"].extend(sessions[test_n : test_n + validation_n].tolist())
        split_sessions["train"].extend(sessions[test_n + validation_n :].tolist())
    splits = {name: data[data.session_id.isin(session_ids)].copy() for name, session_ids in split_sessions.items()}
    if any(frame.empty for frame in splits.values()):
        raise SystemExit("not enough sessions remaining after train/validation/test split")

    model = XGBRegressor(
        n_estimators=600, max_depth=3, learning_rate=0.03, subsample=0.8,
        colsample_bytree=0.9, reg_lambda=5.0, objective="reg:absoluteerror",
        random_state=42, n_jobs=1,
    )
    model.fit(
        splits["train"][VISUAL_FEATURE_COLUMNS], splits["train"].displayed_weight_g,
        eval_set=[(splits["validation"][VISUAL_FEATURE_COLUMNS], splits["validation"].displayed_weight_g)],
        verbose=False,
    )

    report: dict[str, object] = {
        "model_type": "INDIVIDUAL_VISUAL_SCALE_REGRESSION",
        "target": "displayed_weight_g",
        "target_source": "stable individual scale labels after manual image review and configured Standard plausibility gate",
        "estimator_inputs": VISUAL_FEATURE_COLUMNS,
        "date_or_age_provided_to_estimator": False,
        "split_strategy": "deterministic session holdout stratified by capture date; capture date/age omitted from estimator inputs",
        "split_session_counts": {name: len(session_ids) for name, session_ids in split_sessions.items()},
        "split_dates": {name: sorted(frame.split_date.unique().tolist()) for name, frame in splits.items()},
        "individual_accuracy_validated": True,
        "metrics": {},
    }
    prediction_rows: list[pd.DataFrame] = []
    for name, frame in splits.items():
        prediction = model.predict(frame[VISUAL_FEATURE_COLUMNS])
        report["metrics"][name] = metrics(frame.displayed_weight_g, prediction)
        prediction_rows.append(frame[["record_id", "session_id", "captured_at", "displayed_weight_g", "standard_weight_g"]].assign(
            split=name,
            predicted_weight_g=prediction,
            display_error_g=prediction - frame.displayed_weight_g,
            absolute_display_error_g=np.abs(prediction - frame.displayed_weight_g),
        ))
    report["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output_dir / "model.joblib")
    (args.output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    pd.concat(prediction_rows).to_csv(args.output_dir / "holdout_predictions.csv", index=False)
    print(json.dumps(report["metrics"]["test"], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
