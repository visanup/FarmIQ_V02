import { PrismaClient } from '@prisma/client'
import { randomUUID } from 'crypto'

const prisma = new PrismaClient()

export type HistoricalAssociationRequest = {
  tenantId: string; farmId: string; barnId: string; batchId: string
  from: Date; to: Date; requestedBy?: string; reason: string
}

function validate(request: HistoricalAssociationRequest) {
  if (request.from > request.to) throw new Error('from must be before to')
  if (!request.reason.trim()) throw new Error('reason is required')
}

async function findCandidates(request: HistoricalAssociationRequest) {
  validate(request)
  return prisma.weighVisionSession.findMany({
    where: { tenantId: request.tenantId, farmId: request.farmId, barnId: request.barnId,
      startedAt: { gte: request.from, lte: request.to } },
    select: { id: true, sessionId: true, batchId: true }, orderBy: { startedAt: 'asc' },
  })
}

export async function previewHistoricalAssociation(request: HistoricalAssociationRequest) {
  const rows = await findCandidates(request)
  const eligible = rows.filter((row) => row.batchId === null)
  const alreadyAssociated = rows.filter((row) => row.batchId === request.batchId)
  const conflicts = rows.filter((row) => row.batchId !== null && row.batchId !== request.batchId)
  return { dryRun: true, targetBatchId: request.batchId,
    interval: { from: request.from.toISOString(), to: request.to.toISOString() },
    counts: { eligible: eligible.length, alreadyAssociated: alreadyAssociated.length, conflicts: conflicts.length },
    eligibleSessionIds: eligible.map((row) => row.sessionId),
    conflictSessionIds: conflicts.map((row) => row.sessionId) }
}

export async function confirmHistoricalAssociation(request: HistoricalAssociationRequest) {
  const preview = await previewHistoricalAssociation(request)
  if (!preview.eligibleSessionIds.length) return { ...preview, dryRun: false, associated: 0 }
  await prisma.$transaction(async (tx) => {
    const rows = await tx.weighVisionSession.findMany({ where: {
      tenantId: request.tenantId, sessionId: { in: preview.eligibleSessionIds }, batchId: null },
      select: { id: true, sessionId: true, batchId: true } })
    await tx.weighVisionSession.updateMany({ where: { id: { in: rows.map((row) => row.id) }, batchId: null }, data: { batchId: request.batchId } })
    for (const row of rows) await tx.$executeRawUnsafe(
      'INSERT INTO "weighvision_historical_association_audit" ("id","tenantId","sessionDbId","sessionId","previousBatchId","targetBatchId","requestedBy","reason") VALUES ($1,$2,$3,$4,$5,$6,$7,$8)',
      randomUUID(), request.tenantId, row.id, row.sessionId, row.batchId, request.batchId, request.requestedBy || null, request.reason)
  })
  return { ...preview, dryRun: false, associated: preview.eligibleSessionIds.length }
}

export async function enqueueHistoricalReprocess(request: HistoricalAssociationRequest) {
  if (process.env.HISTORICAL_REPROCESS_ENABLED !== 'true') throw new Error('HISTORICAL_REPROCESS_DISABLED')
  validate(request)
  // Reprocess applies to the Batch that has already been explicitly confirmed.
  // It is never inferred from an unassigned-session preview.
  const sessions = await prisma.weighVisionSession.findMany({
    where: { tenantId: request.tenantId, farmId: request.farmId, barnId: request.barnId, batchId: request.batchId,
      startedAt: { gte: request.from, lte: request.to } },
    include: { media: { select: { id: true } } },
  })
  const mediaAvailable = sessions.filter((session) => session.media.length > 0)
  const retentionMissingSessionIds = sessions.filter((session) => session.media.length === 0).map((session) => session.sessionId)
  if (!mediaAvailable.length) throw new Error('MEDIA_RETENTION_UNAVAILABLE')
  const jobId = randomUUID()
  await prisma.$executeRawUnsafe(
    'INSERT INTO "weighvision_historical_reprocess_job" ("id","tenantId","batchId","from","to","requestedBy","reason","totalSessions","skippedSessions") VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)',
    jobId, request.tenantId, request.batchId, request.from, request.to, request.requestedBy || null, request.reason,
    sessions.length, retentionMissingSessionIds.length)
  return { jobId, queue: 'historical-reprocess', status: 'queued', preflight: {
    totalSessions: sessions.length, mediaAvailable: mediaAvailable.length, retentionMissingSessionIds,
  } }
}

export async function cancelHistoricalReprocess(tenantId: string, jobId: string) {
  const changed = await prisma.$executeRawUnsafe(
    'UPDATE "weighvision_historical_reprocess_job" SET "status"=$1,"cancelledAt"=NOW() WHERE "id"=$2 AND "tenantId"=$3 AND "status"=$4',
    'cancelled', jobId, tenantId, 'queued')
  return Number(changed) === 1
}
