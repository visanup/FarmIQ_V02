import {
  buildWeighVisionInferenceSyncEnvelope,
  buildWeighVisionPredictionOutcomeSyncEnvelope,
  normalizeWeighVisionMetadata,
  WEIGHVISION_FEATURE_SCHEMA_VERSION,
  WEIGHVISION_METADATA_MODEL_VERSION,
  WEIGHVISION_METADATA_SCHEMA_NAME,
  WEIGHVISION_METADATA_SCHEMA_VERSION,
} from '../src/utils/weighvisionMetadata'

describe('normalizeWeighVisionMetadata', () => {
  it('builds canonical metadata and normalized features from raw capture payload', () => {
    const result = normalizeWeighVisionMetadata({
      sessionId: 'session-123',
      metadata: {
        image_id: 'capture-001',
        roi_count: 1,
        scale: {
          weight_kg: 1.82,
        },
        detections: [
          {
            confidence: 0.91,
            bbox_xyxy: [10, 20, 110, 220],
            mask_xy: [
              [10, 20],
              [110, 20],
              [110, 220],
              [10, 220],
            ],
            depth_mm: 845.2,
            height_mm: 120.4,
            width_mm: 75.1,
            length_mm: 145.7,
            area_xy_mm2: 9800.5,
          },
        ],
      },
    })

    expect(result.captureId).toBe('capture-001')
    expect(result.metadataSchema).toEqual({
      name: WEIGHVISION_METADATA_SCHEMA_NAME,
      version: WEIGHVISION_METADATA_SCHEMA_VERSION,
    })
    expect(result.featureSchema.version).toBe(
      WEIGHVISION_FEATURE_SCHEMA_VERSION
    )
    expect(WEIGHVISION_METADATA_MODEL_VERSION).toBe('capture-metadata.v1')
    expect(result.normalizedFeatures).toMatchObject({
      capture_id: 'capture-001',
      session_id: 'session-123',
      selected_detection_index: 0,
      detection_count: 1,
      roi_count: 1,
      area_mm2: 9800.5,
      object_height_mm: 120.4,
      object_width_mm: 75.1,
      object_length_mm: 145.7,
      average_depth_mm: 845.2,
      median_depth_mm: 845.2,
      distance_mm: 845.2,
      confidence_score: 0.91,
      scale_weight_kg: 1.82,
    })
    expect(result.normalizedFeatures.bbox).toEqual({
      x1: 10,
      y1: 20,
      x2: 110,
      y2: 220,
    })
    expect(result.normalizedFeatures.mask_area_px2).toBe(20000)
  })

  it('selects the detection with the largest area when multiple detections exist', () => {
    const result = normalizeWeighVisionMetadata({
      sessionId: 'session-456',
      metadata: {
        image_id: 'capture-002',
        detections: [
          {
            confidence: 0.8,
            bbox_xyxy: [0, 0, 10, 10],
            area_xy_mm2: 100,
          },
          {
            confidence: 0.95,
            bbox_xyxy: [0, 0, 20, 20],
            area_xy_mm2: 400,
            depth_mm: 900,
          },
        ],
      },
    })

    expect(result.selectedDetectionIndex).toBe(1)
    expect(result.normalizedFeatures.confidence_score).toBe(0.95)
    expect(result.normalizedFeatures.distance_mm).toBe(900)
  })

  it('builds a cloud sync envelope from canonical metadata', () => {
    const canonical = normalizeWeighVisionMetadata({
      sessionId: 'session-789',
      metadata: {
        image_id: 'capture-789',
        scale: { weight_kg: 2.15 },
        detections: [
          {
            confidence: 0.88,
            bbox_xyxy: [5, 6, 105, 206],
            depth_mm: 812.4,
            height_mm: 131.2,
            width_mm: 81.6,
            length_mm: 151.8,
            area_xy_mm2: 10500.1,
          },
        ],
      },
    })

    const envelope = buildWeighVisionInferenceSyncEnvelope({
      eventId: 'event-789',
      tenantId: 'tenant-1',
      farmId: 'farm-1',
      barnId: 'barn-1',
      deviceId: 'device-1',
      stationId: 'station-1',
      sessionId: 'session-789',
      occurredAt: '2026-07-14T08:00:00Z',
      traceId: 'trace-789',
      mediaIds: ['media-left', 'media-vis'],
      canonical,
    })

    expect(envelope).toMatchObject({
      event_id: 'event-789',
      event_type: 'weighvision.inference.completed',
      tenant_id: 'tenant-1',
      farm_id: 'farm-1',
      barn_id: 'barn-1',
      device_id: 'device-1',
      station_id: 'station-1',
      session_id: 'session-789',
      occurred_at: '2026-07-14T08:00:00Z',
      trace_id: 'trace-789',
      schema_version: '1.0',
      payload: {
        capture_id: 'capture-789',
        session_id: 'session-789',
        media_ids: ['media-left', 'media-vis'],
        metadata_schema: {
          name: WEIGHVISION_METADATA_SCHEMA_NAME,
          version: WEIGHVISION_METADATA_SCHEMA_VERSION,
        },
        feature_schema: {
          version: WEIGHVISION_FEATURE_SCHEMA_VERSION,
        },
        selected_detection_index: 0,
        model_version: WEIGHVISION_METADATA_MODEL_VERSION,
      },
    })
    expect(envelope.payload.normalized_features).toMatchObject({
      area_mm2: 10500.1,
      object_height_mm: 131.2,
      object_width_mm: 81.6,
      object_length_mm: 151.8,
      distance_mm: 812.4,
      confidence_score: 0.88,
      scale_weight_kg: 2.15,
    })
    expect(envelope.payload.metadata).toMatchObject({
      image_id: 'capture-789',
    })
  })

  it('builds a cloud sync envelope from shadow prediction outcome', () => {
    const envelope = buildWeighVisionPredictionOutcomeSyncEnvelope({
      eventId: 'event-pred-001',
      tenantId: 'tenant-1',
      farmId: 'farm-1',
      barnId: 'barn-1',
      deviceId: 'device-1',
      stationId: 'station-1',
      sessionId: 'session-789',
      occurredAt: '2026-07-14T08:01:00Z',
      traceId: 'trace-pred-001',
      inferenceResultId: 'result-001',
      mediaId: 'media-001',
      captureMetadataId: 'cap-001',
      predictedWeightKg: 2.42,
      confidence: 0.81,
      modelVersion: 'wv-shadow-1.0.0',
      packageId: 'pkg-001',
      packageVersion: 'wv-shadow-1.0.0',
      featureSchemaVersion: '1.0',
      activationSource: 'manifest',
      fallbackEngaged: false,
      predictionMode: 'shadow',
      featuresUsed: {
        selected_area_mm2: 12345.6,
      },
    })

    expect(envelope).toMatchObject({
      event_id: 'event-pred-001',
      event_type: 'weighvision.inference.completed',
      tenant_id: 'tenant-1',
      session_id: 'session-789',
      payload: {
        session_id: 'session-789',
        inference_result_id: 'result-001',
        media_id: 'media-001',
        capture_metadata_id: 'cap-001',
        predicted_weight_kg: 2.42,
        confidence: 0.81,
        model_version: 'wv-shadow-1.0.0',
        package_id: 'pkg-001',
        package_version: 'wv-shadow-1.0.0',
        feature_schema_version: '1.0',
        activation_source: 'manifest',
        fallback_engaged: false,
        prediction_mode: 'shadow',
        source_event_type: 'edge.shadow_prediction.completed',
      },
    })
  })
})
