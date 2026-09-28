import { PrismaClient } from '@prisma/client'
import { logger } from '../utils/logger'
import { newUuidV7 } from '../utils/uuid'
import {
  BatchContextEvent,
  BatchContextEventSchema,
  BatchContextEventType,
} from '../contracts/batchContextEvent'

const prisma = new PrismaClient()

type BatchMutationData = {
  species?: string
  breedCode?: string | null
  sex?: 'as_hatched' | 'male' | 'female' | null
  initialHeadcount?: number
  startDate?: Date
  endDate?: Date
  status?: string
}

function eventTypeForMutation(previousStatus: string | null, nextStatus: string): BatchContextEventType {
  if (previousStatus !== 'active' && nextStatus === 'active') return 'batch.activate'
  if (previousStatus === 'active' && nextStatus !== 'active') return 'batch.deactivate'
  return 'batch.upsert'
}

function toIso(value: Date | null): string | null {
  return value ? value.toISOString() : null
}

async function buildEvent(
  tx: any,
  batch: any,
  eventType: BatchContextEventType,
  eventId = newUuidV7(),
): Promise<BatchContextEvent> {
  const devices = await tx.device.findMany({
    where: { tenantId: batch.tenantId, batchId: batch.id },
    select: { id: true, metadata: true },
  })

  const deviceBindings = devices.map((device: { id: string; metadata: unknown }) => {
    const metadata = (device.metadata && typeof device.metadata === 'object')
      ? device.metadata as Record<string, unknown>
      : {}
    return {
      deviceId: device.id,
      stationId: typeof metadata.stationId === 'string' ? metadata.stationId : null,
    }
  })

  return BatchContextEventSchema.parse({
    eventId,
    eventType,
    revision: batch.contextRevision,
    occurredAt: new Date().toISOString(),
    tenantId: batch.tenantId,
    farmId: batch.farmId,
    barnId: batch.barnId,
    batchId: batch.id,
    status: batch.status,
    species: batch.species,
    breedCode: batch.breedCode ?? null,
    sex: batch.sex ?? null,
    startDate: toIso(batch.startDate),
    endDate: toIso(batch.endDate),
    deviceBindings,
  })
}

async function writeOutbox(tx: any, event: BatchContextEvent): Promise<void> {
  await tx.batchContextOutboxEvent.create({
    data: {
      id: event.eventId,
      batchId: event.batchId,
      tenantId: event.tenantId,
      farmId: event.farmId,
      barnId: event.barnId,
      eventType: event.eventType,
      revision: event.revision,
      payload: event,
      occurredAt: new Date(event.occurredAt),
      status: 'pending',
    },
  })
}

/**
 * Get all batches for a tenant (optionally filtered by farm/barn)
 */
export async function getBatchesByTenant(
  tenantId: string,
  farmId?: string,
  barnId?: string
) {
  try {
    logger.info(`Fetching batches for tenant ${tenantId}, farm ${farmId || 'all'}, barn ${barnId || 'all'}`)
    return await prisma.batch.findMany({
      where: {
        tenantId,
        ...(farmId && { farmId }),
        ...(barnId && { barnId }),
      },
      include: {
        devices: true,
      },
      orderBy: { createdAt: 'desc' },
    })
  } catch (error) {
    logger.error(`Error fetching batches for tenant ${tenantId}:`, error)
    throw error
  }
}

/**
 * Get batch by ID (with tenant validation)
 */
export async function getBatchById(
  tenantId: string,
  batchId: string
) {
  try {
    logger.info(`Fetching batch ${batchId} for tenant ${tenantId}`)
    return await prisma.batch.findFirst({
      where: {
        id: batchId,
        tenantId,
      },
      include: {
        devices: true,
      },
    })
  } catch (error) {
    logger.error(`Error fetching batch ${batchId}:`, error)
    throw error
  }
}

/**
 * Create a new batch
 */
export async function createBatch(
  tenantId: string,
  farmId: string,
  barnId: string,
  data: {
    species: string
    breedCode?: string
    sex?: 'as_hatched' | 'male' | 'female'
    initialHeadcount?: number
    startDate?: Date
    endDate?: Date
    status?: string
  }
) {
  try {
    logger.info(`Creating batch for tenant ${tenantId}, farm ${farmId}, barn ${barnId}:`, data)
    return await prisma.$transaction(async (tx) => {
      const batch = await tx.batch.create({
        data: {
          id: newUuidV7(),
          tenantId,
          farmId,
          barnId,
          species: data.species,
          breedCode: data.breedCode,
          sex: data.sex,
          initialHeadcount: data.initialHeadcount,
          startDate: data.startDate,
          endDate: data.endDate,
          status: data.status || 'active',
          contextRevision: 1,
        },
      })
      const event = await buildEvent(tx, batch, 'batch.upsert')
      await writeOutbox(tx, event)
      return batch
    })
  } catch (error) {
    logger.error(`Error creating batch for tenant ${tenantId}:`, error)
    throw error
  }
}

/**
 * Update batch
 */
export async function updateBatch(
  tenantId: string,
  batchId: string,
  data: BatchMutationData
) {
  try {
    logger.info(`Updating batch ${batchId} for tenant ${tenantId}:`, data)
    return await prisma.$transaction(async (tx) => {
      const existing = await tx.batch.findFirst({ where: { id: batchId, tenantId } })
      if (!existing) return { count: 0 }

      const nextStatus = data.status ?? existing.status
      const updated = await tx.batch.update({
        where: { id: batchId },
        data: {
          ...data,
          contextRevision: { increment: 1 },
        },
      })
      const event = await buildEvent(
        tx,
        updated,
        eventTypeForMutation(existing.status, nextStatus),
      )
      await writeOutbox(tx, event)
      return { count: 1 }
    })
  } catch (error) {
    logger.error(`Error updating batch ${batchId}:`, error)
    throw error
  }
}

/**
 * Delete batch
 */
export async function deleteBatch(tenantId: string, batchId: string) {
  try {
    logger.info(`Deleting batch ${batchId} for tenant ${tenantId}`)
    return await prisma.batch.deleteMany({
      where: {
        id: batchId,
        tenantId,
      },
    })
  } catch (error) {
    logger.error(`Error deleting batch ${batchId}:`, error)
    throw error
  }
}

