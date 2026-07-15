from __future__ import annotations

import shutil
import unittest
from pathlib import Path
import sys
from uuid import uuid4

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from model_runtime import (
    list_model_profiles,
    resolve_fallback_profile,
    resolve_model_profile,
    resolve_setting,
)

TEST_TMP_ROOT = Path(__file__).resolve().parent / ".tmp"


def _make_temp_dir() -> Path:
    TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEST_TMP_ROOT / f"case-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


class ModelRuntimeTests(unittest.TestCase):
    def test_resolve_setting_prefers_cli_then_profile_then_fallback(self) -> None:
        self.assertEqual(resolve_setting(1, 2, 3), 1)
        self.assertEqual(resolve_setting(None, 2, 3), 2)
        self.assertEqual(resolve_setting(None, None, 3), 3)

    def test_list_model_profiles_reads_yaml_config(self) -> None:
        tmp_path = _make_temp_dir()
        try:
            model_dir = tmp_path / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "baseline.pt").write_bytes(b"pt")
            config_path = model_dir / "runtime-config.yaml"
            config_path.write_text(
                """
active_model: baseline
models:
  baseline:
    path: baseline.pt
    conf: 0.3
    iou: 0.5
""".strip(),
                encoding="utf-8",
            )
            profiles = list_model_profiles(config_path)
            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0].model_id, "baseline")
            self.assertEqual(profiles[0].path, (model_dir / "baseline.pt").resolve())
            self.assertEqual(profiles[0].conf, 0.3)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def test_resolve_model_profile_from_config(self) -> None:
        tmp_path = _make_temp_dir()
        try:
            model_dir = tmp_path / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "candidate.pt").write_bytes(b"pt")
            config_path = model_dir / "runtime-config.yaml"
            config_path.write_text(
                """
active_model: candidate
models:
  candidate:
    path: candidate.pt
    family: ultralytics-seg
    imgsz: 640
""".strip(),
                encoding="utf-8",
            )
            profile = resolve_model_profile(model_id=None, model=None, model_config=config_path)
            self.assertEqual(profile.model_id, "candidate")
            self.assertEqual(profile.path, (model_dir / "candidate.pt").resolve())
            self.assertEqual(profile.imgsz, 640)
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def test_resolve_fallback_profile_from_config(self) -> None:
        tmp_path = _make_temp_dir()
        try:
            model_dir = tmp_path / "model"
            model_dir.mkdir(parents=True, exist_ok=True)
            (model_dir / "baseline.pt").write_bytes(b"pt")
            (model_dir / "candidate.pt").write_bytes(b"pt")
            config_path = model_dir / "runtime-config.yaml"
            config_path.write_text(
                """
active_model: candidate
fallback_model: baseline
models:
  baseline:
    path: baseline.pt
    family: ultralytics-seg
  candidate:
    path: candidate.pt
    family: ultralytics-seg
""".strip(),
                encoding="utf-8",
            )
            profile = resolve_fallback_profile(config_path)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.model_id, "baseline")
            self.assertEqual(profile.path, (model_dir / "baseline.pt").resolve())
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
