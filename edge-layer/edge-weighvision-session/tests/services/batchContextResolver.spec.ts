import { BatchContextAmbiguousError, resolveBatchContext } from '../../src/services/batchContextResolver'

const originalEnv = process.env

describe('batchContextResolver', () => {
  beforeEach(() => {
    process.env = { ...originalEnv, BATCH_CONTEXT_AUTO_BIND_ENABLED: 'true', BATCH_CONTEXT_RESOLVER_URL: 'http://policy-sync.test/api/v1/edge-config' }
    global.fetch = jest.fn()
  })

  afterEach(() => {
    process.env = originalEnv
    jest.restoreAllMocks()
  })

  it('returns the active cached Batch context for a device/station', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: {
        outcome: 'resolved',
        context: { batchId: 'batch-001', revision: 12, breedCode: 'ROSS-308' },
      } }),
    })

    await expect(resolveBatchContext({ tenantId: 't-001', deviceId: 'wv-001', stationId: 'st-01' }))
      .resolves.toMatchObject({ batchId: 'batch-001', revision: 12, resolution: 'resolved' })
    expect(global.fetch).toHaveBeenCalledWith(
      'http://policy-sync.test/api/v1/edge-config/batch-context/t-001/wv-001/st-01',
      expect.any(Object)
    )
  })

  it('returns unassigned for a missing or stale context', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: { outcome: 'stale', reason: 'CACHE_EXPIRED' } }),
    })

    await expect(resolveBatchContext({ tenantId: 't-001', deviceId: 'wv-001', stationId: 'st-01' }))
      .resolves.toMatchObject({ batchId: null, resolution: 'unassigned', reason: 'CACHE_EXPIRED' })
  })

  it('rejects an ambiguous binding without choosing a Batch', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ data: { outcome: 'ambiguous', candidateBatchIds: ['batch-a', 'batch-b'] } }),
    })

    await expect(resolveBatchContext({ tenantId: 't-001', deviceId: 'wv-001', stationId: 'st-01' }))
      .rejects.toEqual(new BatchContextAmbiguousError(['batch-a', 'batch-b']))
  })

  it('does not call the resolver when auto binding is disabled', async () => {
    process.env.BATCH_CONTEXT_AUTO_BIND_ENABLED = 'false'
    await expect(resolveBatchContext({ tenantId: 't-001', deviceId: 'wv-001', stationId: 'st-01' }))
      .resolves.toMatchObject({ resolution: 'unassigned', reason: 'AUTO_BIND_DISABLED' })
    expect(global.fetch).not.toHaveBeenCalled()
  })
})
