from app.api.v1.endpoints import CreateJobRequest


def test_create_job_request_accepts_per_chicken_records_with_camel_case_fields():
    request = CreateJobRequest.model_validate({
        'tenantId': 'tenant', 'farmId': 'farm', 'barnId': 'barn', 'deviceId': 'device',
        'stationId': 'station', 'sessionId': 'session', 'mediaId': 'left-media',
        'perChickenRecords': [{
            'record_id': 'record-1', 'session_id': 'session', 'chicken_index': 1,
            'chicken_count': 5, 'bbox_xyxy': [1, 2, 3, 4],
            'confidence_score': .92, 'mask_path': '/capture-only/mask.png',
            'weight_label_type': 'group_total',
        }],
        'sessionAggregate': {'chicken_count': 5}, 'filteringSummary': {'kept': 5},
    })
    assert request.per_chicken_records[0].record_id == 'record-1'
    assert request.per_chicken_records[0].bbox_xyxy == [1.0, 2.0, 3.0, 4.0]
    assert request.session_aggregate == {'chicken_count': 5}
