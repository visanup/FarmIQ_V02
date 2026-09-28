import { PrismaClient } from '@prisma/client'
import { logger } from '../utils/logger'

const prisma = new PrismaClient()
const edgeInferenceBaseUrl = () => process.env.EDGE_VISION_INFERENCE_BASE_URL || ''
const batchContextBffBaseUrl = () => process.env.BATCH_CONTEXT_BFF_BASE_URL || ''

type HistoricalJob = {
  id: string; tenantId: string; batchId: string; from: Date; to: Date
}

function enabled() {
  return process.env.HISTORICAL_REPROCESS_ENABLED === 'true' && Boolean(edgeInferenceBaseUrl())
}

/**
 * Dispatches durable Cloud requests to the Edge-only historical queue. This
 * process does not run a model and it never uses the realtime endpoint type.
 * Edge owns concurrency/pause/cancel semantics; Cloud owns audit and lineage.
 */
export async function drainHistoricalReprocessQueue(): Promise<void> {
  if (!enabled()) return
  const jobs = await prisma.$queryRawUnsafe<HistoricalJob[]>(
    'SELECT "id","tenantId","batchId","from","to" FROM "weighvision_historical_reprocess_job" WHERE "status"=$1 ORDER BY "requestedAt" ASC LIMIT 1',
    'queued',
  )
  for (const job of jobs) await dispatch(job)
}

async function dispatch(job: HistoricalJob): Promise<void> {
  const claimed = await prisma.$executeRawUnsafe(
    'UPDATE "weighvision_historical_reprocess_job" SET "status"=$1,"startedAt"=NOW(),"pauseReason"=NULL WHERE "id"=$2 AND "status"=$3',
    'dispatching', job.id, 'queued',
  )
  if (Number(claimed) !== 1) return

  try {
    const contextResponse = await fetch(`${batchContextBffBaseUrl()}/api/v1/batches/${encodeURIComponent(job.batchId)}?tenantId=${encodeURIComponent(job.tenantId)}`, { headers: { 'x-tenant-id': job.tenantId } })
    if (!contextResponse.ok) throw new Error(`Batch context lookup failed: ${contextResponse.status}`)
    const batch = await contextResponse.json() as Record<string, unknown>
    const historicalContext = {
      tenantId: batch.tenantId, farmId: batch.farmId, barnId: batch.barnId, batchId: batch.id,
      species: batch.species, breedCode: batch.breedCode, sex: batch.sex, startDate: batch.startDate,
      revision: batch.contextRevision, modelPolicy: { fallbackOnly: true, fallbackReason: 'NO_SITE_SUBSCRIPTION' },
    }
    const sessions = await prisma.weighVisionSession.findMany({
      where: { tenantId: job.tenantId, batchId: job.batchId, startedAt: { gte: job.from, lte: job.to } },
      include: { media: { orderBy: { ts: 'desc' }, take: 1 }, inferences: { orderBy: { ts: 'desc' }, take: 1 } },
    })
    let submitted = 0
    let skipped = 0
    for (const session of sessions) {
      const media = session.media[0]
      if (!media) { skipped += 1; continue } // retention preflight: never submit absent media
      const response = await fetch(`${edgeInferenceBaseUrl()}/api/v1/inference/jobs`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-tenant-id': job.tenantId },
        body: JSON.stringify({
          tenantId: job.tenantId, farmId: session.farmId, barnId: session.barnId,
          deviceId: '', stationId: session.stationId, sessionId: session.sessionId,
          mediaId: media.objectId, objectKey: media.path, jobType: 'historical-reprocess',
          historicalJobId: job.id, revisionOf: session.inferences[0]?.id || null,
          historicalContext,
        }),
      })
      if (!response.ok) throw new Error(`Edge historical dispatch failed: ${response.status}`)
      submitted += 1
    }
    await prisma.$executeRawUnsafe(
      'UPDATE "weighvision_historical_reprocess_job" SET "status"=$1,"submittedSessions"=$2,"skippedSessions"=$3,"totalSessions"=$4,"completedAt"=NOW() WHERE "id"=$5',
      'submitted', submitted, skipped, sessions.length, job.id,
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    await prisma.$executeRawUnsafe(
      'UPDATE "weighvision_historical_reprocess_job" SET "status"=$1,"lastError"=$2 WHERE "id"=$3',
      'failed', message, job.id,
    )
    logger.error('Historical reprocess dispatch failed', { historicalJobId: job.id, error: message })
  }
}
