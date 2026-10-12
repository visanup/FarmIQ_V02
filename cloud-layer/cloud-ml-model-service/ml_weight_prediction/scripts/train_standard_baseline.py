"""Create an individual-weight standard-growth baseline package candidate.

This is intentionally not a visual ML model: it predicts the approved breed,
sex, and age reference weight when individual scale labels are unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyRegressor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction import FEATURE_COLUMNS  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a standard-growth individual-weight baseline candidate.")
    parser.add_argument("--performance-standard", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("output directory already contains artifacts; use a new versioned directory")
    standard = PerformanceStandard(args.performance_standard)
    model = DummyRegressor(strategy="constant", constant=0.0)
    model.fit(np.zeros((1, len(FEATURE_COLUMNS))), np.array([0.0]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output_dir / "model.joblib")
    metrics = {
        "model_type": "STANDARD_GROWTH_BASELINE",
        "individual_accuracy_validated": False,
        "target_transform": "standard_weight_residual",
        "feature_columns": FEATURE_COLUMNS,
        "performance_standard": standard.coverage(),
        "dataset_sha256": hashlib.sha256(args.performance_standard.read_bytes()).hexdigest(),
        "metrics": {},
        "limitations": [
            "Predictions equal the approved standard weight for breed, sex, and age.",
            "No individual scale labels were used.",
            "This artifact must not be presented as validated individual-weight accuracy.",
        ],
    }
    (args.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
