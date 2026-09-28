import { BatchContextOutboxEvent } from '@prisma/client'

import { BatchContextEvent, BatchContextEventSchema } from '../contracts/batchContextEvent'
import { logger } from '../utils/logger'

type BatchContextOutboxClient = {
  batchContextOutboxEvent: {
    findMany: (args: unknown) => Promise<BatchContextOutboxEvent[]>
    updateMany: (args: unknown) => Promise<{ count: number }>
  }
}

export type BatchContextPublisher = (event: BatchContextEvent) => Promise<void>

export interface BatchContextOutboxDispatchResult {
  enabled: boolean
  dispatched: number
  failed: number
}

/**
 * Publishing remains disabled until BCES-002 supplies the authenticated Edge
 * control-plane endpoint.  Events are still persisted so no batch change is
 * lost while the downstream publisher is unavailable.
 */
export function isBatchContextOutboxDispatchEnabled(
  environment: NodeJS.ProcessEnv = process.env,
): boolean {
  return environment.BATCH_CONTEXT_OUTBOX_ENABLED === 'true'
}

export async function dispatchBatchContextOutbox(
  prisma: BatchContextOutboxClient,
  publish: BatchContextPublisher,
  options: { enabled?: boolean; limit?: number } = {},
): Promise<BatchContextOutboxDispatchResult> {
  const enabled = options.enabled ?? isBatchContextOutboxDispatchEnabled()
  if (!enabled) {
    return { enabled: false, dispatched: 0, failed: 0 }
  }

  const events = await prisma.batchContextOutboxEvent.findMany({
    where: { status: { in: ['pending', 'failed'] } },
    orderBy: { createdAt: 'asc' },
    take: options.limit ?? 100,
  })

  let dispatched = 0
  let failed = 0

  for (const storedEvent of events) {
    const attemptedAt = new Date()
    try {
      const event = BatchContextEventSchema.parse(storedEvent.payload)
      await publish(event)

      const update = await prisma.batchContextOutboxEvent.updateMany({
        where: { id: storedEvent.id, status: { in: ['pending', 'failed'] } },
        data: {
          status: 'dispatched',
          attemptCount: { increment: 1 },
          lastAttemptAt: attemptedAt,
          dispatchedAt: attemptedAt,
          lastError: null,
        },
      })
      dispatched += update.count
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      await prisma.batchContextOutboxEvent.updateMany({
        where: { id: storedEvent.id, status: { in: ['pending', 'failed'] } },
        data: {
          status: 'failed',
          attemptCount: { increment: 1 },
          lastAttemptAt: attemptedAt,
          lastError: message,
        },
      })
      failed += 1
      logger.error('Failed to dispatch batch context outbox event', {
        eventId: storedEvent.id,
        batchId: storedEvent.batchId,
        error: message,
      })
    }
  }

  return { enabled: true, dispatched, failed }
}
