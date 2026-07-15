import { createWeighVisionServiceClient } from '../../src/services/weighvisionService'
import { getServiceBaseUrls } from '../../src/services/dashboardService'

jest.mock('../../src/services/dashboardService', () => ({
  getServiceBaseUrls: jest.fn(),
  callDownstreamJson: jest.fn(),
}))

describe('WeighVisionServiceClient', () => {
  const mockCallDownstreamJson = require('../../src/services/dashboardService').callDownstreamJson

  beforeEach(() => {
    jest.clearAllMocks()
    ;(getServiceBaseUrls as jest.Mock).mockReturnValue({
      weighvisionReadModelBaseUrl: 'http://cloud-weighvision-readmodel:5132',
      mlModelServiceBaseUrl: 'http://cloud-ml-model-service:8000',
    })
  })

  it('propagates headers when listing weighvision sessions', async () => {
    const client = createWeighVisionServiceClient()
    const headers = {
      authorization: 'Bearer token-123',
      'x-request-id': 'req-1',
      'x-trace-id': 'trace-1',
    }

    mockCallDownstreamJson.mockResolvedValue({
      ok: true,
      status: 200,
      data: { items: [], nextCursor: null, hasMore: false },
    })

    await client.getSessions({
      tenantId: 'tenant-batch5-e2e',
      farmId: 'farm-batch5-e2e',
      headers,
    })

    expect(mockCallDownstreamJson).toHaveBeenCalledWith(
      'http://cloud-weighvision-readmodel:5132/api/v1/weighvision/sessions?tenantId=tenant-batch5-e2e&farmId=farm-batch5-e2e',
      {
        method: 'GET',
        headers,
      }
    )
  })

  it('propagates headers when fetching weighvision session by id', async () => {
    const client = createWeighVisionServiceClient()
    const headers = {
      authorization: 'Bearer token-123',
      'x-request-id': 'req-2',
    }

    mockCallDownstreamJson.mockResolvedValue({
      ok: true,
      status: 200,
      data: { id: 'session-1' },
    })

    await client.getSessionById('tenant-batch5-e2e', 'session-1', headers)

    expect(mockCallDownstreamJson).toHaveBeenCalledWith(
      'http://cloud-weighvision-readmodel:5132/api/v1/weighvision/sessions/session-1?tenantId=tenant-batch5-e2e',
      {
        method: 'GET',
        headers,
      }
    )
  })
})
