jest.mock('@prisma/client', () => ({ PrismaClient: jest.fn() }))
jest.mock('../../src/utils/uuid', () => ({
  newUuidV7: jest.fn(),
}))

import { PrismaClient } from '@prisma/client'
import { newUuidV7 } from '../../src/utils/uuid'

const prismaMock = PrismaClient as unknown as jest.Mock
const uuidMock = newUuidV7 as jest.Mock
let createBatch: typeof import('../../src/services/batchService').createBatch
let updateBatch: typeof import('../../src/services/batchService').updateBatch

describe('batchService batch-context outbox', () => {
  const transaction = {
    batch: {
      create: jest.fn(),
      findFirst: jest.fn(),
      update: jest.fn(),
    },
    device: { findMany: jest.fn() },
    batchContextOutboxEvent: { create: jest.fn() },
  }

  beforeAll(() => {
    prismaMock.mockImplementation(() => ({
      $transaction: (callback: (tx: typeof transaction) => unknown) => callback(transaction),
    }))
    ;({ createBatch, updateBatch } = require('../../src/services/batchService'))
  })

  beforeEach(() => {
    jest.clearAllMocks()
    uuidMock.mockReset()
    transaction.device.findMany.mockResolvedValue([])
    transaction.batchContextOutboxEvent.create.mockResolvedValue({})
  })

  it('persists a revision-one batch.upsert event with the new batch', async () => {
    uuidMock.mockReturnValueOnce('batch-001').mockReturnValueOnce('event-001')
    transaction.batch.create.mockResolvedValue({
      id: 'batch-001', tenantId: 't-001', farmId: 'f-001', barnId: 'b-001',
      status: 'active', species: 'CHICKEN', breedCode: 'ROSS-308', sex: 'female',
      startDate: new Date('2026-09-01T00:00:00.000Z'), endDate: null,
      contextRevision: 1,
    })

    await createBatch('t-001', 'f-001', 'b-001', {
      species: 'CHICKEN', breedCode: 'ROSS-308', sex: 'female', initialHeadcount: 1000,
      startDate: new Date('2026-09-01T00:00:00.000Z'), status: 'active',
    })

    expect(transaction.batch.create).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.objectContaining({ id: 'batch-001', contextRevision: 1 }),
    }))
    expect(transaction.batchContextOutboxEvent.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        id: 'event-001', batchId: 'batch-001', revision: 1, eventType: 'batch.upsert',
        status: 'pending',
        payload: expect.objectContaining({ eventType: 'batch.upsert', revision: 1, batchId: 'batch-001' }),
      }),
    })
  })

  it('increments revision and emits batch.deactivate on an active-to-inactive update', async () => {
    uuidMock.mockReturnValueOnce('event-002')
    transaction.batch.findFirst.mockResolvedValue({ id: 'batch-001', status: 'active' })
    transaction.batch.update.mockResolvedValue({
      id: 'batch-001', tenantId: 't-001', farmId: 'f-001', barnId: 'b-001',
      status: 'inactive', species: 'CHICKEN', breedCode: null, sex: null,
      startDate: new Date('2026-09-01T00:00:00.000Z'), endDate: null,
      contextRevision: 2,
    })

    const result = await updateBatch('t-001', 'batch-001', { status: 'inactive' })

    expect(result).toEqual({ count: 1 })
    expect(transaction.batch.update).toHaveBeenCalledWith(expect.objectContaining({
      data: expect.objectContaining({ contextRevision: { increment: 1 }, status: 'inactive' }),
    }))
    expect(transaction.batchContextOutboxEvent.create).toHaveBeenCalledWith({
      data: expect.objectContaining({
        eventType: 'batch.deactivate', revision: 2,
        payload: expect.objectContaining({ eventType: 'batch.deactivate', revision: 2 }),
      }),
    })
  })
})
