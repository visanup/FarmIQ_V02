import {
  dispatchBatchContextOutbox,
  isBatchContextOutboxDispatchEnabled,
} from '../../src/services/batchContextOutboxService'

const event = {
  eventId: 'event-001', eventType: 'batch.upsert', revision: 1,
  occurredAt: '2026-09-24T00:00:00.000Z', tenantId: 't-001', farmId: 'f-001', barnId: 'b-001',
  batchId: 'batch-001', status: 'ACTIVE', species: 'CHICKEN', breedCode: 'ROSS-308',
  sex: 'female', startDate: '2026-09-01T00:00:00.000Z', endDate: null, deviceBindings: [],
}

describe('batchContextOutboxService', () => {
  const prisma = {
    batchContextOutboxEvent: {
      findMany: jest.fn(),
      updateMany: jest.fn(),
    },
  }

  beforeEach(() => jest.clearAllMocks())

  it('is disabled unless explicitly enabled', async () => {
    expect(isBatchContextOutboxDispatchEnabled({})).toBe(false)
    await expect(dispatchBatchContextOutbox(prisma as any, jest.fn())).resolves.toEqual({
      enabled: false, dispatched: 0, failed: 0,
    })
    expect(prisma.batchContextOutboxEvent.findMany).not.toHaveBeenCalled()
  })

  it('publishes a pending event and marks it dispatched', async () => {
    prisma.batchContextOutboxEvent.findMany.mockResolvedValue([{ id: 'event-001', batchId: 'batch-001', payload: event }])
    prisma.batchContextOutboxEvent.updateMany.mockResolvedValue({ count: 1 })
    const publish = jest.fn().mockResolvedValue(undefined)

    await expect(dispatchBatchContextOutbox(prisma as any, publish, { enabled: true })).resolves.toEqual({
      enabled: true, dispatched: 1, failed: 0,
    })
    expect(publish).toHaveBeenCalledWith(event)
    expect(prisma.batchContextOutboxEvent.updateMany).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.objectContaining({ status: 'dispatched', attemptCount: { increment: 1 } }),
    }))
  })

  it('records a failed publish for a retry without reporting it as dispatched', async () => {
    prisma.batchContextOutboxEvent.findMany.mockResolvedValue([{ id: 'event-001', batchId: 'batch-001', payload: event }])
    prisma.batchContextOutboxEvent.updateMany.mockResolvedValue({ count: 1 })
    const publish = jest.fn().mockRejectedValue(new Error('control plane unavailable'))

    await expect(dispatchBatchContextOutbox(prisma as any, publish, { enabled: true })).resolves.toEqual({
      enabled: true, dispatched: 0, failed: 1,
    })
    expect(prisma.batchContextOutboxEvent.updateMany).toHaveBeenCalledWith(expect.objectContaining({
      where: { id: 'event-001', status: { in: ['pending', 'failed'] } },
      data: expect.objectContaining({ status: 'failed', lastError: 'control plane unavailable' }),
    }))
  })
})
