import json

import pytest

from app.db import InferenceDb


class _FakeConn:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    async def fetchrow(self, *_args, **_kwargs):
        return self._row

    async def fetch(self, *_args, **_kwargs):
        return self._rows


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_inference_result_parses_jsonb_metadata_strings():
    row = {
        "id": "result-1",
        "model_version": "wv-shadow-1.0.0",
        "metadata": json.dumps({"package_id": "pkg-1", "prediction_mode": "shadow"}),
    }
    db = InferenceDb("postgresql://unused")
    db.pool = _FakePool(_FakeConn(row=row))

    result = await db.get_inference_result("result-1")

    assert result is not None
    assert result["metadata"]["package_id"] == "pkg-1"
    assert result["metadata"]["prediction_mode"] == "shadow"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_inference_results_by_session_parses_jsonb_metadata_strings():
    rows = [
        {
            "id": "result-1",
            "session_id": "sess-1",
            "metadata": json.dumps({"package_version": "2026.07.14"}),
        },
        {
            "id": "result-2",
            "session_id": "sess-1",
            "metadata": {"stub_mode": False},
        },
    ]
    db = InferenceDb("postgresql://unused")
    db.pool = _FakePool(_FakeConn(rows=rows))

    result = await db.get_inference_results_by_session("sess-1", 10)

    assert result[0]["metadata"]["package_version"] == "2026.07.14"
    assert result[1]["metadata"]["stub_mode"] is False
