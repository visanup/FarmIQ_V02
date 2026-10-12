"""Replay one archived real chicken image/geometry as a new dev IoT event.

This is an integration replay, not a new physical scale measurement. Device
and station IDs must equal the IDs bound to the active Batch in dashboard-web.
"""

import csv
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "cloud-layer/cloud-ml-model-service/ml_weight_prediction/docs/sample_data/session_id_20260919"
SOURCE_SESSION = "20260919_000740"
DEVICE = "f2dc205d-92a6-4a1b-ba80-6c95612dcc9d"
STATION = "f201fd16-2485-4d60-903f-b7b577114900"
CONTAINER = "iot-layer-weight-vision-service-1"


def find_row(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return next(row for row in csv.DictReader(file) if row["session_id"] == SOURCE_SESSION)


def main():
    capture = find_row(SAMPLE / "metadata/session_capture_metadata-1789967494963.csv")
    media = find_row(SAMPLE / "metadata/media_objects-1789967735311.csv")
    image = SAMPLE / "images" / Path(media["object_key"]).name
    session_id = f"hybrid75-dev-{int(time.time())}"
    metadata = json.loads(capture["raw_metadata"])
    metadata.update({
        "image_id": session_id,
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    for detection in metadata.get("detections", []):
        detection.pop("mask_path", None)
    for record in metadata.get("per_chicken_records", []):
        record["capture_id"] = session_id
        record["session_id"] = session_id
        record.pop("mask_path", None)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as work:
        folder = Path(work)
        (folder / "metadata").mkdir()
        (folder / "images").mkdir()
        (folder / "metadata" / f"{session_id}.json").write_text(json.dumps(metadata), encoding="utf-8")
        shutil.copyfile(image, folder / "images" / f"{session_id}_vis.jpg")
        remote = f"/tmp/{session_id}"
        subprocess.run(["docker", "cp", str(folder), f"{CONTAINER}:{remote}"], check=True)
        result = subprocess.run([
            "docker", "exec",
            "-e", f"DEVICE_ID={DEVICE}",
            "-e", f"STATION_ID={STATION}",
            "-e", f"MQTT_CLIENT_ID={session_id}",
            "-e", f"CAPTURE_DATA_DIR={remote}",
            "-e", f"METADATA_FILE_ONCE={remote}/metadata/{session_id}.json",
            "-e", f"EVENT_BUFFER_DIR={remote}/buffer",
            "-e", f"STATE_DIR={remote}/state",
            CONTAINER, "python", "-m", "app.main",
        ], capture_output=True, text=True)
    print(json.dumps({"session_id": session_id, "replayed_image": str(image),
                      "device_id": DEVICE, "station_id": STATION,
                      "exit_code": result.returncode}, indent=2))
    print(result.stdout[-2500:])
    print(result.stderr[-6500:])
    if result.returncode:
        raise SystemExit(result.returncode)
    for failure in ("Bind media failed", "Create session failed", "Persist capture metadata failed", "Trigger edge inference failed"):
        if failure in result.stderr:
            raise RuntimeError(f"IoT replay reported: {failure}")


if __name__ == "__main__":
    main()
