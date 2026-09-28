import { bindDeviceToBatch, getBatchContext } from '../../src/services/batchContextService'

describe('batchContextService', () => {
  it('returns only batches changed after the global revision cursor', async () => {
    const client: any = {
      batchContextOutboxEvent: {
        findFirst: jest.fn().mockResolvedValue({ changeSequence: 7n }),
        findMany: jest.fn().mockResolvedValue([{ batchId: 'batch-2' }]),
      },
      batch: {
        findMany: jest.fn().mockResolvedValue([{
          id: 'batch-2', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', contextRevision: 1,
          status: 'active', species: 'chicken', breedCode: 'ROSS-308', sex: 'female',
          startDate: new Date('2026-09-01T00:00:00Z'), endDate: null, devices: [],
        }]),
      },
    }

    const result = await getBatchContext('t-1', 'f-1', 'b-1', 6, client)

    expect(result).toMatchObject({ mode: 'delta', reset: false, nextRevision: 7 })
    expect(result.contexts).toHaveLength(1)
    expect(client.batchContextOutboxEvent.findMany).toHaveBeenCalledWith(expect.objectContaining({
      where: expect.objectContaining({ changeSequence: { gt: 6n }, tenantId: 't-1' }),
    }))
  })

  it('returns an empty delta when no revision changed', async () => {
    const client: any = {
      batchContextOutboxEvent: {
        findFirst: jest.fn().mockResolvedValue({ changeSequence: 7n }),
        findMany: jest.fn().mockResolvedValue([]),
      },
      batch: { findMany: jest.fn() },
    }
    const result = await getBatchContext('t-1', 'f-1', 'b-1', 7, client)
    expect(result).toEqual({ mode: 'delta', reset: false, nextRevision: 7, contexts: [] })
    expect(client.batch.findMany).not.toHaveBeenCalled()
  })

  it('resets an invalid cursor to a full snapshot rather than serving a stale delta', async () => {
    const client: any = {
      batchContextOutboxEvent: { findFirst: jest.fn().mockResolvedValue({ changeSequence: 7n }), findMany: jest.fn() },
      batch: { findMany: jest.fn().mockResolvedValue([]) },
    }
    await expect(getBatchContext('t-1', 'f-1', 'b-1', 8, client)).resolves.toEqual({
      mode: 'snapshot', reset: true, nextRevision: 7, contexts: [],
    })
    expect(client.batchContextOutboxEvent.findMany).not.toHaveBeenCalled()
  })

  it('rejects a binding when device and batch are in different barns', async () => {
    const tx: any = {
      batch: { findFirst: jest.fn().mockResolvedValue({ id: 'batch-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1' }) },
      device: { findFirst: jest.fn().mockResolvedValue({ id: 'device-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-2' }), update: jest.fn() },
      station: { findFirst: jest.fn() },
    }
    const client: any = { $transaction: (callback: (value: any) => unknown) => callback(tx) }
    await expect(bindDeviceToBatch('t-1', 'batch-1', 'device-1', undefined, client)).resolves.toBeNull()
    expect(tx.device.update).not.toHaveBeenCalled()
  })

  it('increments the Batch revision and appends an outbox event when binding succeeds', async () => {
    const tx: any = {
      batch: {
        findFirst: jest.fn().mockResolvedValue({ id: 'batch-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1' }),
        update: jest.fn().mockResolvedValue({
          id: 'batch-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', contextRevision: 3,
          status: 'active', species: 'chicken', breedCode: 'ROSS-308', sex: 'female', startDate: null, endDate: null,
        }),
      },
      device: {
        findFirst: jest.fn().mockResolvedValue({ id: 'device-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', metadata: {} }),
        update: jest.fn().mockResolvedValue({}),
        findMany: jest.fn().mockResolvedValue([{ id: 'device-1', metadata: {} }]),
      },
      station: { findFirst: jest.fn() },
      batchContextOutboxEvent: { create: jest.fn().mockResolvedValue({}) },
    }
    const client: any = { $transaction: (callback: (value: any) => unknown) => callback(tx) }
    await expect(bindDeviceToBatch('t-1', 'batch-1', 'device-1', undefined, client)).resolves.toMatchObject({ revision: 3 })
    expect(tx.batch.update).toHaveBeenCalledWith(expect.objectContaining({ data: { contextRevision: { increment: 1 } } }))
    expect(tx.batchContextOutboxEvent.create).toHaveBeenCalledWith({ data: expect.objectContaining({
      eventType: 'batch.binding.upsert', revision: 3, status: 'pending',
    }) })
  })

  it('removes a binding and emits a revisioned remove event', async () => {
    const tx: any = {
      device: { findFirst: jest.fn().mockResolvedValue({ id: 'device-1', tenantId: 't-1', batchId: 'batch-1' }), update: jest.fn(), findMany: jest.fn().mockResolvedValue([]) },
      batch: { update: jest.fn().mockResolvedValue({ id: 'batch-1', tenantId: 't-1', farmId: 'f-1', barnId: 'b-1', contextRevision: 4, status: 'active', species: 'chicken', breedCode: 'ROSS-308', sex: 'female', startDate: null, endDate: null }) },
      batchContextOutboxEvent: { create: jest.fn().mockResolvedValue({}) },
    }
    const client: any = { $transaction: (callback: (value: any) => unknown) => callback(tx) }
    const { removeDeviceBinding } = await import('../../src/services/batchContextService')
    await expect(removeDeviceBinding('t-1', 'batch-1', 'device-1', client)).resolves.toBe(true)
    expect(tx.device.update).toHaveBeenCalledWith({ where: { id: 'device-1' }, data: { batchId: null } })
    expect(tx.batchContextOutboxEvent.create).toHaveBeenCalledWith({ data: expect.objectContaining({ eventType: 'batch.binding.remove', revision: 4 }) })
  })
})
