jest.mock('../../src/services/tenantRegistryService', () => ({
  tenantRegistryServiceClient: { getBatchContext: jest.fn() },
}))
const mockResolveModelSubscription = jest.fn()
jest.mock('../../src/services/weighvisionService', () => ({
  createWeighVisionServiceClient: jest.fn(() => ({ resolveModelSubscription: mockResolveModelSubscription })),
}))

import { Request, Response } from 'express'
import { tenantRegistryServiceClient } from '../../src/services/tenantRegistryService'
import { getEdgeBatchContextHandler } from '../../src/controllers/edgeBatchContextController'

const registry = tenantRegistryServiceClient as jest.Mocked<typeof tenantRegistryServiceClient>

function response(locals: Record<string, unknown> = {}) {
  const res: any = { locals, status: jest.fn(), json: jest.fn(), end: jest.fn(), setHeader: jest.fn() }
  res.status.mockReturnValue(res)
  res.json.mockReturnValue(res)
  res.end.mockReturnValue(res)
  return res as Response
}

describe('getEdgeBatchContextHandler', () => {
  beforeEach(() => jest.clearAllMocks())

  it('rejects a site outside the credential scope', async () => {
    const req = { query: { siteId: 'site-b' }, headers: {} } as unknown as Request
    const res = response({ tenantId: 't-1', siteId: 'site-a', traceId: 'trace-1' })
    await getEdgeBatchContextHandler(req, res)
    expect(mockResolveModelSubscription).not.toHaveBeenCalled()
    expect(res.status).toHaveBeenCalledWith(403)
    expect(registry.getBatchContext).not.toHaveBeenCalled()
  })

  it('rejects an invalid revision cursor with the standard error envelope', async () => {
    const req = { query: { siteId: 'site-a', sinceRevision: '-1' }, headers: {} } as unknown as Request
    const res = response({ tenantId: 't-1', siteId: 'site-a', traceId: 'trace-1' })
    await getEdgeBatchContextHandler(req, res)
    expect(res.status).toHaveBeenCalledWith(400)
    expect(res.json).toHaveBeenCalledWith({ error: { code: 'VALIDATION_ERROR', message: 'sinceRevision must be a non-negative safe integer', traceId: 'trace-1' } })
  })

  it('aggregates model policy into each batch and returns an ETag', async () => {
    mockResolveModelSubscription.mockResolvedValue({
      tenantId: 't-1', siteId: 'site-a', farmId: 'f-1', barnId: 'b-1', channel: 'stable',
      activePackage: { id: 'pkg-1', version: '1.0.0' }, fallbackPackage: null,
      activationPolicy: { minConfidence: 0.8 }, fallbackPolicy: { order: ['stub_mode'] },
    })
    ;(registry.getBatchContext as jest.Mock).mockResolvedValue({ ok: true, status: 200, data: {
      mode: 'snapshot', reset: false, nextRevision: 4,
      contexts: [{ batchId: 'batch-1', species: 'chicken', breedCode: 'ROSS-308', sex: 'female' }],
    } })
    const req = { query: { siteId: 'site-a', sinceRevision: '0' }, headers: {} } as unknown as Request
    const res = response({ tenantId: 't-1', siteId: 'site-a', traceId: 'trace-1' })
    await getEdgeBatchContextHandler(req, res)
    expect(mockResolveModelSubscription).toHaveBeenCalledWith('site-a', expect.objectContaining({ authorization: 'Bearer t-1' }))
    expect(res.setHeader).toHaveBeenCalledWith('ETag', '"edge-batch-context-t-1-site-a-4-pkg-1"')
    expect(res.json).toHaveBeenCalledWith(expect.objectContaining({
      contexts: [expect.objectContaining({ modelPolicy: expect.objectContaining({ activePackage: { id: 'pkg-1', version: '1.0.0' } }) })],
    }))
  })

  it('returns 304 for an unchanged matching ETag', async () => {
    mockResolveModelSubscription.mockResolvedValue({ tenantId: 't-1', siteId: 'site-a', channel: 'stable', activePackage: { id: 'pkg-1' } })
    ;(registry.getBatchContext as jest.Mock).mockResolvedValue({ ok: true, status: 200, data: { mode: 'delta', reset: false, nextRevision: 4, contexts: [] } })
    const req = { query: { siteId: 'site-a', sinceRevision: '4' }, headers: { 'if-none-match': '"edge-batch-context-t-1-site-a-4-pkg-1"' } } as unknown as Request
    const res = response({ tenantId: 't-1', siteId: 'site-a' })
    await getEdgeBatchContextHandler(req, res)
    expect(res.status).toHaveBeenCalledWith(304)
    expect(res.end).toHaveBeenCalled()
  })

  it('returns an explicit fallback policy when a site has no subscription', async () => {
    mockResolveModelSubscription.mockRejectedValue(new Error('not found'))
    ;(registry.getBatchContext as jest.Mock).mockResolvedValue({ ok: true, status: 200, data: {
      mode: 'snapshot', reset: false, nextRevision: 1, contexts: [],
    } })
    const req = { query: { siteId: 'site-a' }, headers: {} } as unknown as Request
    const res = response({ tenantId: 't-1', siteId: 'site-a', farmId: 'f-1', barnId: 'b-1' })
    await getEdgeBatchContextHandler(req, res)
    expect(res.json).toHaveBeenCalledWith(expect.objectContaining({
      modelPolicy: expect.objectContaining({ fallbackOnly: true, fallbackReason: 'NO_SITE_SUBSCRIPTION' }),
    }))
  })

  it('returns a standard downstream error envelope when the registry cannot load context', async () => {
    mockResolveModelSubscription.mockResolvedValue({ tenantId: 't-1', siteId: 'site-a', farmId: 'f-1', barnId: 'b-1', activePackage: null })
    ;(registry.getBatchContext as jest.Mock).mockResolvedValue({ ok: false, status: 503 })
    const req = { query: { siteId: 'site-a' }, headers: {} } as unknown as Request
    const res = response({ tenantId: 't-1', siteId: 'site-a', traceId: 'trace-1' })
    await getEdgeBatchContextHandler(req, res)
    expect(res.status).toHaveBeenCalledWith(503)
    expect(res.json).toHaveBeenCalledWith({ error: { code: 'SERVICE_UNAVAILABLE', message: 'Unable to load batch context', traceId: 'trace-1' } })
  })
})
