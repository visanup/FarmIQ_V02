"""Train a visual-only weight regressor against an approved growth standard.

The model sees only per-detection geometry emitted from the source image.  The
standard is used to build the target during training and evaluation, never as
an estimator feature.
"""

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
    error = actual.to_numpy() - predicted
    return {
        "n": int(len(actual)),
        "mae_g": float(mean_absolute_error(actual, predicted)),
        "rmse_g": float(mean_squared_error(actual, predicted) ** 0.5),
        "mape_pct": float(np.mean(np.abs(error / actual.to_numpy())) * 100),
        "p95_absolute_error_g": float(np.percentile(np.abs(error), 95)),
        "mean_error_g": float(np.mean(error)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a visual-only model using approved-standard targets.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        from xgboost import XGBRegressor
    except ImportError as error:
        raise SystemExit("xgboost is required; install requirements.txt in the training environment") from error

    data = pd.read_csv(args.dataset)
    required = set(VISUAL_FEATURE_COLUMNS + ["captured_at", "standard_weight_g", "record_id"])
    missing = required - set(data.columns)
    if missing:
        raise SystemExit(f"dataset missing columns: {', '.join(sorted(missing))}")
    data["captured_at"] = pd.to_datetime(data["captured_at"], utc=True, format="mixed")
    data = data.dropna(subset=VISUAL_FEATURE_COLUMNS + ["standard_weight_g"]).copy()
    data["split_date"] = data.captured_at.dt.date.astype(str)
    if data.session_id.nunique() < 5:
        raise SystemExit(f"need at least five independent sessions; found {data.session_id.nunique()}")
    # The target requires a capture date, but no date/age value enters the
    # estimator.  Keep whole sessions together and stratify their assignment by
    # date so each split covers the same growth range.
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
    if not split_sessions["train"]:
        raise SystemExit("not enough sessions remaining after train/validation/test split")
    splits = {name: data[data.session_id.isin(session_ids)].copy() for name, session_ids in split_sessions.items()}
    model = XGBRegressor(
        n_estimators=800, max_depth=5, learning_rate=0.03, subsample=0.8,
        colsample_bytree=0.9, reg_lambda=2.0, objective="reg:absoluteerror",
        random_state=42, n_jobs=1,
    )
    model.fit(
        splits["train"][VISUAL_FEATURE_COLUMNS], splits["train"].standard_weight_g,
        eval_set=[(splits["validation"][VISUAL_FEATURE_COLUMNS], splits["validation"].standard_weight_g)],
        verbose=False,
    )
    report: dict[str, object] = {
        "model_type": "VISUAL_STANDARD_PROXY_REGRESSION",
        "target": "standard_weight_g",
        "target_source": "approved growth-performance standard matched by capture date during dataset construction",
        "estimator_inputs": VISUAL_FEATURE_COLUMNS,
        "date_or_age_provided_to_estimator": False,
        "split_strategy": "deterministic session holdout stratified by capture date; capture date/age omitted from estimator inputs",
        "split_session_counts": {name: len(session_ids) for name, session_ids in split_sessions.items()},
        "split_dates": {name: sorted(frame.split_date.unique().tolist()) for name, frame in splits.items()},
        "individual_accuracy_validated": False,
        "metrics": {},
    }
    prediction_rows: list[pd.DataFrame] = []
    for name, frame in splits.items():
        prediction = model.predict(frame[VISUAL_FEATURE_COLUMNS])
        report["metrics"][name] = metrics(frame.standard_weight_g, prediction)
        prediction_rows.append(frame[["record_id", "session_id", "captured_at", "breed", "sex", "age_days", "standard_weight_g"]].assign(
            split=name,
            predicted_weight_g=prediction,
            absolute_error_g=np.abs(frame.standard_weight_g - prediction),
        ))
    report["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output_dir / "model.joblib")
    (args.output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    pd.concat(prediction_rows).to_csv(args.output_dir / "holdout_predictions.csv", index=False)
    print(json.dumps(report["metrics"]["test"], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
