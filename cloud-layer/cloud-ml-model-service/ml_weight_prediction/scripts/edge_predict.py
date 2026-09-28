from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from weight_prediction.edge_runtime import EdgeWeightPredictor  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Run one validated edge prediction from a JSON event.")
    p.add_argument("--package-dir", required=True, type=Path)
    p.add_argument("--event", required=True, type=Path, help="JSON object containing model feature values")
    args = p.parse_args()
    result = EdgeWeightPredictor(args.package_dir).predict(json.loads(args.event.read_text(encoding="utf-8")))
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
