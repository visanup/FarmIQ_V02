import type { Request, Response } from 'express'
import { finalizeSession } from '../../src/controllers/sessionController'
import * as sessionService from '../../src/services/sessionService'

jest.mock('../../src/services/sessionService')

describe('sessionController.finalizeSession', () => {
  let req: Partial<Request>
  let res: Partial<Response>

  beforeEach(() => {
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
})
