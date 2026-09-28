from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction.features import build_rows  # noqa: E402
from weight_prediction.performance_standard import PerformanceStandard, REFERENCE_WORKBOOK_FILENAME  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Build auditable individual-weight feature rows from FarmIQ metadata.")
    p.add_argument("--metadata", required=True, nargs="+", type=Path)
    p.add_argument("--labels", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--audit-output", required=True, type=Path)
    p.add_argument("--height-min-mm", type=float, required=True)
    p.add_argument("--height-max-mm", type=float, required=True)
    p.add_argument("--performance-standard", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "sample_data" / REFERENCE_WORKBOOK_FILENAME)
    args = p.parse_args()
    if args.height_min_mm <= 0 or args.height_max_mm <= args.height_min_mm:
        p.error("height bounds must be positive and max must be greater than min")
    labels = pd.read_csv(args.labels)
    required = {"record_id", "actual_weight_g", "weight_stable", "weight_label_type", "breed", "sex", "age_days"}
    missing = required - set(labels.columns)
    if missing:
        p.error(f"labels missing required columns: {', '.join(sorted(missing))}")
    if labels.record_id.duplicated().any():
        p.error("labels has duplicate record_id values")
    performance_standard = PerformanceStandard(args.performance_standard)
    rows = [row for path in args.metadata for row in build_rows(path, labels, (args.height_min_mm, args.height_max_mm), performance_standard)]
    audit = pd.DataFrame(rows)
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.audit_output, index=False)
    eligible = audit[audit.quality_pass].copy() if not audit.empty else audit
    args.output.parent.mkdir(parents=True, exist_ok=True)
    eligible.to_csv(args.output, index=False)
    print(f"audited={len(audit)} eligible={len(eligible)} audit={args.audit_output} dataset={args.output}")
    if eligible.empty:
        raise SystemExit("No eligible labelled rows. Read audit CSV; no model was trained.")


if __name__ == "__main__":
    main()
