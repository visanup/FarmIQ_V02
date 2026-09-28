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
from weight_prediction import FEATURE_COLUMNS  # noqa: E402


def metrics(y: pd.Series, pred: np.ndarray) -> dict[str, float]:
    error = y.to_numpy() - pred
    nonzero = y.to_numpy() != 0
    return {
        "n": int(len(y)), "mae_g": float(mean_absolute_error(y, pred)),
        "rmse_g": float(mean_squared_error(y, pred) ** 0.5),
        "mape_pct": float(np.mean(np.abs(error[nonzero] / y.to_numpy()[nonzero])) * 100) if nonzero.any() else float("nan"),
        "p95_absolute_error_g": float(np.percentile(np.abs(error), 95)), "mean_error_g": float(np.mean(error)),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Train a leakage-safe XGBoost individual-weight candidate.")
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args()
    try:
        from xgboost import XGBRegressor
    except ImportError as error:
        raise SystemExit("xgboost is required; install requirements.txt") from error
    data = pd.read_csv(args.dataset)
    required = set(FEATURE_COLUMNS + ["actual_weight_g", "captured_at"])
    missing = required - set(data.columns)
    if missing:
        raise SystemExit(f"dataset missing columns: {', '.join(sorted(missing))}")
    if data[FEATURE_COLUMNS + ["actual_weight_g"]].isna().any().any():
        raise SystemExit("dataset has missing model features or labels; use the audit report to resolve them")
    data["split_group"] = data.get("batch_id", pd.Series(index=data.index, dtype=object)).fillna(pd.to_datetime(data.captured_at, utc=True).dt.date.astype(str))
    group_dates = data.groupby("split_group").captured_at.min().sort_values()
    groups = group_dates.index.tolist()
    if len(groups) < 5:
        raise SystemExit(f"need at least 5 independent batch_id/days for chronological split; found {len(groups)}")
    test_n = max(1, round(len(groups) * 0.20))
    validation_n = max(1, round((len(groups) - test_n) * 0.25))
    train_groups = groups[: -test_n - validation_n]
    validation_groups = groups[-test_n - validation_n : -test_n]
    test_groups = groups[-test_n:]
    if not train_groups:
        raise SystemExit("not enough groups remaining after train/validation/test split")
    splits = {"train": data[data.split_group.isin(train_groups)], "validation": data[data.split_group.isin(validation_groups)], "test": data[data.split_group.isin(test_groups)]}
    x_train = splits["train"][FEATURE_COLUMNS]
    # The model learns each bird's deviation from its breed/sex/age objective.
    # This keeps the Aviagen curve as the baseline at inference rather than
    # letting visual geometry alone determine the expected age-related weight.
    y_train = splits["train"].actual_weight_g - splits["train"].standard_weight_g
    model = XGBRegressor(n_estimators=800, max_depth=5, learning_rate=0.03, subsample=0.8, colsample_bytree=0.9, reg_lambda=2.0, objective="reg:absoluteerror", random_state=42, n_jobs=1)
    validation_target = splits["validation"].actual_weight_g - splits["validation"].standard_weight_g
    model.fit(x_train, y_train, eval_set=[(splits["validation"][FEATURE_COLUMNS], validation_target)], verbose=False)
    baseline_residual = float(y_train.median())
    report: dict[str, object] = {"target_transform": "standard_weight_residual", "feature_columns": FEATURE_COLUMNS, "split_groups": {k: sorted(frame.split_group.unique().tolist()) for k, frame in splits.items()}, "baseline_train_median_residual_g": baseline_residual, "metrics": {}}
    prediction_rows = []
    for name, frame in splits.items():
        predicted_residual = model.predict(frame[FEATURE_COLUMNS])
        pred = frame.standard_weight_g.to_numpy() + predicted_residual
        baseline_pred = frame.standard_weight_g.to_numpy() + baseline_residual
        report["metrics"][name] = {"xgboost": metrics(frame.actual_weight_g, pred), "growth_standard_baseline": metrics(frame.actual_weight_g, baseline_pred)}
        prediction_rows.append(frame[["record_id", "split_group", "actual_weight_g", "breed", "sex", "age_days", "standard_weight_g"]].assign(split=name, predicted_weight_g=pred, predicted_residual_g=predicted_residual, absolute_error_g=np.abs(frame.actual_weight_g - pred)))
    test_xgb = report["metrics"]["test"]["xgboost"]["mae_g"]
    test_base = report["metrics"]["test"]["growth_standard_baseline"]["mae_g"]
    report["test_mae_improvement_vs_baseline_pct"] = float((test_base - test_xgb) / test_base * 100) if test_base else None
    report["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output_dir / "model.joblib")
    (args.output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    pd.concat(prediction_rows).to_csv(args.output_dir / "holdout_predictions.csv", index=False)
    print(json.dumps(report["metrics"]["test"], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
