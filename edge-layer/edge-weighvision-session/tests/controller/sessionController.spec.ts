import type { Request, Response } from 'express'
import { createSession, finalizeSession } from '../../src/controllers/sessionController'
import * as sessionService from '../../src/services/sessionService'
import { BatchContextAmbiguousError } from '../../src/services/batchContextResolver'

jest.mock('../../src/services/sessionService')

describe('sessionController.finalizeSession', () => {
  let req: Partial<Request>
  let res: Partial<Response>

  beforeEach(() => {
    jest.clearAllMocks()
    req = {
      params: { sessionId: 'sess-001' },
      body: {},
    }
    res = {
      locals: { traceId: 'trace-001' },
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    }
    ;(sessionService.finalizeSession as jest.Mock).mockResolvedValue({
      sessionId: 'sess-001',
      finalWeightKg: 12.34,
    })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('uses nested payload.scale.weight_kg when explicit final weight is absent', async () => {
    req.body = {
      tenantId: 'tenant-001',
      eventId: 'evt-001',
      occurredAt: '2026-07-14T10:00:00.000Z',
      payload: {
        scale: {
          weight_kg: 12.34,
          weight_source: 'instant',
        },
      },
    }

    await finalizeSession(req as Request, res as Response)

    expect(sessionService.finalizeSession).toHaveBeenCalledWith(
      'sess-001',
      expect.objectContaining({
        finalWeightKg: 12.34,
        traceId: 'trace-001',
      })
    )
    expect(res.status).toHaveBeenCalledWith(200)
  })

  it('prefers explicit top-level final weight over nested scale weight', async () => {
    req.body = {
      tenantId: 'tenant-001',
      eventId: 'evt-002',
      occurredAt: '2026-07-14T10:00:00.000Z',
      finalWeightKg: 11.11,
      payload: {
        scale: {
          weight_kg: 12.34,
        },
      },
    }

    await finalizeSession(req as Request, res as Response)

    expect(sessionService.finalizeSession).toHaveBeenCalledWith(
      'sess-001',
      expect.objectContaining({
        finalWeightKg: 11.11,
        traceId: 'trace-001',
      })
    )
    expect(res.status).toHaveBeenCalledWith(200)
  })

  it('rejects batchId from a device caller and does not create a session', async () => {
    req = {
      body: {
        sessionId: 'sess-002', eventId: 'evt-003', tenantId: 't-001', farmId: 'f-001', barnId: 'b-001',
        deviceId: 'wv-001', stationId: 'st-01', batchId: 'batch-manual', startAt: '2026-09-24T00:00:00.000Z',
      },
      header: jest.fn().mockReturnValue(undefined),
    }

    await createSession(req as Request, res as Response)

    expect(res.status).toHaveBeenCalledWith(400)
    expect(res.json).toHaveBeenCalledWith(expect.objectContaining({
      error: expect.objectContaining({ code: 'VALIDATION_ERROR' }),
    }))
    expect(sessionService.createSession).not.toHaveBeenCalled()
  })

  it('generates identifiers and a start time from a scoped device request', async () => {
    ;(sessionService.createSession as jest.Mock).mockResolvedValue({ sessionId: 'generated-session' })
    req = {
      body: {
        tenantId: 't-001', farmId: 'f-001', barnId: 'b-001',
        deviceId: 'wv-001', stationId: 'st-01',
      },
    }

    await createSession(req as Request, res as Response)

    expect(sessionService.createSession).toHaveBeenCalledWith(expect.objectContaining({
      tenantId: 't-001',
      farmId: 'f-001',
      barnId: 'b-001',
      deviceId: 'wv-001',
      stationId: 'st-01',
      sessionId: expect.any(String),
      eventId: expect.any(String),
      startAt: expect.any(String),
    }))
    expect(res.status).toHaveBeenCalledWith(201)
  })

  it('returns a conflict without creating a partial session for ambiguous bindings', async () => {
    ;(sessionService.createSession as jest.Mock).mockRejectedValue(new BatchContextAmbiguousError(['batch-a', 'batch-b']))
    req = {
      body: {
        sessionId: 'sess-004', eventId: 'evt-005', tenantId: 't-001', farmId: 'f-001', barnId: 'b-001',
        deviceId: 'wv-001', stationId: 'st-01', startAt: '2026-09-24T00:00:00.000Z',
      },
    }

    await createSession(req as Request, res as Response)

    expect(res.status).toHaveBeenCalledWith(409)
    expect(res.json).toHaveBeenCalledWith(expect.objectContaining({
      error: expect.objectContaining({ code: 'BATCH_CONTEXT_AMBIGUOUS', candidateBatchIds: ['batch-a', 'batch-b'] }),
    }))
  })
})
