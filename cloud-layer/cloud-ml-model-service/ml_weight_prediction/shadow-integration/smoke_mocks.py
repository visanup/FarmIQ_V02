"""Isolated synthetic session/media providers. Never connect to farm endpoints."""
from fastapi import FastAPI
from fastapi.responses import Response
from tests.test_allocation_shadow import mock_capture

app = FastAPI()


@app.get('/api/ready')
def ready():
    return {'ready': True, 'fixture_only': True}


@app.get('/api/v1/weighvision/sessions/{session_id}')
def session(session_id: str):
    event = mock_capture()
    raw = event['raw_metadata']
    raw['session_id'] = session_id
    if session_id.endswith('-reject'):
        raw['scale']['weight_stable'] = False
    return {'sessionId': session_id, 'captureMetadata': [{
        'captureId': event['capture_id'], 'mediaIds': ['mock-media'],
        'occurredAt': event['captured_at'], 'rawMetadata': raw,
        'featureSchemaVersion': '1.0', 'normalizedFeatures': {'area_mm2': 7000},
    }]}


@app.get('/api/v1/media/objects/{media_id}')
def media(media_id: str):
    # The existing scalar interface only checks the file; geometry comes from metadata.
    return Response(b'synthetic-media-fixture', media_type='application/octet-stream')


@app.post('/api/v1/weighvision/sessions/{session_id}/{action}')
def outcome(session_id: str, action: str):
    return {'fixture_only': True, 'ok': True}
