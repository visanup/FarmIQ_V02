import { Request, Response } from 'express'
import { logger } from '../utils/logger'
import * as sessionService from '../services/sessionService'
import { z } from 'zod'
import { WeighVisionSessionAttachRequestSchema } from '@farmiq/edge-contracts'

type RequestWithTrace = Request & { traceId?: string }

function getTraceId(req: Request, res: Response): string {
  return (
    (res.locals.traceId as string | undefined) ||
    (req as RequestWithTrace).traceId ||
    'unknown'
  )
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

// Validation schemas
const createSessionSchema = z.object({
  sessionId: z.string().min(1),
  eventId: z.string().min(1),
  tenantId: z.string().min(1),
  farmId: z.string().min(1),
  barnId: z.string().min(1),
  deviceId: z.string().min(1),
  stationId: z.string().min(1),
  batchId: z.string().min(1).optional(),
  startAt: z.string().datetime(),
})

const bindWeightSchema = z.object({
  tenantId: z.string().min(1),
  weightKg: z.number(),
  occurredAt: z.string().datetime(),
  eventId: z.string().min(1),
})

const bindMediaSchema = z.object({
  tenantId: z.string().min(1),
  mediaObjectId: z.string(),
  occurredAt: z.string().datetime(),
  eventId: z.string().min(1),
})

const finalizeSessionSchema = z.object({
  tenantId: z.string().min(1),
  eventId: z.string().min(1),
  occurredAt: z.string().datetime(),
  finalWeightKg: z.number().finite().optional(),
  payload: z.record(z.unknown()).optional(),
})

const upsertCaptureMetadataSchema = z.object({
  tenantId: z.string().min(1),
  farmId: z.string().min(1),
  barnId: z.string().min(1),
  deviceId: z.string().min(1),
  stationId: z.string().min(1),
  eventId: z.string().min(1),
  occurredAt: z.string().datetime(),
  captureId: z.string().min(1).optional(),
  mediaIds: z.array(z.string().min(1)).optional(),
  metadata: z.record(z.unknown()),
  eventSchemaVersion: z.string().min(1).optional(),
  sourceEventType: z.string().min(1).optional(),
})

const publishInferenceOutcomeSchema = z.object({
  tenantId: z.string().min(1),
  farmId: z.string().min(1).optional(),
  barnId: z.string().min(1).optional(),
  deviceId: z.string().min(1).optional(),
  stationId: z.string().min(1).optional(),
  eventId: z.string().min(1),
  occurredAt: z.string().datetime(),
  inferenceResultId: z.string().min(1).optional(),
  mediaId: z.string().min(1).optional(),
  captureMetadataId: z.string().min(1).optional(),
  predictedWeightKg: z.number().finite().optional(),
  confidence: z.number().finite().optional(),
  modelVersion: z.string().min(1),
  packageId: z.string().min(1).optional(),
  packageVersion: z.string().min(1).optional(),
  featureSchemaVersion: z.string().min(1).optional(),
  activationSource: z.string().min(1).optional(),
  fallbackEngaged: z.boolean().optional(),
  predictionMode: z.string().min(1).optional(),
  featuresUsed: z.record(z.unknown()).optional(),
  eventSchemaVersion: z.string().min(1).optional(),
  sourceEventType: z.string().min(1).optional(),
})

function parseFiniteNumber(value: unknown): number | undefined {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined
  }
  if (typeof value === 'string') {
    const normalized = value.trim()
    if (!normalized) return undefined
    const parsed = Number(normalized)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  return value as Record<string, unknown>
}

function extractFinalWeightFromPayload(
  payload?: Record<string, unknown>
): number | undefined {
  if (!payload) return undefined

  const topLevelCandidate =
    payload['final_weight_kg'] ??
    payload['finalWeightKg'] ??
    payload['weight_kg'] ??
    payload['weightKg'] ??
    payload['scale_weight_kg'] ??
    payload['scaleWeightKg']

  const topLevelWeight = parseFiniteNumber(topLevelCandidate)
  if (topLevelWeight !== undefined) {
    return topLevelWeight
  }

  const scaleRecord = asRecord(payload['scale'])
  if (!scaleRecord) return undefined

  return parseFiniteNumber(
    scaleRecord['weight_kg'] ??
      scaleRecord['weightKg'] ??
      scaleRecord['final_weight_kg'] ??
      scaleRecord['finalWeightKg']
  )
}

export const createSession = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  try {
    const validated = createSessionSchema.parse(req.body)
    const session = await sessionService.createSession({
      ...validated,
      traceId,
    })
    return res.status(201).json(session)
  } catch (error: unknown) {
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: error.errors, traceId },
      })
    }
    logger.error('Failed to create session', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to create session',
        traceId,
      },
    })
  }
}

export const getSession = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const session = await sessionService.getSession(sessionId)
    if (!session) {
      return res.status(404).json({
        error: { code: 'NOT_FOUND', message: 'Session not found', traceId },
      })
    }
    return res.status(200).json(session)
  } catch (error: unknown) {
    logger.error('Failed to get session', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to get session',
        traceId,
      },
    })
  }
}

export const bindWeight = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const validated = bindWeightSchema.parse(req.body)
    const weight = await sessionService.bindWeight(sessionId, {
      ...validated,
      traceId,
    })
    return res.status(200).json(weight)
  } catch (error: unknown) {
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: error.errors, traceId },
      })
    }
    logger.error('Failed to bind weight', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to bind weight',
        traceId,
      },
    })
  }
}

export const bindMedia = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const validated = bindMediaSchema.parse(req.body)
    const binding = await sessionService.bindMedia(sessionId, {
      ...validated,
      traceId,
    })
    return res.status(200).json(binding)
  } catch (error: unknown) {
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: error.errors, traceId },
      })
    }
    logger.error('Failed to bind media', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to bind media',
        traceId,
      },
    })
  }
}

export const finalizeSession = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const validated = finalizeSessionSchema.parse(req.body ?? {})
    const payloadFinalWeight = extractFinalWeightFromPayload(validated.payload)

    const session = await sessionService.finalizeSession(sessionId, {
      ...validated,
      finalWeightKg: parseFiniteNumber(validated.finalWeightKg) ?? payloadFinalWeight,
      traceId,
    })
    return res.status(200).json(session)
  } catch (error: unknown) {
    if (error instanceof Error && error.message === 'Session not found') {
      return res.status(404).json({
        error: { code: 'NOT_FOUND', message: 'Session not found', traceId },
      })
    }
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: error.errors, traceId },
      })
    }
    logger.error('Failed to finalize session', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to finalize session',
        traceId,
      },
    })
  }
}

export const upsertCaptureMetadata = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const validated = upsertCaptureMetadataSchema.parse(req.body ?? {})
    const result = await sessionService.upsertCaptureMetadata(sessionId, {
      ...validated,
      traceId,
    })
    return res.status(200).json(result)
  } catch (error: unknown) {
    if (error instanceof Error && error.message === 'TENANT_MISMATCH') {
      return res.status(403).json({
        error: {
          code: 'TENANT_MISMATCH',
          message: 'tenant mismatch',
          traceId,
        },
      })
    }
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: error.errors, traceId },
      })
    }
    logger.error('Failed to persist capture metadata', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to persist capture metadata',
        traceId,
      },
    })
  }
}

export const getSessionCaptureMetadata = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const metadata = await sessionService.getSessionCaptureMetadata(sessionId)
    return res.status(200).json({
      sessionId,
      items: metadata,
    })
  } catch (error: unknown) {
    logger.error('Failed to get session capture metadata', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to get session capture metadata',
        traceId,
      },
    })
  }
}

export const attach = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const sessionId = req.params.sessionId
  const tenantId = (req.header('x-tenant-id') || '').toString()
  if (!tenantId) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'x-tenant-id is required',
        traceId,
      },
    })
  }

  const parsed = WeighVisionSessionAttachRequestSchema.safeParse(req.body ?? {})
  if (!parsed.success) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: parsed.error.issues,
        traceId,
      },
    })
  }

  try {
    const result = await sessionService.attach(sessionId, {
      tenantId,
      traceId,
      mediaId: parsed.data.media_id,
      inferenceResultId: parsed.data.inference_result_id,
      capturedAt: parsed.data.captured_at,
    })
    return res.status(200).json(result)
  } catch (error: unknown) {
    if (error instanceof Error && error.message === 'Session not found') {
      return res.status(404).json({
        error: { code: 'NOT_FOUND', message: 'Session not found', traceId },
      })
    }
    if (error instanceof Error && error.message === 'TENANT_MISMATCH') {
      return res.status(403).json({
        error: {
          code: 'TENANT_MISMATCH',
          message: 'tenant mismatch',
          traceId,
        },
      })
    }
    logger.error('Failed to attach artifacts', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: { code: 'INTERNAL_ERROR', message: 'Failed to attach', traceId },
    })
  }
}

export const publishInferenceOutcome = async (req: Request, res: Response) => {
  const traceId = getTraceId(req, res)
  const { sessionId } = req.params
  try {
    const validated = publishInferenceOutcomeSchema.parse(req.body ?? {})
    const result = await sessionService.publishInferenceOutcome(sessionId, {
      ...validated,
      traceId,
    })
    return res.status(200).json(result)
  } catch (error: unknown) {
    if (error instanceof Error && error.message === 'Session not found') {
      return res.status(404).json({
        error: { code: 'NOT_FOUND', message: 'Session not found', traceId },
      })
    }
    if (error instanceof Error && error.message === 'TENANT_MISMATCH') {
      return res.status(403).json({
        error: {
          code: 'TENANT_MISMATCH',
          message: 'tenant mismatch',
          traceId,
        },
      })
    }
    if (error instanceof z.ZodError) {
      return res.status(400).json({
        error: { code: 'VALIDATION_ERROR', message: error.errors, traceId },
      })
    }
    logger.error('Failed to publish inference outcome', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to publish inference outcome',
        traceId,
      },
    })
  }
}

export const getHealth = async (req: Request, res: Response) => {
  return res.status(200).json({ status: 'healthy' })
}

export const getReady = async (req: Request, res: Response) => {
  try {
    await sessionService.pingDb()
    return res.status(200).json({ status: 'ready' })
  } catch (error: unknown) {
    const traceId = getTraceId(req, res)
    logger.error('Readiness check failed', {
      error: errorMessage(error),
      traceId,
    })
    return res.status(503).json({ status: 'not_ready' })
  }
}
