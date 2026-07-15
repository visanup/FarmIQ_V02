import { PrismaClient } from '@prisma/client'
import { logger } from '../utils/logger'
import {
  buildWeighVisionInferenceSyncEnvelope,
  buildWeighVisionPredictionOutcomeSyncEnvelope,
  normalizeWeighVisionMetadata,
} from '../utils/weighvisionMetadata'
import { ensureWeighVisionSchema } from '../db/ensureSchema'

const prisma = new PrismaClient()
let schemaEnsurePromise: Promise<void> | null = null

type CreateSessionParams = {
  sessionId: string
  eventId: string
  tenantId: string
  farmId: string
  barnId: string
  deviceId: string
  stationId: string
  batchId?: string
  startAt: string
  traceId: string
}

type BindWeightParams = {
  tenantId: string
  weightKg: number
  occurredAt: string
  eventId: string
  traceId: string
}

type BindMediaParams = {
  tenantId: string
  mediaObjectId: string
  occurredAt: string
  eventId: string
  traceId: string
}

type UpsertCaptureMetadataParams = {
  tenantId: string
  farmId: string
  barnId: string
  deviceId: string
  stationId: string
  eventId: string
  traceId: string
  occurredAt: string
  captureId?: string
  mediaIds?: string[]
  metadata: Record<string, unknown>
  eventSchemaVersion?: string
  sourceEventType?: string
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function toJsonString(value: unknown): string {
  return JSON.stringify(value ?? null)
}

function toNullableNumber(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

async function ensureSchemaReady(): Promise<void> {
  if (!schemaEnsurePromise) {
    schemaEnsurePromise = ensureWeighVisionSchema(prisma).catch((error) => {
      schemaEnsurePromise = null
      throw error
    })
  }

  await schemaEnsurePromise
}

export const pingDb = async () => {
  await ensureSchemaReady()
  await prisma.$queryRaw`SELECT 1`
}

export const createSession = async (data: CreateSessionParams) => {
  await ensureSchemaReady()

  const {
    sessionId,
    eventId,
    tenantId,
    farmId,
    barnId,
    deviceId,
    stationId,
    batchId,
    startAt,
    traceId,
  } = data

  const session = await prisma.$transaction(async (tx) => {
    // Idempotent upsert
    const createdOrExisting = await tx.weightSession.upsert({
      where: { sessionId },
      create: {
        sessionId,
        tenantId,
        farmId,
        barnId,
        deviceId,
        stationId,
        batchId,
        status: 'created',
        startAt: new Date(startAt),
      },
      update: {}, // No-op if exists
    })

    // Reconcile pending media bindings
    const unboundMedia = await tx.sessionMediaBinding.findMany({
      where: { sessionId, isBound: false },
    })

    if (unboundMedia.length > 0) {
      await tx.sessionMediaBinding.updateMany({
        where: { id: { in: unboundMedia.map((m) => m.id) } },
        data: { isBound: true },
      })

      await tx.weightSession.update({
        where: { sessionId },
        data: { imageCount: { increment: unboundMedia.length } },
      })

      logger.info(
        `Reconciled ${unboundMedia.length} media bindings for session ${sessionId}`
      )
    }

    // Reconcile pending weight records if any (not strictly required but good for consistency)
    const weights = await tx.sessionWeight.findMany({
      where: { sessionId },
    })

    if (weights.length > 0 && !createdOrExisting.initialWeightKg) {
      const firstWeight = weights.sort(
        (a, b) => a.occurredAt.getTime() - b.occurredAt.getTime()
      )[0]
      await tx.weightSession.update({
        where: { sessionId },
        data: { initialWeightKg: firstWeight.weightKg },
      })
    }

    return createdOrExisting
  })

  // Emit sync_outbox event (idempotent by eventId).
  // Write outside the session transaction so a transient outbox failure does not roll back session persistence.
  try {
    await prisma.$executeRawUnsafe(
      `
      INSERT INTO sync_outbox (
        id, tenant_id, farm_id, barn_id, device_id, session_id,
        event_type, occurred_at, trace_id, payload_json,
        status, next_attempt_at, priority, attempt_count, created_at, updated_at
      ) VALUES (
        $1::uuid, $2::text, $3::text, $4::text, $5::text, $6::text,
        'weighvision.session.created', $7::timestamptz, $8::text, $9::jsonb,
        'pending', NOW(), 0, 0, NOW(), NOW()
      )
      ON CONFLICT (id) DO NOTHING
      `,
      eventId,
      tenantId,
      farmId,
      barnId,
      deviceId,
      sessionId,
      new Date(startAt),
      traceId || null,
      JSON.stringify({
        session_id: sessionId,
        tenant_id: tenantId,
        farm_id: farmId,
        barn_id: barnId,
        device_id: deviceId,
        station_id: stationId,
        batch_id: batchId,
        start_at: startAt,
      })
    )
  } catch (error: unknown) {
    logger.error('Failed to write sync_outbox weighvision.session.created', {
      error: errorMessage(error),
      eventId,
      traceId,
    })
  }

  return session
}

export const getSession = async (sessionId: string) => {
  await ensureSchemaReady()

  const session = await prisma.weightSession.findUnique({
    where: { sessionId },
    include: {
      weights: {
        orderBy: { occurredAt: 'asc' },
      },
    },
  })

  if (!session) {
    return null
  }

  const captureMetadata = await getSessionCaptureMetadata(sessionId)
  return {
    ...session,
    captureMetadata,
  }
}

export const bindWeight = async (sessionId: string, data: BindWeightParams) => {
  await ensureSchemaReady()

  const { tenantId, weightKg, occurredAt, eventId, traceId } = data

  return await prisma.$transaction(async (tx) => {
    // Create weight record (unique by tenantId + eventId handles idempotency)
    const weight = await tx.sessionWeight.upsert({
      where: { tenantId_eventId: { tenantId, eventId } },
      create: {
        sessionId,
        tenantId,
        weightKg,
        occurredAt: new Date(occurredAt),
        eventId,
        traceId,
      },
      update: {},
    })

    // Update initial weight if first
    const session = await tx.weightSession.findUnique({ where: { sessionId } })
    if (session && !session.initialWeightKg) {
      await tx.weightSession.update({
        where: { sessionId },
        data: { initialWeightKg: weightKg },
      })
    }

    return weight
  })
}

export const bindMedia = async (sessionId: string, data: BindMediaParams) => {
  await ensureSchemaReady()

  const { tenantId, mediaObjectId, occurredAt, eventId, traceId } = data

  return await prisma.$transaction(async (tx) => {
    // Create media binding
    const binding = await tx.sessionMediaBinding.upsert({
      where: { tenantId_eventId: { tenantId, eventId } },
      create: {
        sessionId,
        tenantId,
        mediaObjectId,
        occurredAt: new Date(occurredAt),
        eventId,
        traceId,
        isBound: false, // Will be updated if session exists
      },
      update: {},
    })

    // Check if session exists to update imageCount
    const session = await tx.weightSession.findUnique({ where: { sessionId } })
    if (session && !binding.isBound) {
      await tx.sessionMediaBinding.update({
        where: { id: binding.id },
        data: { isBound: true },
      })

      await tx.weightSession.update({
        where: { sessionId },
        data: { imageCount: { increment: 1 } },
      })
    }

    return binding
  })
}

export const finalizeSession = async (
  sessionId: string,
  data: {
    tenantId: string
    eventId: string
    occurredAt: string
    traceId: string
    finalWeightKg?: number
    payload?: Record<string, unknown>
  }
) => {
  await ensureSchemaReady()

  const updatedSession = await prisma.$transaction(async (tx) => {
    const session = await tx.weightSession.findUnique({
      where: { sessionId },
      include: { weights: { orderBy: { occurredAt: 'desc' }, take: 1 } },
    })

    if (!session) throw new Error('Session not found')
    if (session.status === 'finalized') return session

    const finalWeight =
      typeof data.finalWeightKg === 'number'
        ? data.finalWeightKg
        : (session.weights[0]?.weightKg ?? session.initialWeightKg ?? 0)
    const endTime = new Date()

    const updatedSession = await tx.weightSession.update({
      where: { sessionId },
      data: {
        status: 'finalized',
        endAt: endTime,
        finalWeightKg: finalWeight,
      },
    })

    return updatedSession
  })

  // Emit sync_outbox finalized event (idempotent by eventId).
  try {
    await prisma.$executeRawUnsafe(
      `
      INSERT INTO sync_outbox (
        id, tenant_id, farm_id, barn_id, device_id, session_id,
        event_type, occurred_at, trace_id, payload_json,
        status, next_attempt_at, priority, attempt_count, created_at, updated_at
      ) VALUES (
        $1::uuid, $2::text, $3::text, $4::text, $5::text, $6::text,
        'weighvision.session.finalized', $7::timestamptz, $8::text, $9::jsonb,
        'pending', NOW(), 0, 0, NOW(), NOW()
      )
      ON CONFLICT (id) DO NOTHING
      `,
      data.eventId,
      data.tenantId,
      updatedSession.farmId,
      updatedSession.barnId,
      updatedSession.deviceId,
      sessionId,
      new Date(data.occurredAt),
      data.traceId || null,
      JSON.stringify({
        session_id: sessionId,
        tenant_id: data.tenantId,
        farm_id: updatedSession.farmId,
        barn_id: updatedSession.barnId,
        device_id: updatedSession.deviceId,
        final_weight_kg: updatedSession.finalWeightKg,
        image_count: updatedSession.imageCount,
        end_at: updatedSession.endAt?.toISOString(),
        payload: data.payload ?? undefined,
      })
    )
  } catch (error: unknown) {
    logger.error('Failed to write sync_outbox weighvision.session.finalized', {
      error: errorMessage(error),
      eventId: data.eventId,
      traceId: data.traceId,
    })
  }

  return updatedSession
}

export const attach = async (
  sessionId: string,
  params: {
    tenantId: string
    traceId: string
    mediaId?: string
    inferenceResultId?: string
    capturedAt?: string
  }
) => {
  return await prisma.$transaction(async (tx) => {
    const session = await tx.weightSession.findUnique({ where: { sessionId } })
    if (!session) throw new Error('Session not found')
    if (params.tenantId && session.tenantId !== params.tenantId)
      throw new Error('TENANT_MISMATCH')

    let mediaBinding: unknown = null
    if (params.mediaId) {
      const existing = await tx.sessionMediaBinding.findFirst({
        where: { sessionId, mediaObjectId: params.mediaId },
      })

      mediaBinding = await tx.sessionMediaBinding.upsert({
        where: {
          sessionId_mediaObjectId: { sessionId, mediaObjectId: params.mediaId },
        },
        create: {
          sessionId,
          tenantId: session.tenantId,
          mediaObjectId: params.mediaId,
          occurredAt: params.capturedAt
            ? new Date(params.capturedAt)
            : new Date(),
          eventId: `attach-${session.tenantId}-${params.mediaId}`,
          traceId: params.traceId,
          isBound: true,
        },
        update: { isBound: true },
      })

      if (!existing) {
        await tx.weightSession.update({
          where: { sessionId },
          data: { imageCount: { increment: 1 } },
        })
      }
    }

    let updatedSession = session
    if (params.inferenceResultId) {
      updatedSession = await tx.weightSession.update({
        where: { sessionId },
        data: { inferenceResultId: params.inferenceResultId },
      })
    }

    return {
      session: updatedSession,
      media_binding: mediaBinding,
    }
  })
}

export const upsertCaptureMetadata = async (
  sessionId: string,
  data: UpsertCaptureMetadataParams
) => {
  await ensureSchemaReady()

  const existingSession = await prisma.weightSession.findUnique({
    where: { sessionId },
  })

  if (existingSession && existingSession.tenantId !== data.tenantId) {
    throw new Error('TENANT_MISMATCH')
  }

  const canonical = normalizeWeighVisionMetadata({
    sessionId,
    metadata: data.metadata,
    captureId: data.captureId,
  })

  await prisma.$executeRawUnsafe(
    `
    INSERT INTO session_capture_metadata (
      id, session_id, tenant_id, capture_id, event_id, trace_id, source_event_type,
      metadata_schema_version, feature_schema_version, occurred_at, media_ids,
      raw_metadata, normalized_features, selected_detection_index, detection_count, roi_count,
      area_mm2, mask_area_px2, bbox_x1, bbox_y1, bbox_x2, bbox_y2,
      object_height_mm, object_width_mm, object_length_mm,
      average_depth_mm, median_depth_mm, distance_mm, confidence_score, scale_weight_kg,
      created_at, updated_at
    ) VALUES (
      gen_random_uuid(), $1::text, $2::text, $3::text, $4::text, $5::text, $6::text,
      $7::text, $8::text, $9::timestamptz, $10::jsonb,
      $11::jsonb, $12::jsonb, $13::integer, $14::integer, $15::integer,
      $16::numeric, $17::numeric, $18::integer, $19::integer, $20::integer, $21::integer,
      $22::numeric, $23::numeric, $24::numeric,
      $25::numeric, $26::numeric, $27::numeric, $28::numeric, $29::numeric,
      NOW(), NOW()
    )
    ON CONFLICT (tenant_id, event_id) DO UPDATE SET
      capture_id = EXCLUDED.capture_id,
      trace_id = EXCLUDED.trace_id,
      source_event_type = EXCLUDED.source_event_type,
      metadata_schema_version = EXCLUDED.metadata_schema_version,
      feature_schema_version = EXCLUDED.feature_schema_version,
      occurred_at = EXCLUDED.occurred_at,
      media_ids = EXCLUDED.media_ids,
      raw_metadata = EXCLUDED.raw_metadata,
      normalized_features = EXCLUDED.normalized_features,
      selected_detection_index = EXCLUDED.selected_detection_index,
      detection_count = EXCLUDED.detection_count,
      roi_count = EXCLUDED.roi_count,
      area_mm2 = EXCLUDED.area_mm2,
      mask_area_px2 = EXCLUDED.mask_area_px2,
      bbox_x1 = EXCLUDED.bbox_x1,
      bbox_y1 = EXCLUDED.bbox_y1,
      bbox_x2 = EXCLUDED.bbox_x2,
      bbox_y2 = EXCLUDED.bbox_y2,
      object_height_mm = EXCLUDED.object_height_mm,
      object_width_mm = EXCLUDED.object_width_mm,
      object_length_mm = EXCLUDED.object_length_mm,
      average_depth_mm = EXCLUDED.average_depth_mm,
      median_depth_mm = EXCLUDED.median_depth_mm,
      distance_mm = EXCLUDED.distance_mm,
      confidence_score = EXCLUDED.confidence_score,
      scale_weight_kg = EXCLUDED.scale_weight_kg,
      updated_at = NOW()
    `,
    sessionId,
    data.tenantId,
    canonical.captureId,
    data.eventId,
    data.traceId,
    data.sourceEventType ?? 'weighvision.inference.completed',
    canonical.metadataSchema.version,
    canonical.featureSchema.version,
    new Date(data.occurredAt),
    toJsonString(data.mediaIds ?? []),
    toJsonString(canonical.rawMetadata),
    toJsonString(canonical.normalizedFeatures),
    canonical.selectedDetectionIndex,
    canonical.detectionCount,
    canonical.normalizedFeatures.roi_count,
    toNullableNumber(canonical.normalizedFeatures.area_mm2),
    toNullableNumber(canonical.normalizedFeatures.mask_area_px2),
    canonical.normalizedFeatures.bbox.x1,
    canonical.normalizedFeatures.bbox.y1,
    canonical.normalizedFeatures.bbox.x2,
    canonical.normalizedFeatures.bbox.y2,
    toNullableNumber(canonical.normalizedFeatures.object_height_mm),
    toNullableNumber(canonical.normalizedFeatures.object_width_mm),
    toNullableNumber(canonical.normalizedFeatures.object_length_mm),
    toNullableNumber(canonical.normalizedFeatures.average_depth_mm),
    toNullableNumber(canonical.normalizedFeatures.median_depth_mm),
    toNullableNumber(canonical.normalizedFeatures.distance_mm),
    toNullableNumber(canonical.normalizedFeatures.confidence_score),
    toNullableNumber(canonical.normalizedFeatures.scale_weight_kg)
  )

  const syncEnvelope = buildWeighVisionInferenceSyncEnvelope({
    eventId: data.eventId,
    tenantId: data.tenantId,
    farmId: existingSession?.farmId ?? data.farmId,
    barnId: existingSession?.barnId ?? data.barnId,
    deviceId: existingSession?.deviceId ?? data.deviceId,
    stationId: existingSession?.stationId ?? data.stationId,
    sessionId,
    occurredAt: data.occurredAt,
    traceId: data.traceId,
    schemaVersion: data.eventSchemaVersion,
    mediaIds: data.mediaIds ?? [],
    canonical,
  })

  try {
    await prisma.$executeRawUnsafe(
      `
      INSERT INTO sync_outbox (
        id, tenant_id, farm_id, barn_id, device_id, session_id,
        event_type, occurred_at, trace_id, payload_json,
        status, next_attempt_at, priority, attempt_count, created_at, updated_at
      ) VALUES (
        $1::uuid, $2::text, $3::text, $4::text, $5::text, $6::text,
        'weighvision.inference.completed', $7::timestamptz, $8::text, $9::jsonb,
        'pending', NOW(), 0, 0, NOW(), NOW()
      )
      ON CONFLICT (id) DO NOTHING
      `,
      data.eventId,
      data.tenantId,
      existingSession?.farmId ?? data.farmId,
      existingSession?.barnId ?? data.barnId,
      existingSession?.deviceId ?? data.deviceId,
      sessionId,
      new Date(data.occurredAt),
      data.traceId || null,
      JSON.stringify(syncEnvelope)
    )
  } catch (error: unknown) {
    logger.error('Failed to write sync_outbox weighvision.inference.completed', {
      error: errorMessage(error),
      eventId: data.eventId,
      traceId: data.traceId,
    })
  }

  return {
    sessionId,
    captureId: canonical.captureId,
    metadataSchema: canonical.metadataSchema,
    featureSchema: canonical.featureSchema,
    normalizedFeatures: canonical.normalizedFeatures,
  }
}

export const getSessionCaptureMetadata = async (sessionId: string) => {
  await ensureSchemaReady()

  const rows = (await prisma.$queryRawUnsafe(
    `
    SELECT
      session_id,
      tenant_id,
      capture_id,
      event_id,
      trace_id,
      source_event_type,
      metadata_schema_version,
      feature_schema_version,
      occurred_at,
      media_ids,
      raw_metadata,
      normalized_features,
      selected_detection_index,
      detection_count,
      roi_count,
      area_mm2,
      mask_area_px2,
      bbox_x1,
      bbox_y1,
      bbox_x2,
      bbox_y2,
      object_height_mm,
      object_width_mm,
      object_length_mm,
      average_depth_mm,
      median_depth_mm,
      distance_mm,
      confidence_score,
      scale_weight_kg,
      created_at,
      updated_at
    FROM session_capture_metadata
    WHERE session_id = $1
    ORDER BY occurred_at ASC, created_at ASC
    `,
    sessionId
  )) as Array<Record<string, unknown>>

  return rows.map((row) => ({
    sessionId: row.session_id,
    tenantId: row.tenant_id,
    captureId: row.capture_id,
    eventId: row.event_id,
    traceId: row.trace_id,
    sourceEventType: row.source_event_type,
    metadataSchemaVersion: row.metadata_schema_version,
    featureSchemaVersion: row.feature_schema_version,
    occurredAt:
      row.occurred_at instanceof Date
        ? row.occurred_at.toISOString()
        : row.occurred_at,
    mediaIds: row.media_ids,
    rawMetadata: row.raw_metadata,
    normalizedFeatures: row.normalized_features,
    selectedDetectionIndex: row.selected_detection_index,
    detectionCount: row.detection_count,
    roiCount: row.roi_count,
    areaMm2: row.area_mm2,
    maskAreaPx2: row.mask_area_px2,
    bbox: {
      x1: row.bbox_x1,
      y1: row.bbox_y1,
      x2: row.bbox_x2,
      y2: row.bbox_y2,
    },
    objectHeightMm: row.object_height_mm,
    objectWidthMm: row.object_width_mm,
    objectLengthMm: row.object_length_mm,
    averageDepthMm: row.average_depth_mm,
    medianDepthMm: row.median_depth_mm,
    distanceMm: row.distance_mm,
    confidenceScore: row.confidence_score,
    scaleWeightKg: row.scale_weight_kg,
    createdAt:
      row.created_at instanceof Date
        ? row.created_at.toISOString()
        : row.created_at,
    updatedAt:
      row.updated_at instanceof Date
        ? row.updated_at.toISOString()
        : row.updated_at,
  }))
}

export const publishInferenceOutcome = async (
  sessionId: string,
  data: {
    tenantId: string
    farmId?: string
    barnId?: string
    deviceId?: string
    stationId?: string
    eventId: string
    occurredAt: string
    traceId: string
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
    eventSchemaVersion?: string
    sourceEventType?: string
  }
) => {
  await ensureSchemaReady()

  const session = await prisma.weightSession.findUnique({
    where: { sessionId },
  })

  if (!session) throw new Error('Session not found')
  if (session.tenantId !== data.tenantId) throw new Error('TENANT_MISMATCH')

  if (data.inferenceResultId) {
    await prisma.weightSession.update({
      where: { sessionId },
      data: { inferenceResultId: data.inferenceResultId },
    })
  }

  const syncEnvelope = buildWeighVisionPredictionOutcomeSyncEnvelope({
    eventId: data.eventId,
    tenantId: data.tenantId,
    farmId: session.farmId ?? data.farmId ?? '',
    barnId: session.barnId ?? data.barnId ?? '',
    deviceId: session.deviceId ?? data.deviceId ?? '',
    stationId: session.stationId ?? data.stationId ?? '',
    sessionId,
    occurredAt: data.occurredAt,
    traceId: data.traceId,
    schemaVersion: data.eventSchemaVersion,
    inferenceResultId: data.inferenceResultId,
    mediaId: data.mediaId,
    captureMetadataId: data.captureMetadataId,
    predictedWeightKg: data.predictedWeightKg,
    confidence: data.confidence,
    modelVersion: data.modelVersion,
    packageId: data.packageId,
    packageVersion: data.packageVersion,
    featureSchemaVersion: data.featureSchemaVersion,
    activationSource: data.activationSource,
    fallbackEngaged: data.fallbackEngaged,
    predictionMode: data.predictionMode,
    featuresUsed: data.featuresUsed,
    sourceEventType: data.sourceEventType,
  })

  await prisma.$executeRawUnsafe(
    `
    INSERT INTO sync_outbox (
      id, tenant_id, farm_id, barn_id, device_id, session_id,
      event_type, occurred_at, trace_id, payload_json,
      status, next_attempt_at, priority, attempt_count, created_at, updated_at
    ) VALUES (
      $1::uuid, $2::text, $3::text, $4::text, $5::text, $6::text,
      'weighvision.inference.completed', $7::timestamptz, $8::text, $9::jsonb,
      'pending', NOW(), 0, 0, NOW(), NOW()
    )
    ON CONFLICT (id) DO NOTHING
    `,
    data.eventId,
    data.tenantId,
    session.farmId ?? data.farmId ?? null,
    session.barnId ?? data.barnId ?? null,
    session.deviceId ?? data.deviceId ?? null,
    sessionId,
    new Date(data.occurredAt),
    data.traceId || null,
    JSON.stringify(syncEnvelope)
  )

  return {
    sessionId,
    eventId: data.eventId,
    inferenceResultId: data.inferenceResultId,
    modelVersion: data.modelVersion,
    predictionMode: data.predictionMode ?? null,
    published: true,
  }
}
