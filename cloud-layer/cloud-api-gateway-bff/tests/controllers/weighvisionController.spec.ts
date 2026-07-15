import { Request, Response } from 'express'

const mockGetSessions = jest.fn()
const mockGetSessionById = jest.fn()

jest.mock('../../src/services/weighvisionService', () => ({
  createWeighVisionServiceClient: () => ({
    getSessions: mockGetSessions,
    getSessionById: mockGetSessionById,
    getAnalytics: jest.fn(),
    getWeightAggregates: jest.fn(),
    getDatasetContract: jest.fn(),
    bootstrapBaseline: jest.fn(),
    trainBaseline: jest.fn(),
    upsertModelSubscription: jest.fn(),
    getModelSubscription: jest.fn(),
    resolveModelSubscription: jest.fn(),
    ackModelSubscription: jest.fn(),
  }),
}))

import {
  getSessionByIdHandler,
  getSessionsHandler,
} from '../../src/controllers/weighvisionController'

describe('WeighVisionController header propagation', () => {
  let mockReq: Partial<Request>
  let mockRes: Partial<Response>

  beforeEach(() => {
    jest.clearAllMocks()

    mockReq = {
      query: {},
      params: {},
      headers: {
        authorization: 'Bearer token-123',
      } as any,
    }

    mockRes = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
      locals: {
        tenantId: 'tenant-batch5-e2e',
        requestId: 'req-123',
        traceId: 'trace-123',
      },
    }
  })

  it('forwards authorization and trace headers when listing sessions', async () => {
    mockReq.query = { farmId: 'farm-batch5-e2e' }
    mockGetSessions.mockResolvedValue({ items: [], nextCursor: null, hasMore: false })

    await getSessionsHandler(mockReq as Request, mockRes as Response)

    expect(mockGetSessions).toHaveBeenCalledWith({
      tenantId: 'tenant-batch5-e2e',
      farmId: 'farm-batch5-e2e',
      barnId: undefined,
      batchId: undefined,
      stationId: undefined,
      status: undefined,
      from: undefined,
      to: undefined,
      limit: undefined,
      cursor: undefined,
      headers: {
        authorization: 'Bearer token-123',
        'x-request-id': 'req-123',
        'x-trace-id': 'trace-123',
      },
    })
  })

  it('forwards authorization and trace headers when fetching a session by id', async () => {
    mockReq.params = { sessionId: 'session-1' }
    mockGetSessionById.mockResolvedValue({ id: 'session-1' })

    await getSessionByIdHandler(mockReq as Request, mockRes as Response)

    expect(mockGetSessionById).toHaveBeenCalledWith(
      'tenant-batch5-e2e',
      'session-1',
      {
        authorization: 'Bearer token-123',
        'x-request-id': 'req-123',
        'x-trace-id': 'trace-123',
      }
    )
  })
})
