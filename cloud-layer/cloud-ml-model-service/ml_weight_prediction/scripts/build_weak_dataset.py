from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction.weak_supervision import build_weak_dataset  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard, REFERENCE_WORKBOOK_FILENAME  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an auditable weak-label dataset from group-scale capture telemetry.")
    parser.add_argument("--captures", required=True, type=Path, help="session_capture_metadata.csv")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    parser.add_argument("--performance-standard", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "sample_data" / REFERENCE_WORKBOOK_FILENAME)
    parser.add_argument("--default-breed", help="Explicit fallback breed for legacy capture metadata, e.g. 'Arbor Acres Plus'.")
    parser.add_argument("--default-sex", help="Explicit fallback sex for legacy capture metadata: male, female, or as_hatched.")
    parser.add_argument("--default-age-days", type=int, help="Explicit fallback flock age in days for legacy capture metadata.")
    args = parser.parse_args()
    context_defaults = {
        field: value
        for field, value in {
            "breed": args.default_breed,
            "sex": args.default_sex,
            "age_days": args.default_age_days,
        }.items()
        if value is not None
    }
    dataset = build_weak_dataset(args.captures, PerformanceStandard(args.performance_standard), context_defaults)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(args.audit_output, index=False)
    eligible = dataset[dataset.quality_pass].copy()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    eligible.to_csv(args.output, index=False)
    print(f"audited={len(dataset)} eligible={len(eligible)} sessions={eligible.session_id.nunique()} output={args.output}")
    if eligible.empty:
        raise SystemExit("No quality-passing group-scale detections; review audit output.")


if __name__ == "__main__":
    main()
