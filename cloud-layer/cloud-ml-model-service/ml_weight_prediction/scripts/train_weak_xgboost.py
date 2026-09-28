from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction import FEATURE_COLUMNS  # noqa: E402


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = actual - predicted
    return {"n": int(len(actual)), "mae_g": float(np.mean(np.abs(error))), "rmse_g": float(np.sqrt(np.mean(error ** 2))), "p95_absolute_error_g": float(np.percentile(np.abs(error), 95)), "mean_error_g": float(np.mean(error))}


def _group_raw_metrics(frame: pd.DataFrame, prediction: np.ndarray) -> dict[str, float]:
    totals = frame.assign(raw_prediction_g=prediction).groupby("session_id", as_index=False).agg(group_total_weight_g=("group_total_weight_g", "first"), raw_prediction_g=("raw_prediction_g", "sum"))
    return _metrics(totals.group_total_weight_g.to_numpy(), totals.raw_prediction_g.to_numpy())


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a weakly supervised XGBoost group-scale allocation candidate.")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--allow-within-day-holdout", action="store_true", help="Permit session-level holdout when captures span fewer than five days/batches. Results are non-production.")
    args = parser.parse_args()
    try:
        from xgboost import XGBRegressor
    except ImportError as error:
        raise SystemExit("xgboost is required; install requirements.txt in the training environment") from error
    data = pd.read_csv(args.dataset)
    required = set(FEATURE_COLUMNS + ["session_id", "captured_at", "pseudo_weight_g", "session_sample_weight", "group_total_weight_g"])
    missing = required - set(data.columns)
    if missing:
        raise SystemExit(f"dataset missing columns: {', '.join(sorted(missing))}")
    data = data.dropna(subset=["pseudo_weight_g", "session_sample_weight", "group_total_weight_g"]).copy()
    data["captured_at"] = pd.to_datetime(data["captured_at"], utc=True)
    data = data.sort_values(["captured_at", "session_id", "detection_index"])
    groups = data.groupby("session_id", as_index=False).captured_at.min().sort_values("captured_at").session_id.tolist()
    if len(groups) < 5:
        raise SystemExit(f"need at least five independent sessions; found {len(groups)}")
    independent_days = data.captured_at.dt.date.nunique()
    if independent_days < 5 and not args.allow_within_day_holdout:
        raise SystemExit("captures span fewer than five independent days/batches; use --allow-within-day-holdout only for a non-production experiment")
    test_n = max(1, round(len(groups) * 0.20))
    validation_n = max(1, round((len(groups) - test_n) * 0.25))
    split_groups = {"train": groups[: -test_n - validation_n], "validation": groups[-test_n - validation_n : -test_n], "test": groups[-test_n:]}
    if not split_groups["train"]:
        raise SystemExit("not enough sessions after split")
    splits = {name: data[data.session_id.isin(ids)].copy() for name, ids in split_groups.items()}
    model = XGBRegressor(n_estimators=600, max_depth=4, learning_rate=0.03, subsample=0.8, colsample_bytree=0.9, reg_lambda=2.0, objective="reg:absoluteerror", random_state=42, n_jobs=1)
    model.fit(splits["train"][FEATURE_COLUMNS], splits["train"].pseudo_weight_g, sample_weight=splits["train"].session_sample_weight, eval_set=[(splits["validation"][FEATURE_COLUMNS], splits["validation"].pseudo_weight_g)], verbose=False)
    report: dict[str, object] = {"model_type": "WEAKLY_SUPERVISED_GROUP_ALLOCATION", "target": "pseudo_weight_g", "individual_accuracy_validated": False, "within_day_holdout": independent_days < 5, "feature_columns": FEATURE_COLUMNS, "split_sessions": split_groups, "metrics": {}}
    predictions: list[pd.DataFrame] = []
    for name, frame in splits.items():
        raw = np.maximum(model.predict(frame[FEATURE_COLUMNS]), 0.001)
        allocated = frame.group_total_weight_g.to_numpy() * raw / pd.Series(raw, index=frame.index).groupby(frame.session_id).transform("sum").to_numpy()
        pseudo = frame.pseudo_weight_g.to_numpy()
        report["metrics"][name] = {"pseudo_label_error": _metrics(pseudo, raw), "raw_group_total_error": _group_raw_metrics(frame, raw)}
        predictions.append(frame[["session_id", "detection_index", "group_total_weight_g", "pseudo_weight_g"]].assign(split=name, raw_score_g=raw, allocated_weight_g=allocated, prediction_status="WEAK_ALLOCATION"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output_dir / "model.joblib")
    pd.concat(predictions).to_csv(args.output_dir / "holdout_allocations.csv", index=False)
    report["dataset_sha256"] = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    (args.output_dir / "metrics.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["metrics"]["test"], indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
