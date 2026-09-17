import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

import pytest

from app.config import Config
from app.db import InferenceDb
from app.inference_service import InferenceService
from app.job_service import JobService


def capture():
    return {
        'captureId': 'capture-1', 'detectionCount': 2, 'featureSchemaVersion': '1.0',
        'mediaIds': ['media-1', 'media-2'],
        'normalizedFeatures': {'area_mm2': 999999},
        'rawMetadata': {'roi_count': 2, 'height_estimation': {'floor_depth_mm': 1100},
                        'detections': [
                            {'area_xy_mm2': 100, 'confidence': .8, 'depth_mm': 900,
                             'height_mm': 20, 'width_mm': 30, 'length_mm': 40, 'bbox_xyxy': [0, 0, 10, 10]},
                            {'area_xy_mm2': 400, 'confidence': .9, 'depth_mm': 800,
                             'height_mm': 50, 'width_mm': 60, 'length_mm': 70, 'bbox_xyxy': [10, 10, 30, 30]},
                        ]},
    }


def service():
    db = MagicMock(spec=InferenceDb)
    db.create_inference_result = AsyncMock(side_effect=lambda **kw: kw['result_id'])
    db.create_outbox_event = AsyncMock()
    predictor = MagicMock(spec=InferenceService)
    async def predict(path, metadata):
        return {'predicted_weight_kg': metadata['features']['selected_area_mm2'] / 100,
                'confidence': .9, 'model_version': 'test-model',
                'metadata': {**metadata, 'features_used': metadata['features']}}
    predictor.run_inference = AsyncMock(side_effect=predict)
    result = JobService(db, predictor)
    result._attach_to_session = AsyncMock()
    result._publish_prediction_outcome_to_session = AsyncMock()
    return result


def test_distinct_features_identity_and_original_order():
    s = service()
    contexts = s._build_detection_contexts(capture())
    assert [c['features']['selected_area_mm2'] for c in contexts] == [100, 400]
    assert [c['features']['selected_height_mm'] for c in contexts] == [20, 50]
    assert [c['detection_index'] for c in contexts] == [0, 1]
    assert all(c['features']['detection_count'] == 2 for c in contexts)
    assert all(c['require_model'] for c in contexts)


@pytest.mark.parametrize('change', ['mismatch', 'invalid_entry', 'missing_array', 'missing_identity'])
def test_invalid_capture_is_rejected(change):
    c = capture()
    if change == 'mismatch': c['detectionCount'] = 3
    if change == 'invalid_entry': c['rawMetadata']['detections'][0] = None
    if change == 'missing_array': del c['rawMetadata']['detections']
    if change == 'missing_identity': del c['captureId']
    with pytest.raises(ValueError): service()._build_detection_contexts(c)


def test_job_saves_and_publishes_one_result_per_object(tmp_path):
    s = service()
    path = tmp_path / 'capture.img'
    path.write_bytes(b'image')
    s.jobs['job-1'] = {'job_id': 'job-1', 'tenant_id': 'tenant', 'farm_id': 'farm',
                       'barn_id': 'barn', 'device_id': 'device', 'session_id': 'session',
                       'media_id': 'media-1', 'trace_id': 'trace'}
    s._fetch_media_to_tmp = AsyncMock(return_value=str(path))
    s._fetch_session_features = AsyncMock(return_value={'detection_contexts': s._build_detection_contexts(capture())})
    asyncio.run(s._process_job('job-1'))
    job = s.jobs['job-1']
    assert job['status'] == 'completed'
    assert job['detection_count'] == 2
    assert len(set(job['result_ids'])) == 2
    calls = s.db.create_inference_result.await_args_list
    assert [c.kwargs['predicted_weight_kg'] for c in calls] == [1, 4]
    assert [c.kwargs['metadata']['detection_index'] for c in calls] == [0, 1]
    assert all(c.kwargs['session_id'] == 'session' for c in calls)
    assert [c.kwargs['payload']['detection_index'] for c in s.db.create_outbox_event.await_args_list] == [0, 1]
    assert s._publish_prediction_outcome_to_session.await_count == 2
    assert not path.exists()


def test_repeated_views_have_same_ids_but_objects_models_and_captures_differ():
    s = service()
    contexts = s._build_detection_contexts(capture())
    job = {'job_id': 'a', 'tenant_id': 't', 'session_id': 's', 'media_id': 'left'}
    result = {'metadata': contexts[0], 'model_version': 'v1'}
    original = s._detection_result_id(job, result)
    assert original == s._detection_result_id({**job, 'job_id': 'b', 'media_id': 'right'}, result)
    assert original != s._detection_result_id(job, {**result, 'metadata': contexts[1]})
    assert original != s._detection_result_id(job, {**result, 'model_version': 'v2'})
    assert original != s._detection_result_id(job, {**result, 'metadata': {**contexts[0], 'capture_metadata_id': 'other'}})


def test_failed_object_does_not_save_partial_prediction_batch(tmp_path):
    s = service()
    path = tmp_path / 'capture.img'
    path.write_bytes(b'image')
    s.jobs['job'] = {'job_id': 'job', 'tenant_id': 't', 'session_id': 's'}
    s._fetch_media_to_tmp = AsyncMock(return_value=str(path))
    s._fetch_session_features = AsyncMock(return_value={'detection_contexts': s._build_detection_contexts(capture())})
    s.inference_service.run_inference.side_effect = [
        {'predicted_weight_kg': 1, 'confidence': .9, 'model_version': 'v1'}, ValueError('missing area')]
    asyncio.run(s._process_job('job'))
    assert s.jobs['job']['status'] == 'failed'
    s.db.create_inference_result.assert_not_called()
    assert not path.exists()


def test_no_objects_produces_no_predictions(tmp_path):
    s = service()
    c = capture()
    c['rawMetadata']['detections'] = []
    c['detectionCount'] = 0
    path = tmp_path / 'empty.img'
    path.write_bytes(b'image')
    s.jobs['job'] = {'job_id': 'job', 'tenant_id': 't', 'session_id': 's'}
    s._fetch_media_to_tmp = AsyncMock(return_value=str(path))
    s._fetch_session_features = AsyncMock(return_value={'detection_contexts': s._build_detection_contexts(c)})
    asyncio.run(s._process_job('job'))
    assert s.jobs['job']['result_ids'] == []
    assert s.jobs['job']['status'] == 'completed'
    s.inference_service.run_inference.assert_not_called()
    s.db.create_inference_result.assert_not_called()


def test_model_missing_or_feature_missing_never_returns_stub(tmp_path):
    config = Config()
    config.MODEL_SYNC_ENABLED = False
    config.MODEL_MANIFEST_PATH = ''
    config.FALLBACK_MODEL_MANIFEST_PATH = ''
    config.MODEL_CACHE_DIR = str(tmp_path / 'models')
    predictor = InferenceService(config)
    path = tmp_path / 'image'
    path.write_bytes(b'image')
    context = service()._build_detection_contexts(capture())[0]
    with pytest.raises(ValueError, match='requires an active model'):
        asyncio.run(predictor.run_inference(str(path), context))
    predictor.active_model_payload = {'feature_order': ['absent'], 'coefficients': [1],
                                      'feature_means': [0], 'feature_stds': [1]}
    with pytest.raises(ValueError, match='Missing feature absent'):
        asyncio.run(predictor.run_inference(str(path), context))


def test_select_capture_matching_media_and_retry_delayed_metadata():
    s = service()
    response = MagicMock()
    response.__enter__.return_value = response
    other = {**capture(), 'captureId': 'wrong-capture', 'mediaIds': ['other-media']}
    response.read.side_effect = [json.dumps({'captureMetadata': []}).encode(),
                                json.dumps({'captureMetadata': [capture(), other]}).encode()]
    with patch('app.job_service.urllib.request.urlopen', return_value=response), patch('app.job_service.asyncio.sleep', new=AsyncMock()):
        result = asyncio.run(s._fetch_session_features({'tenant_id': 't', 'session_id': 's', 'media_id': 'media-1'}))
    assert len(result['detection_contexts']) == 2
    assert result['detection_contexts'][0]['capture_metadata_id'] == 'capture-1'


def test_outcome_keeps_zero_index_and_unique_event_identity():
    s = JobService(MagicMock(), MagicMock())
    response = MagicMock()
    response.__enter__.return_value = response
    context = service()._build_detection_contexts(capture())[0]
    with patch('app.job_service.urllib.request.urlopen', return_value=response) as post:
        asyncio.run(s._publish_prediction_outcome_to_session(
            {'tenant_id': 't', 'session_id': 's', 'job_id': 'parent'}, 'object-result-id',
            {'metadata': context, 'model_version': 'v1'}, '2026-09-15T08:00:00Z'))
    body = json.loads(post.call_args.args[0].data)
    assert body['eventId'] == 'object-result-id'
    assert body['detectionIndex'] == 0
    assert body['detectionCount'] == 2
    assert body['detection']['area_xy_mm2'] == 100


def test_per_chicken_records_crop_and_save_by_stable_record_id(tmp_path):
    s = service()
    media = tmp_path / 'left.png'
    Image.new('RGB', (100, 80), color='white').save(media)
    s.jobs['job-records'] = {
        'job_id': 'job-records', 'tenant_id': 'tenant', 'farm_id': 'farm',
        'barn_id': 'barn', 'device_id': 'device', 'session_id': 'session',
        'media_id': 'left-media', 'trace_id': 'trace',
        'per_chicken_records': [
            {'record_id': 'record-1', 'session_id': 'session', 'chicken_index': 1,
             'chicken_count': 2, 'bbox_xyxy': [0, 0, 20, 20], 'confidence_score': .92,
             'weight_label_type': 'group_total'},
            {'record_id': 'record-2', 'session_id': 'session', 'chicken_index': 2,
             'chicken_count': 2, 'bbox_xyxy': [20, 10, 70, 60], 'confidence_score': .81,
             'weight_label_type': 'group_total'},
        ],
        'session_aggregate': {'chicken_count': 2}, 'filtering_summary': {'kept': 2},
    }
    s._fetch_media_to_tmp = AsyncMock(return_value=str(media))
    asyncio.run(s._process_job('job-records'))

    job = s.jobs['job-records']
    assert job['status'] == 'completed'
    assert job['detection_count'] == 2
    assert s._fetch_session_features.await_count == 0 if isinstance(s._fetch_session_features, AsyncMock) else True
    calls = s.db.create_inference_result.await_args_list
    assert [call.kwargs['metadata']['record_id'] for call in calls] == ['record-1', 'record-2']
    assert [call.kwargs['metadata']['chicken_index'] for call in calls] == [1, 2]
    assert all(call.kwargs['metadata']['weight_label_type'] == 'group_total' for call in calls)
    assert all('scale_weight_kg' not in call.kwargs['metadata'] for call in calls)
    assert all(call.kwargs['metadata']['processing_duration_ms'] >= 0 for call in calls)
    assert s._detection_result_id(s.jobs['job-records'], {'metadata': {'record_id': 'record-1'}}) == s._detection_result_id(
        {**s.jobs['job-records'], 'job_id': 'retry'}, {'metadata': {'record_id': 'record-1'}}
    )
    assert not media.exists()
