const findMany = jest.fn()
const updateMany = jest.fn()
const executeRawUnsafe = jest.fn()
const transaction = jest.fn()

jest.mock('@prisma/client', () => ({
  PrismaClient: jest.fn(() => ({
    weighVisionSession: { findMany, updateMany },
    $executeRawUnsafe: executeRawUnsafe,
    $transaction: transaction,
  })),
}))

describe('historical association safety contract', () => {
  beforeEach(() => {
    jest.resetModules()
    jest.clearAllMocks()
    transaction.mockImplementation(async (callback: any) => callback({
      weighVisionSession: { findMany, updateMany },
      $executeRawUnsafe: executeRawUnsafe,
    }))
    delete process.env.HISTORICAL_REPROCESS_ENABLED
  })

  const request = {
    tenantId: 't-001', farmId: 'f-001', barnId: 'b-001', batchId: 'batch-new',
    from: new Date('2026-09-01T00:00:00.000Z'), to: new Date('2026-09-02T00:00:00.000Z'),
    requestedBy: 'user-1', reason: 'late batch registration',
  }

  async function service() {
    return require('../../src/services/historicalAssociationService') as typeof import('../../src/services/historicalAssociationService')
  }

  it('previews eligible, already-associated, and conflict sessions without mutation', async () => {
    findMany.mockResolvedValue([
      { id: 'db-1', sessionId: 'session-1', batchId: null },
      { id: 'db-2', sessionId: 'session-2', batchId: 'batch-new' },
      { id: 'db-3', sessionId: 'session-3', batchId: 'another-active-batch' },
    ])
    const { previewHistoricalAssociation } = await service()

    await expect(previewHistoricalAssociation(request)).resolves.toMatchObject({
      dryRun: true,
      counts: { eligible: 1, alreadyAssociated: 1, conflicts: 1 },
      eligibleSessionIds: ['session-1'], conflictSessionIds: ['session-3'],
    })
    expect(updateMany).not.toHaveBeenCalled()
    expect(executeRawUnsafe).not.toHaveBeenCalled()
  })

  it('rejects an inverted interval before querying', async () => {
    const { previewHistoricalAssociation } = await service()
    await expect(previewHistoricalAssociation({ ...request, from: request.to, to: request.from }))
      .rejects.toThrow('from must be before to')
    expect(findMany).not.toHaveBeenCalled()
  })

  it('associates only still-unassigned sessions and records an audit row, without inference writes', async () => {
    findMany
      .mockResolvedValueOnce([{ id: 'db-1', sessionId: 'session-1', batchId: null }])
      .mockResolvedValueOnce([{ id: 'db-1', sessionId: 'session-1', batchId: null }])
    updateMany.mockResolvedValue({ count: 1 })
    const { confirmHistoricalAssociation } = await service()

    await expect(confirmHistoricalAssociation(request)).resolves.toMatchObject({ dryRun: false, associated: 1 })
    expect(updateMany).toHaveBeenCalledWith(expect.objectContaining({ data: { batchId: 'batch-new' } }))
    expect(executeRawUnsafe).toHaveBeenCalledWith(expect.stringContaining('historical_association_audit'), expect.any(String), 't-001', 'db-1', 'session-1', null, 'batch-new', 'user-1', 'late batch registration')
  })

  it('keeps reprocess disabled unless the explicit feature flag is enabled', async () => {
    const { enqueueHistoricalReprocess } = await service()
    await expect(enqueueHistoricalReprocess(request)).rejects.toThrow('HISTORICAL_REPROCESS_DISABLED')
    expect(executeRawUnsafe).not.toHaveBeenCalled()
  })

  it('cancels only a queued job in the request tenant', async () => {
    executeRawUnsafe.mockResolvedValue(1)
    const { cancelHistoricalReprocess } = await service()
    await expect(cancelHistoricalReprocess('t-001', 'job-1')).resolves.toBe(true)
    expect(executeRawUnsafe).toHaveBeenCalledWith(expect.stringContaining('"status"=$1'), 'cancelled', 'job-1', 't-001', 'queued')
  })
})
