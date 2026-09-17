from pathlib import Path

import pyarrow.parquet as pq

from feature_store.farmiq_features import (
    barn_telemetry_source,
    bird_performance_source,
    ensure_local_feature_files,
    environmental_source,
    feed_consumption_source,
    parse_feature_timestamp,
)


EXPECTED_DATASETS = {
    "barn_telemetry.parquet",
    "bird_performance.parquet",
    "feed_consumption.parquet",
    "environmental.parquet",
}


def test_file_sources_set_timestamp_field_explicitly() -> None:
    sources = (
        barn_telemetry_source,
        bird_performance_source,
        feed_consumption_source,
        environmental_source,
    )

    assert all(source.timestamp_field == "event_timestamp" for source in sources)


def test_parse_feature_timestamp_returns_timezone_aware_datetime() -> None:
    parsed = parse_feature_timestamp("2026-08-24T00:00:00Z")

    assert parsed.isoformat() == "2026-08-24T00:00:00+00:00"


def test_bootstrap_creates_schema_only_parquet_files(tmp_path: Path) -> None:
    created = ensure_local_feature_files(tmp_path)

    assert {path.name for path in created} == EXPECTED_DATASETS
    assert {path.name for path in tmp_path.iterdir()} == EXPECTED_DATASETS

    for path in created:
        table = pq.read_table(path)
        assert table.num_rows == 0
        assert "event_timestamp" in table.column_names
        assert "created_timestamp" in table.column_names


def test_bootstrap_does_not_overwrite_existing_data(tmp_path: Path) -> None:
    ensure_local_feature_files(tmp_path)
    existing = tmp_path / "barn_telemetry.parquet"
    original = existing.read_bytes()

    created = ensure_local_feature_files(tmp_path)

    assert created == []
    assert existing.read_bytes() == original
