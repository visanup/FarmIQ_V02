export const WEIGHVISION_METADATA_SCHEMA_NAME =
  'farmiq.weighvision.capture-metadata'
export const WEIGHVISION_METADATA_SCHEMA_VERSION = '1.0'
export const WEIGHVISION_FEATURE_SCHEMA_VERSION = '1.0'
export const WEIGHVISION_METADATA_MODEL_VERSION = 'capture-metadata.v1'

type JsonRecord = Record<string, unknown>

export type CanonicalBbox = {
  x1: number | null
  y1: number | null
  x2: number | null
  y2: number | null
}

export type CanonicalNormalizedFeatures = {
  capture_id: string | null
  session_id: string
  selected_detection_index: number | null
  detection_count: number
  roi_count: number | null
  area_mm2: number | null
  mask_area_px2: number | null
  bbox: CanonicalBbox
  object_height_mm: number | null
  object_width_mm: number | null
  object_length_mm: number | null
  average_depth_mm: number | null
  median_depth_mm: number | null
  distance_mm: number | null
  confidence_score: number | null
  scale_weight_kg: number | null
}

export type CanonicalMetadataEnvelope = {
  captureId: string | null
  metadataSchema: {
    name: string
    version: string
  }
  featureSchema: {
    version: string
  }
  normalizedFeatures: CanonicalNormalizedFeatures
  selectedDetectionIndex: number | null
  detectionCount: number
  rawMetadata: JsonRecord
}

export type WeighVisionInferenceSyncEnvelope = {
  event_id: string
  event_type: 'weighvision.inference.completed'
  tenant_id: string
  farm_id: string
  barn_id: string
  device_id: string
  station_id: string
  session_id: string
  occurred_at: string
  trace_id: string
  schema_version: string
  payload: {
    capture_id: string | null
    session_id: string
    media_ids: string[]
    metadata_schema: {
      name: string
      version: string
    }
    feature_schema: {
      version: string
    }
    selected_detection_index: number | null
    normalized_features: CanonicalNormalizedFeatures
    metadata: JsonRecord
    model_version: string
  }
}

export type WeighVisionPredictionOutcomeSyncEnvelope = {
  event_id: string
  event_type: 'weighvision.inference.completed'
  tenant_id: string
  farm_id: string
  barn_id: string
  device_id: string
  station_id: string
  session_id: string
  occurred_at: string
  trace_id: string
  schema_version: string
  payload: {
    session_id: string
    inference_result_id?: string
    media_id?: string
    capture_metadata_id?: string
    predicted_weight_kg?: number
    confidence?: number
    model_version: string
    package_id?: string
    package_version?: string
    feature_schema_version?: string
    activation_source?: string
    fallback_engaged?: boolean
    prediction_mode?: string
    features_used?: Record<string, unknown>
    source_event_type: string
  }
}

function asRecord(value: unknown): JsonRecord | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as JsonRecord
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  if (typeof value === 'string') {
    const normalized = value.trim()
    if (!normalized) return null
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function getString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0
    ? value.trim()
    : null
}

function getNumberFromRecord(
  record: JsonRecord | null,
  ...keys: string[]
): number | null {
  if (!record) return null
  for (const key of keys) {
    const value = toFiniteNumber(record[key])
    if (value !== null) {
      return value
    }
  }
  return null
}

function polygonArea(points: unknown): number | null {
  const polygon = asArray(points)
  if (polygon.length < 3) return null

  const vertices = polygon
    .map((point) => {
      const pair = asArray(point)
      if (pair.length < 2) return null
      const x = toFiniteNumber(pair[0])
      const y = toFiniteNumber(pair[1])
      if (x === null || y === null) return null
      return { x, y }
    })
    .filter((value): value is { x: number; y: number } => value !== null)

  if (vertices.length < 3) return null

  let area = 0
  for (let index = 0; index < vertices.length; index += 1) {
    const current = vertices[index]
    const next = vertices[(index + 1) % vertices.length]
    area += current.x * next.y - next.x * current.y
  }

  return Math.abs(area / 2)
}

function extractBbox(detection: JsonRecord | null): CanonicalBbox {
  const bbox = asArray(detection?.bbox_xyxy)
  return {
    x1: toFiniteNumber(bbox[0]),
    y1: toFiniteNumber(bbox[1]),
    x2: toFiniteNumber(bbox[2]),
    y2: toFiniteNumber(bbox[3]),
  }
}

function pickSelectedDetectionIndex(detections: JsonRecord[]): number | null {
  if (detections.length === 0) return null

  let selectedIndex = 0
  let selectedArea = Number.NEGATIVE_INFINITY
  for (let index = 0; index < detections.length; index += 1) {
    const detection = detections[index]
    const area =
      getNumberFromRecord(detection, 'area_xy_mm2') ??
      getNumberFromRecord(detection, 'mask_area_px2') ??
      polygonArea(detection.mask_xy) ??
      0
    if (area > selectedArea) {
      selectedArea = area
      selectedIndex = index
    }
  }

  return selectedIndex
}

export function normalizeWeighVisionMetadata(params: {
  sessionId: string
  metadata: unknown
  captureId?: string | null
}): CanonicalMetadataEnvelope {
  const rawMetadata = asRecord(params.metadata) ?? {}
  const metadataSchemaRecord = asRecord(rawMetadata.metadata_schema)
  const detections = asArray(rawMetadata.detections)
    .map((entry) => asRecord(entry))
    .filter((entry): entry is JsonRecord => entry !== null)
  const selectedDetectionIndex = pickSelectedDetectionIndex(detections)
  const selectedDetection =
    selectedDetectionIndex !== null ? detections[selectedDetectionIndex] : null
  const scale = asRecord(rawMetadata.scale)

  const captureId =
    getString(params.captureId) ??
    getString(rawMetadata.capture_id) ??
    getString(rawMetadata.image_id)

  const bbox = extractBbox(selectedDetection)
  const averageDepthMm =
    getNumberFromRecord(selectedDetection, 'average_depth_mm') ??
    getNumberFromRecord(asRecord(selectedDetection?.depth_statistics), 'average_mm') ??
    getNumberFromRecord(selectedDetection, 'depth_mm')
  const medianDepthMm =
    getNumberFromRecord(selectedDetection, 'median_depth_mm') ??
    getNumberFromRecord(asRecord(selectedDetection?.depth_statistics), 'median_mm') ??
    getNumberFromRecord(selectedDetection, 'depth_mm')

  const normalizedFeatures: CanonicalNormalizedFeatures = {
    capture_id: captureId,
    session_id: params.sessionId,
    selected_detection_index: selectedDetectionIndex,
    detection_count: detections.length,
    roi_count: getNumberFromRecord(rawMetadata, 'roi_count'),
    area_mm2: getNumberFromRecord(selectedDetection, 'area_xy_mm2'),
    mask_area_px2:
      getNumberFromRecord(selectedDetection, 'mask_area_px2') ??
      polygonArea(selectedDetection?.mask_xy),
    bbox,
    object_height_mm: getNumberFromRecord(selectedDetection, 'height_mm'),
    object_width_mm: getNumberFromRecord(selectedDetection, 'width_mm'),
    object_length_mm: getNumberFromRecord(selectedDetection, 'length_mm'),
    average_depth_mm: averageDepthMm,
    median_depth_mm: medianDepthMm,
    distance_mm:
      getNumberFromRecord(selectedDetection, 'distance_mm') ??
      averageDepthMm ??
      medianDepthMm,
    confidence_score: getNumberFromRecord(selectedDetection, 'confidence'),
    scale_weight_kg: getNumberFromRecord(scale, 'weight_kg'),
  }

  return {
    captureId,
    metadataSchema: {
      name:
        getString(metadataSchemaRecord?.name) ??
        WEIGHVISION_METADATA_SCHEMA_NAME,
      version:
        getString(metadataSchemaRecord?.version) ??
        WEIGHVISION_METADATA_SCHEMA_VERSION,
    },
    featureSchema: {
      version: WEIGHVISION_FEATURE_SCHEMA_VERSION,
    },
    normalizedFeatures,
    selectedDetectionIndex,
    detectionCount: detections.length,
    rawMetadata,
  }
}

export function buildWeighVisionInferenceSyncEnvelope(params: {
  eventId: string
  tenantId: string
  farmId: string
  barnId: string
  deviceId: string
  stationId: string
  sessionId: string
  occurredAt: string
  traceId: string
  schemaVersion?: string
  mediaIds?: string[]
  canonical: CanonicalMetadataEnvelope
}): WeighVisionInferenceSyncEnvelope {
  return {
    event_id: params.eventId,
    event_type: 'weighvision.inference.completed',
    tenant_id: params.tenantId,
    farm_id: params.farmId,
    barn_id: params.barnId,
    device_id: params.deviceId,
    station_id: params.stationId,
    session_id: params.sessionId,
    occurred_at: params.occurredAt,
    trace_id: params.traceId,
    schema_version: params.schemaVersion ?? '1.0',
    payload: {
      capture_id: params.canonical.captureId,
      session_id: params.sessionId,
      media_ids: params.mediaIds ?? [],
      metadata_schema: params.canonical.metadataSchema,
      feature_schema: params.canonical.featureSchema,
      selected_detection_index: params.canonical.selectedDetectionIndex,
      normalized_features: params.canonical.normalizedFeatures,
      metadata: params.canonical.rawMetadata,
      model_version: WEIGHVISION_METADATA_MODEL_VERSION,
    },
  }
}

export function buildWeighVisionPredictionOutcomeSyncEnvelope(params: {
  eventId: string
  tenantId: string
  farmId: string
  barnId: string
  deviceId: string
  stationId: string
  sessionId: string
  occurredAt: string
  traceId: string
  schemaVersion?: string
  inferenceResultId?: string
  mediaId?: string
  captureMetadataId?: string
  predictedWeightKg?: number
  confidence?: number
  modelVersion: string
  packageId?: string
  packageVersion?: string
  featureSchemaVersion?: string
  activationSource?: string
  fallbackEngaged?: boolean
  predictionMode?: string
  featuresUsed?: Record<string, unknown>
  sourceEventType?: string
}): WeighVisionPredictionOutcomeSyncEnvelope {
  return {
    event_id: params.eventId,
    event_type: 'weighvision.inference.completed',
    tenant_id: params.tenantId,
    farm_id: params.farmId,
    barn_id: params.barnId,
    device_id: params.deviceId,
    station_id: params.stationId,
    session_id: params.sessionId,
    occurred_at: params.occurredAt,
    trace_id: params.traceId,
    schema_version: params.schemaVersion ?? '1.0',
    payload: {
      session_id: params.sessionId,
      inference_result_id: params.inferenceResultId,
      media_id: params.mediaId,
      capture_metadata_id: params.captureMetadataId,
      predicted_weight_kg: params.predictedWeightKg,
      confidence: params.confidence,
      model_version: params.modelVersion,
      package_id: params.packageId,
      package_version: params.packageVersion,
      feature_schema_version: params.featureSchemaVersion,
      activation_source: params.activationSource,
      fallback_engaged: params.fallbackEngaged,
      prediction_mode: params.predictionMode,
      features_used: params.featuresUsed,
      source_event_type:
        params.sourceEventType ?? 'edge.shadow_prediction.completed',
    },
  }
}
