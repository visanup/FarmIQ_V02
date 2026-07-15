from pathlib import Path
from types import SimpleNamespace

from app.processor import CaptureProcessor


class DummyStateStore:
    def __init__(self) -> None:
        self.processed: set[str] = set()

    def is_processed(self, path: str) -> bool:
        return path in self.processed

    def mark_processed(self, path: str) -> None:
        self.processed.add(path)


def build_processor(tmp_path: Path) -> CaptureProcessor:
    config = SimpleNamespace(
        capture=SimpleNamespace(data_dir=str(tmp_path)),
        mqtt=SimpleNamespace(qos=1),
        dry_run=True,
        device=SimpleNamespace(
            tenant_id="tenant-test",
            farm_id="farm-test",
            barn_id="barn-test",
            device_id="device-test",
            station_id="station-test",
        ),
    )
    return CaptureProcessor(
        config=config,
        mqtt=SimpleNamespace(),
        uploader=SimpleNamespace(),
        state=DummyStateStore(),
        session_client=SimpleNamespace(),
    )


def test_process_one_metadata_resolves_relative_path_and_marks_processed(
    tmp_path: Path,
) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir(parents=True)
    metadata_path = metadata_dir / "capture.json"
    metadata_path.write_text('{"image_id":"capture"}', encoding="utf-8")

    processor = build_processor(tmp_path)
    called: list[Path] = []
    processor._process_metadata = lambda path: called.append(path)  # type: ignore[method-assign]

    result = processor.process_one_metadata(Path("capture.json"))

    assert result is True
    assert called == [metadata_path.resolve()]
    assert processor.state.is_processed(str(metadata_path.resolve()))


def test_process_one_metadata_skips_processed_without_force(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir(parents=True)
    metadata_path = metadata_dir / "capture.json"
    metadata_path.write_text('{"image_id":"capture"}', encoding="utf-8")

    processor = build_processor(tmp_path)
    processor.state.mark_processed(str(metadata_path.resolve()))
    processor._process_metadata = lambda path: (_ for _ in ()).throw(  # type: ignore[method-assign]
        AssertionError("_process_metadata should not be called")
    )

    result = processor.process_one_metadata(metadata_path)

    assert result is False
