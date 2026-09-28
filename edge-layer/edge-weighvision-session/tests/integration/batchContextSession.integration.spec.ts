import { PrismaClient } from '@prisma/client'

const enabled = process.env.RUN_DB_INTEGRATION === 'true'
const tenantId = 'bces-004-integration'
const sessionId = 'bces-004-session'
const createdEventId = '10000000-0000-4000-8000-000000000004'
const finalizedEventId = '10000000-0000-4000-8000-000000000005'

describe('BCES-004 session binding integration', () => {
  const prisma = new PrismaClient()

  beforeAll(async () => {
    if (!enabled) return
    process.env.BATCH_CONTEXT_AUTO_BIND_ENABLED = 'true'
    ;(global.fetch as jest.Mock) = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: {
        outcome: 'resolved',
        context: {
          batchId: 'batch-e2e', revision: 27, tenantId, farmId: 'farm-e2e', barnId: 'barn-e2e',
          deviceId: 'wv-001', stationId: 'st-01', breedCode: 'ROSS-308', sex: 'female',
        },
      } }),
    })
    await prisma.$executeRawUnsafe('DELETE FROM sync_outbox WHERE session_id=$1', sessionId)
    await prisma.$executeRawUnsafe('DELETE FROM weight_sessions WHERE session_id=$1', sessionId)
  })

  afterAll(async () => {
    if (enabled) {
      await prisma.$executeRawUnsafe('DELETE FROM sync_outbox WHERE session_id=$1', sessionId)
      await prisma.$executeRawUnsafe('DELETE FROM weight_sessions WHERE session_id=$1', sessionId)
    }
    await prisma.$disconnect()
  })

  it('stamps resolved context and sends the same provenance in created/finalized outbox events', async () => {
    if (!enabled) return
    const service = await import('../../src/services/sessionService')
    const created = await service.createSession({
      sessionId,
      eventId: createdEventId,
      tenantId,
      farmId: 'farm-e2e',
      barnId: 'barn-e2e',
      deviceId: 'wv-001',
      stationId: 'st-01',
      startAt: '2026-09-24T00:00:00.000Z',
      traceId: 'trace-bces-004',
    })
    expect(created).toMatchObject({
      batchId: 'batch-e2e', batchContextRevision: 27, batchContextResolution: 'resolved',
    })

    await service.finalizeSession(sessionId, {
      tenantId,
      eventId: finalizedEventId,
      occurredAt: '2026-09-24T00:05:00.000Z',
      traceId: 'trace-bces-004-final',
      finalWeightKg: 2.4,
    })

    const rows = await prisma.$queryRawUnsafe<Array<{ event_type: string; payload_json: Record<string, unknown> }>>(
      'SELECT event_type, payload_json FROM sync_outbox WHERE session_id=$1 ORDER BY occurred_at',
      sessionId
    )
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(row.payload_json).toMatchObject({
        session_id: sessionId,
        batch_id: 'batch-e2e',
        batch_context_revision: 27,
        batch_context_resolution: 'resolved',
      })
    }
  })
})
