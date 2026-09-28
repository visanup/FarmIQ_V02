import { Prisma, PrismaClient } from '@prisma/client'
import { newUuidV7 } from '../utils/uuid'

const prisma = new PrismaClient()
type ContextClient = Pick<PrismaClient, 'batch' | 'batchContextOutboxEvent' | 'device' | 'station' | '$transaction'>

function getStationId(metadata: Prisma.JsonValue | null): string | null {
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return null
  const value = (metadata as Record<string, unknown>).stationId
  return typeof value === 'string' ? value : null
}

function mapBatch(batch: any) {
  return {
    batchId: batch.id, tenantId: batch.tenantId, farmId: batch.farmId, barnId: batch.barnId,
    revision: batch.contextRevision, status: batch.status, species: batch.species,
    breedCode: batch.breedCode, sex: batch.sex, startDate: batch.startDate, endDate: batch.endDate,
    deviceBindings: batch.devices.map((device: any) => ({
      bindingId: device.id, deviceId: device.id, stationId: getStationId(device.metadata),
    })),
  }
}

export async function getBatchContext(
  tenantId: string, farmId?: string, barnId?: string, sinceRevision = 0,
  client: ContextClient = prisma,
) {
  const scope = { tenantId, ...(farmId ? { farmId } : {}), ...(barnId ? { barnId } : {}) }
  const latest = await client.batchContextOutboxEvent.findFirst({
    where: scope, orderBy: { changeSequence: 'desc' }, select: { changeSequence: true },
  })
  const latestRevision = Number(latest?.changeSequence ?? 0n)
  const cursorInvalid = sinceRevision < 0 || sinceRevision > latestRevision
  const fullSnapshot = sinceRevision === 0 || cursorInvalid
  let batchIds: string[] | undefined
  if (!fullSnapshot) {
    const changes = await client.batchContextOutboxEvent.findMany({
      where: { ...scope, changeSequence: { gt: BigInt(sinceRevision) } },
      select: { batchId: true }, distinct: ['batchId'],
    })
    batchIds = changes.map((change) => change.batchId)
  }
  const batches = batchIds?.length === 0 ? [] : await client.batch.findMany({
    where: { ...scope, ...(batchIds ? { id: { in: batchIds } } : {}) },
    include: { devices: { select: { id: true, metadata: true } } },
    orderBy: [{ updatedAt: 'asc' }, { id: 'asc' }],
  })
  return { mode: fullSnapshot ? 'snapshot' : 'delta', reset: cursorInvalid, nextRevision: latestRevision, contexts: batches.map(mapBatch) }
}

async function appendBindingEvent(tx: Prisma.TransactionClient, batch: any, eventType: 'batch.binding.upsert' | 'batch.binding.remove') {
  const devices = await tx.device.findMany({ where: { tenantId: batch.tenantId, batchId: batch.id }, select: { id: true, metadata: true } })
  const eventId = newUuidV7()
  const occurredAt = new Date().toISOString()
  const payload = {
    eventId, eventType, revision: batch.contextRevision, occurredAt,
    tenantId: batch.tenantId, farmId: batch.farmId, barnId: batch.barnId, batchId: batch.id,
    status: batch.status, species: batch.species, breedCode: batch.breedCode, sex: batch.sex,
    startDate: batch.startDate?.toISOString() ?? null, endDate: batch.endDate?.toISOString() ?? null,
    deviceBindings: devices.map((device) => ({ deviceId: device.id, stationId: getStationId(device.metadata) })),
  }
  await tx.batchContextOutboxEvent.create({ data: {
    id: eventId, batchId: batch.id, tenantId: batch.tenantId, farmId: batch.farmId,
    barnId: batch.barnId, eventType, revision: batch.contextRevision, payload,
    occurredAt: new Date(occurredAt), status: 'pending',
  } })
}

export async function bindDeviceToBatch(
  tenantId: string, batchId: string, deviceId: string, requestedStationId?: string,
  client: ContextClient = prisma,
) {
  return client.$transaction(async (tx) => {
    const batch = await tx.batch.findFirst({ where: { id: batchId, tenantId } })
    const device = await tx.device.findFirst({ where: { id: deviceId, tenantId } })
    if (!batch || !device || device.farmId !== batch.farmId || device.barnId !== batch.barnId) return null
    if (requestedStationId && !await tx.station.findFirst({ where: { id: requestedStationId, tenantId, farmId: batch.farmId, barnId: batch.barnId } })) return null
    const metadata = { ...((device.metadata as Record<string, unknown> | null) || {}), ...(requestedStationId ? { stationId: requestedStationId } : {}) }
    await tx.device.update({ where: { id: device.id }, data: { batchId, metadata } })
    const updated = await tx.batch.update({ where: { id: batchId }, data: { contextRevision: { increment: 1 } } })
    await appendBindingEvent(tx, updated, 'batch.binding.upsert')
    return { bindingId: device.id, deviceId: device.id, stationId: requestedStationId || null, revision: updated.contextRevision }
  })
}

export async function removeDeviceBinding(
  tenantId: string, batchId: string, deviceId: string, client: ContextClient = prisma,
) {
  return client.$transaction(async (tx) => {
    const device = await tx.device.findFirst({ where: { id: deviceId, tenantId, batchId } })
    if (!device) return false
    await tx.device.update({ where: { id: device.id }, data: { batchId: null } })
    const updated = await tx.batch.update({ where: { id: batchId }, data: { contextRevision: { increment: 1 } } })
    await appendBindingEvent(tx, updated, 'batch.binding.remove')
    return true
  })
}
