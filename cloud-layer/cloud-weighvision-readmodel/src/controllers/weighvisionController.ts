import { Request, Response } from 'express'
import { getSessions, getSessionById, getAnalytics, listWeightAggregates } from '../services/weighvisionService'
import {
  cancelHistoricalReprocess,
  confirmHistoricalAssociation,
  enqueueHistoricalReprocess,
  previewHistoricalAssociation,
} from '../services/historicalAssociationService'
import { logger } from '../utils/logger'
import { getTenantIdFromRequest } from '../utils/tenantScope'

/**
 * Get weighvision sessions
 */
export async function getSessionsHandler(req: Request, res: Response) {
  try {
    const tenantId = getTenantIdFromRequest(res, req.query.tenantId as string)
    if (!tenantId) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'tenantId is required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const farmId = req.query.farmId as string | undefined
    const barnId = req.query.barnId as string | undefined
    const batchId = req.query.batchId as string | undefined
    const stationId = req.query.stationId as string | undefined
    const status = req.query.status as string | undefined
    const from = req.query.from ? new Date(req.query.from as string) : undefined
    const to = req.query.to ? new Date(req.query.to as string) : undefined
    const limit = req.query.limit ? parseInt(req.query.limit as string, 10) : 100
    const cursor = req.query.cursor as string | undefined

    if (limit > 1000) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'limit cannot exceed 1000',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const result = await getSessions({
      tenantId,
      farmId,
      barnId,
      batchId,
      stationId,
      status,
      from,
      to,
      limit,
      cursor,
    })

    res.json({
      items: result.items,
      nextCursor: result.nextCursor,
      hasMore: result.hasMore,
    })
  } catch (error) {
    logger.error('Error in getSessionsHandler:', error)
    res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to fetch weighvision sessions',
        traceId: res.locals.traceId || 'unknown',
      },
    })
  }
}

function historicalRequest(req: Request, res: Response) {
  const tenantId = getTenantIdFromRequest(res, req.body?.tenantId)
  const { farmId, barnId, batchId, from, to, reason } = req.body || {}
  if (!tenantId || !farmId || !barnId || !batchId || !from || !to || !reason) {
    return null
  }
  const fromDate = new Date(from)
  const toDate = new Date(to)
  if (Number.isNaN(fromDate.getTime()) || Number.isNaN(toDate.getTime())) return null
  return { tenantId, farmId, barnId, batchId, from: fromDate, to: toDate,
    reason: String(reason), requestedBy: typeof req.body.requestedBy === 'string' ? req.body.requestedBy : undefined }
}

export async function previewHistoricalAssociationHandler(req: Request, res: Response) {
  const request = historicalRequest(req, res)
  if (!request) return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId, farmId, barnId, batchId, from, to and reason are required', traceId: res.locals.traceId || 'unknown' } })
  try { return res.json(await previewHistoricalAssociation(request)) }
  catch (error: any) { return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: error.message, traceId: res.locals.traceId || 'unknown' } }) }
}

export async function confirmHistoricalAssociationHandler(req: Request, res: Response) {
  const request = historicalRequest(req, res)
  if (!request) return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId, farmId, barnId, batchId, from, to and reason are required', traceId: res.locals.traceId || 'unknown' } })
  try { return res.json(await confirmHistoricalAssociation(request)) }
  catch (error: any) { return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: error.message, traceId: res.locals.traceId || 'unknown' } }) }
}

export async function enqueueHistoricalReprocessHandler(req: Request, res: Response) {
  const request = historicalRequest(req, res)
  if (!request) return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId, farmId, barnId, batchId, from, to and reason are required', traceId: res.locals.traceId || 'unknown' } })
  try { return res.status(202).json(await enqueueHistoricalReprocess(request)) }
  catch (error: any) {
    const status = error.message === 'HISTORICAL_REPROCESS_DISABLED' ? 409 : 400
    return res.status(status).json({ error: { code: error.message, message: error.message, traceId: res.locals.traceId || 'unknown' } })
  }
}

export async function cancelHistoricalReprocessHandler(req: Request, res: Response) {
  const tenantId = getTenantIdFromRequest(res, req.body?.tenantId)
  if (!tenantId) return res.status(400).json({ error: { code: 'VALIDATION_ERROR', message: 'tenantId is required', traceId: res.locals.traceId || 'unknown' } })
  const cancelled = await cancelHistoricalReprocess(tenantId, req.params.jobId)
  return cancelled ? res.status(204).end() : res.status(404).json({ error: { code: 'NOT_FOUND', message: 'Queued historical job not found', traceId: res.locals.traceId || 'unknown' } })
}

/**
 * Get weighvision session by ID
 */
export async function getSessionByIdHandler(req: Request, res: Response) {
  try {
    const tenantId = getTenantIdFromRequest(res, req.query.tenantId as string)
    if (!tenantId) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'tenantId is required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const sessionId = req.params.sessionId
    if (!sessionId) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'sessionId is required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const session = await getSessionById(tenantId, sessionId)
    if (!session) {
      return res.status(404).json({
        error: {
          code: 'NOT_FOUND',
          message: 'WeighVision session not found',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    res.json(session)
  } catch (error) {
    logger.error('Error in getSessionByIdHandler:', error)
    res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to fetch weighvision session',
        traceId: res.locals.traceId || 'unknown',
      },
    })
  }
}

/**
 * Get weighvision analytics
 */
export async function getAnalyticsHandler(req: Request, res: Response) {
  try {
    const tenantId = getTenantIdFromRequest(res, req.query.tenantId as string)
    if (!tenantId) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'tenantId is required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const farmId = req.query.farm_id as string | undefined
    const barnId = req.query.barn_id as string | undefined
    const batchId = req.query.batch_id as string | undefined
    const startDateStr = req.query.start_date as string
    const endDateStr = req.query.end_date as string
    const aggregation = (req.query.aggregation as 'daily' | 'weekly' | 'monthly') || 'daily'

    if (!startDateStr || !endDateStr) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'start_date and end_date are required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const startDate = new Date(startDateStr)
    const endDate = new Date(endDateStr)

    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid date format. Use ISO 8601 format (YYYY-MM-DD)',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    if (startDate > endDate) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'start_date must be before end_date',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const result = await getAnalytics({
      tenantId,
      farmId,
      barnId,
      batchId,
      startDate,
      endDate,
      aggregation,
    })

    res.json({ data: result })
  } catch (error) {
    logger.error('Error in getAnalyticsHandler:', error)
    res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to fetch weighvision analytics',
        traceId: res.locals.traceId || 'unknown',
      },
    })
  }
}

/**
 * Get weighvision weight aggregates
 */
export async function getWeightAggregatesHandler(req: Request, res: Response) {
  try {
    const tenantId = getTenantIdFromRequest(res, req.query.tenant_id as string || req.query.tenantId as string)
    if (!tenantId) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'tenantId is required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const farmId = req.query.farm_id as string | undefined || req.query.farmId as string | undefined
    const barnId = req.query.barn_id as string | undefined || req.query.barnId as string | undefined
    const batchId = req.query.batch_id as string | undefined || req.query.batchId as string | undefined
    const startDateStr = (req.query.start as string) || (req.query.start_date as string) || (req.query.startDate as string)
    const endDateStr = (req.query.end as string) || (req.query.end_date as string) || (req.query.endDate as string)

    if (!startDateStr || !endDateStr) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'start and end are required',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const startDate = new Date(startDateStr)
    const endDate = new Date(endDateStr)
    if (isNaN(startDate.getTime()) || isNaN(endDate.getTime())) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid date format. Use ISO 8601 format (YYYY-MM-DD)',
          traceId: res.locals.traceId || 'unknown',
        },
      })
    }

    const items = await listWeightAggregates({
      tenantId,
      farmId,
      barnId,
      batchId,
      startDate,
      endDate,
    })

    return res.json({ items })
  } catch (error) {
    logger.error('Error in getWeightAggregatesHandler:', error)
    res.status(500).json({
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Failed to fetch weighvision weight aggregates',
        traceId: res.locals.traceId || 'unknown',
      },
    })
  }
}

