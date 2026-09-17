import asyncio
from unittest.mock import AsyncMock
import pytest
from app.config import Config
from app.inference_service import InferenceService


def make_service(tmp_path):
    config = Config()
    config.SIMULATED_MODEL_ENABLED = True
    config.MODEL_MANIFEST_PATH = ''
    config.FALLBACK_MODEL_MANIFEST_PATH = ''
    config.MODEL_CACHE_DIR = str(tmp_path / 'models')
    service = InferenceService(config)
    service.ensure_subscription_activation = AsyncMock()
    image = tmp_path / 'image.jpg'
    image.write_bytes(b'only area determines the simulated weight')
    return service, str(image)


def test_simulation_runs_per_object_without_active_model(tmp_path):
    service, image = make_service(tmp_path)
    results = [asyncio.run(service.run_inference(image, {
        'require_model': True, 'detection_index': index, 'detection_count': 2,
        'features': {'selected_area_mm2': area},
    })) for index, area in enumerate([5000, 20000])]
    assert [r['predicted_weight_kg'] for r in results] == [0.5, 2.0]
    assert [r['metadata']['detection_index'] for r in results] == [0, 1]
    assert all(r['confidence'] == 0 and r['metadata']['simulated'] for r in results)
    assert all(r['model_version'] == 'simulated-geometry-v1' for r in results)
    assert all(r['metadata']['prediction_mode'] == 'simulated_per_object' for r in results)
    service.ensure_subscription_activation.assert_not_called()
    assert service.get_model_info()['status'] == 'simulated'


def test_same_object_same_weight_across_image_sizes(tmp_path):
    service, image = make_service(tmp_path)
    context = {'features': {'selected_area_mm2': 12345}, 'require_model': True}
    first = asyncio.run(service.run_inference(image, context))
    (tmp_path / 'image.jpg').write_bytes(b'x' * 10000)
    second = asyncio.run(service.run_inference(image, context))
    assert first['predicted_weight_kg'] == second['predicted_weight_kg']


def test_bbox_fallback_is_labelled(tmp_path):
    service, image = make_service(tmp_path)
    result = asyncio.run(service.run_inference(image, {'detection': {'bbox_xyxy': [0, 0, 100, 200]}}))
    assert result['predicted_weight_kg'] == 2.0
    assert result['metadata']['features_used'] == {'bbox_area_px2': 20000}


def test_simulation_can_be_disabled(tmp_path):
    service, image = make_service(tmp_path)
    service.config.SIMULATED_MODEL_ENABLED = False
    with pytest.raises(ValueError, match='requires an active model'):
        asyncio.run(service.run_inference(image, {'require_model': True, 'features': {'selected_area_mm2': 100}}))


@pytest.mark.parametrize('bbox', [None, [1, 1, 0, 0], [0, 0, float('inf'), 100]])
def test_missing_or_invalid_geometry_does_not_invent_a_result(tmp_path, bbox):
    service, image = make_service(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(service.run_inference(image, {'detection': {'bbox_xyxy': bbox}}))
